// Röktest av gränssnittet i en riktig webbläsare (Chromium via Playwright), med appens riktiga data i docs/.
// Körs i GitHub Actions (tests.yml, jobbet ui). Varje vy öppnas i mobil- och datorbredd, och testet underkänner:
// fel i konsolen, "null"/"undefined"/"NaN" i texten (som "null" i rättningen 3 november 2026), sidledsscroll och
// vyer utan sitt huvudinnehåll. Dessutom provas förslagsknapparna, Veckans läge och Mina spel.
//
//   npm install --no-save playwright@1.49.1 && npx playwright install chromium && node tests/ui/rok.mjs

import { chromium } from "playwright";
import http from "node:http";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const DOCS = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../docs");
const TYPER = {
  ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css", ".json": "application/json",
  ".svg": "image/svg+xml", ".png": "image/png", ".webmanifest": "application/manifest+json",
};
const FEL_TEXT = /\b(null|undefined|NaN)\b|\[object Object\]/;
const BREDDER = [{ namn: "mobil", width: 375, height: 812 }, { namn: "dator", width: 1280, height: 800 }];

const server = http.createServer(async (req, res) => {
  const fil = path.join(DOCS, decodeURIComponent(new URL(req.url, "http://x").pathname).replace(/\/$/, "/index.html"));
  try {
    if (!fil.startsWith(DOCS)) throw new Error("utanför docs");
    const data = await fs.readFile(fil);
    res.writeHead(200, { "Content-Type": TYPER[path.extname(fil)] || "application/octet-stream" });
    res.end(data);
  } catch {
    res.writeHead(404);
    res.end();
  }
});
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const BAS = `http://127.0.0.1:${server.address().port}/`;

const omgang = JSON.parse(await fs.readFile(path.join(DOCS, "omgang.json"), "utf8"));
const fel = [];
const ok = [];
let n = 0;

async function sida(browser, bredd) {
  const context = await browser.newContext({ viewport: { width: bredd.width, height: bredd.height } });
  const page = await context.newPage();
  page.konsol = [];
  page.on("console", (m) => { if (m.type() === "error") page.konsol.push(m.text()); });
  page.on("pageerror", (e) => page.konsol.push(String(e)));
  return page;
}

async function kontrollera(page, namn) {
  const r = await page.evaluate(() => ({
    text: [...document.querySelectorAll("main > .vy:not([hidden])")].map((v) => v.innerText).join("\n"),
    scroll: document.documentElement.scrollWidth, vy: window.innerWidth,
  }));
  const m = r.text.match(FEL_TEXT);
  if (m) fel.push(`${namn}: texten innehåller "${m[0]}" – …${r.text.slice(Math.max(0, m.index - 60), m.index + 20)}…`);
  if (r.scroll > r.vy + 1) fel.push(`${namn}: sidledsscroll (${r.scroll} > ${r.vy} px)`);
  if (page.konsol.length) fel.push(`${namn}: fel i konsolen: ${page.konsol.join(" | ")}`);
  page.konsol.length = 0;
}

async function steg(namn, fn) {
  try {
    await fn();
    ok.push(namn);
  } catch (e) {
    fel.push(`${namn}: ${e.message.split("\n")[0]}`);
  }
}

async function oppna(page, vy, sok = "") {
  await page.goto(`${BAS}?t=${++n}${sok}#${vy}`);
}

const browser = await chromium.launch();
for (const bredd of BREDDER) {
  const page = await sida(browser, bredd);
  const b = bredd.namn;

  await steg(`${b} kupongen`, async () => {
    await oppna(page, "kupong");
    await page.waitForSelector("#avdelningar .avd", { timeout: 10000 });
    const antal = await page.locator("#avdelningar .avd").count();
    if (antal !== omgang.spel.antal_avd) throw new Error(`${antal} avdelningar, väntade ${omgang.spel.antal_avd}`);
    const sammanfattning = await page.locator("#sammanfattning").innerText();
    if (!/rader? · .* kr/.test(sammanfattning)) throw new Error(`sammanfattningen: "${sammanfattning}"`);
    await kontrollera(page, `${b} kupongen`);
  });

  await steg(`${b} förslag och insatser`, async () => {
    for (const k of ["experter", "skrall", "hastkoll", "modell"]) {
      await page.locator(`section[data-vy="kupong"] .forslag button[data-kalla="${k}"]`).click();
      for (const kr of [25, 500, 200]) await page.locator(`#budgetknappar button[data-budget="${kr}"]`).click();
      await kontrollera(page, `${b} förslaget ${k}`);
    }
  });

  await steg(`${b} spikar`, async () => {
    await page.locator('#spikknappar button[data-spikar="2"]').click();
    let text = await page.locator("#sammanfattning").innerText();
    if (!/— 2 spikar/.test(text)) throw new Error(`2 spikar valda, sammanfattningen: "${text}"`);
    await page.locator("#avdelningar .avd-huvud").first().click();
    const forsta = page.locator("#avdelningar .avd").first();
    await forsta.locator(".hast:not(.struken) .spika").last().click();      // en lågt streckad häst som egen spik
    if (!/SPIK/.test(await forsta.locator(".avd-typ").innerText())) throw new Error("den egna spiken syns inte i avdelningen");
    text = await page.locator("#sammanfattning").innerText();
    if (!/— 2 spikar/.test(text)) throw new Error(`egen spik + 2 spikar, sammanfattningen: "${text}"`);
    await kontrollera(page, `${b} spikar`);
    await page.locator("#rensa").click();
    await page.locator('#spikknappar button[data-spikar="auto"]').click();
    await forsta.locator(".avd-huvud").click();
  });

  await steg(`${b} utfälld avdelning och Veckans läge`, async () => {
    await page.locator("#avdelningar .avd-huvud").first().click();
    await page.waitForSelector("#avdelningar .avd.utfalld .hast");
    const lank = page.locator("#veckolage .vl-lank").first();
    if (await lank.count()) {
      const avd = await lank.getAttribute("data-avd");
      await lank.click();
      await page.waitForSelector(`#avdelningar .avd.utfalld[data-avd="${avd}"]`);
    }
    await kontrollera(page, `${b} utfälld avdelning`);
  });

  await steg(`${b} förra omgången`, async () => {
    await oppna(page, "rattning");
    await page.waitForSelector("#r-resultat .r-stort, #r-resultat .dampad", { timeout: 10000 });
    await page.waitForSelector("#r-avdelningar .avd");
    await kontrollera(page, `${b} förra omgången`);
  });

  await steg(`${b} backtestet`, async () => {
    await oppna(page, "backtest");
    await page.waitForSelector("#backtest-innehall table", { timeout: 20000 });
    await page.locator("#bt-period").selectOption("premiar");
    await page.waitForSelector("#backtest-innehall table");
    await kontrollera(page, `${b} backtestet`);
  });

  await steg(`${b} om-sidan`, async () => {
    await oppna(page, "om");
    await page.waitForSelector("#drift li, #drift p", { timeout: 10000 });
    await kontrollera(page, `${b} om-sidan`);
  });

  await steg(`${b} exempelomgången`, async () => {
    await oppna(page, "kupong", "&exempel");
    await page.waitForSelector("#avdelningar .avd", { timeout: 10000 });
    await kontrollera(page, `${b} exempelomgången`);
  });
  await page.context().close();
}

// Mina spel: spara på kupongen, och ett sparat spel för förra omgången rättas under Förra omgången
await steg("Mina spel", async () => {
  const page = await sida(browser, BREDDER[0]);
  await oppna(page, "kupong");
  await page.waitForSelector("#avdelningar .avd");
  const knapp = page.locator("#spara-spel");
  await knapp.click();
  if (!/Sparat/.test(await knapp.innerText())) throw new Error(`knappen efter sparande: "${await knapp.innerText()}"`);
  // Ett spel som inte är avgjort går att ta bort direkt på kupongen
  if (await page.locator("#sparade-spel li").count() !== 1) throw new Error("det sparade spelet syns inte på kupongen");
  await page.locator("#sparade-spel [data-ta-bort]").click();
  if (await page.locator("#sparade-spel li").count() !== 0 || /Sparat/.test(await knapp.innerText())) {
    throw new Error("spelet togs inte bort från kupongen");
  }
  await knapp.click();
  await page.evaluate(async () => {
    const s = await (await fetch("senaste.json")).json();
    const lista = JSON.parse(localStorage.getItem("travguiden-mina-spel"));
    const val = s.avdelningar.map((a) => ({ avd: a.avd, nr: a.hastar.filter((h) => !h.struken).slice(0, 2).map((h) => h.nr) }));
    lista.push({ id: `${s.omgang.id}:1`, omgang: s.omgang.id, datum: s.omgang.datum, bana: s.omgang.bana,
      spelform: s.omgang.spelform, kalla: "modell", kallnamn: "Oddsen", budget: 100,
      rader: 2 ** val.length, kostnad: 2 ** val.length * 0.5, val, sparad: "2026-01-01T00:00:00Z" });
    localStorage.setItem("travguiden-mina-spel", JSON.stringify(lista));
  });
  await oppna(page, "rattning");
  await page.waitForSelector("#r-minaspel:not([hidden]) .minaspel-lista li", { timeout: 10000 });
  const text = await page.locator("#r-minaspel").innerText();
  if (!/rätt · .* tillbaka/.test(text)) throw new Error(`Mina spel: "${text}"`);
  await kontrollera(page, "Mina spel");
  await page.locator("#r-minaspel [data-ta-bort]").first().click();
  await page.context().close();
});

await browser.close();
server.close();
console.log(ok.map((x) => `ok   ${x}`).join("\n"));
if (fel.length) {
  console.error(fel.map((x) => `FEL  ${x}`).join("\n"));
  process.exit(1);
}
console.log(`\n${ok.length} steg ok`);
