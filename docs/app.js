import {
  ANTAL_AVD, BUDGETAR, RADPRIS, VARDE_GRANS, deltagare, kronor, optimera, ratta, sammanfattning, skrallchanser,
  skrallKrav, vinst,
} from "./optimizer.js?v=20261014c";
import { KALLOR, backtesta, sammanstall } from "./backtest.js?v=20261014c";

const $ = (id) => document.getElementById(id);
const LAGRING = "travguiden";
const TZ = "Europe/Stockholm";

const state = {
  data: null,           // omgang.json
  exempel: false,
  budget: 200,          // kr
  kalla: "modell",      // valt förslag, se FORSLAG
  lasningar: {},        // {avd: [nr, ...]} för aktuell omgång
  oppna: new Set(),     // "avd-nr" för hästar med utfällda detaljer
  resultat: null,       // senaste optimeringen
  senaste: null,        // senaste.json – förra omgången
  rBudget: null,
  rOppna: new Set(),
  historik: null,       // historik.json, laddas först när backtestet öppnas
  btBudget: null,
};

// ---------- lagring (localStorage kan saknas eller kasta, t.ex. i privat läge) ----------

function lasLagring() {
  try { return JSON.parse(localStorage.getItem(LAGRING)) || {}; } catch { return {}; }
}
function sparaLagring() {
  try {
    const d = lasLagring();
    const id = state.data.omgang.id;
    d.budget = state.budget;
    d.kalla = state.kalla;
    d.lasningar = { [id]: state.lasningar };          // bara aktuell omgång behöver sparas
    d.budgetar = { ...(d.budgetar || {}), [id]: state.budget };
    const nycklar = Object.keys(d.budgetar).sort().slice(-6);   // budgeten per omgång till rättningen
    d.budgetar = Object.fromEntries(nycklar.map((k) => [k, d.budgetar[k]]));
    localStorage.setItem(LAGRING, JSON.stringify(d));
  } catch { /* låsningar sparas bara för den här sessionen */ }
}

// ---------- formatering ----------

const procent = (x) => (x == null ? "–" : x < 0.01 && x > 0 ? "<1" : String(Math.round(x * 100)));
const datumFmt = new Intl.DateTimeFormat("sv-SE", { timeZone: TZ, weekday: "long", day: "numeric", month: "long" });
const tidFmt = new Intl.DateTimeFormat("sv-SE", { timeZone: TZ, hour: "2-digit", minute: "2-digit" });
const kortDatum = new Intl.DateTimeFormat("sv-SE", { timeZone: TZ, day: "numeric", month: "short", year: "numeric" });
const kr = (x) => `${Math.round(x).toLocaleString("sv-SE")} kr`;
const plusKr = (x) => (x > 0 ? "+" : x < 0 ? "−" : "") + kr(Math.abs(x));
const decimal = (x, n = 2) => x.toFixed(n).replace(".", ",");
const METOD = { auto: "autostart", volte: "voltstart" };

function el(tag, attrs = {}, ...barn) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === "text") e.textContent = v;
    else if (k === "class") e.className = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v === true ? "" : v);
  }
  for (const b of barn.flat()) if (b != null && b !== false) e.append(b);
  return e;
}

// ---------- hämtning ----------

async function hamta(fil) {
  const r = await fetch(fil, { cache: "no-cache" });
  if (!r.ok) throw new Error(`${fil}: ${r.status}`);
  const d = await r.json();
  if (d.avdelningar && d.avdelningar.length !== ANTAL_AVD) throw new Error(`${fil}: väntade ${ANTAL_AVD} avdelningar`);
  return d;
}

// Förslagen. Experterna = Oddsen plus experternas system (chans_exp, där systemen finns). Skrällchansen =
// Oddsens chans, men systemet måste ha med omgångens bästa skrällar (1 upp till 200 kr, annars 2).
const FORSLAG = {
  modell: { namn: "Oddsen", under: "Streck + vinnarodds" },
  experter: { namn: "Experterna", under: "Oddsen + expertsystem" },
  skrall: { namn: "Skrällchansen", under: "Oddsen + 1–2 skrällar" },
};
const harExperter = (data) => Boolean(data?.experter?.length);
const chansFor = (h, kalla) => (kalla === "experter" && h.chans_exp != null ? h.chans_exp : h.chans);

/** Avdelningarna i optimerarens format, med chansen enligt valt förslag. */
const avdelningarFor = (data, kalla = state.kalla) => data.avdelningar.map((a) => ({
  avd: a.avd,
  hastar: a.hastar.map((h) => ({ nr: h.nr, chans: chansFor(h, kalla), streck: h.streck, struken: Boolean(h.struken) })),
}));

/** Optimera enligt ett förslag. Skrällchansen får krav på skrällar. */
function optimeraForslag(data, kalla, budget, lasningar) {
  const avd = avdelningarFor(data, kalla);
  return optimera(avd, budget, lasningar, undefined, kalla === "skrall" ? skrallKrav(avd, budget, lasningar) : {});
}

/** Kort förklaring under sammanfattningen. */
function forslagInfo(data, kalla, res) {
  if (kalla === "experter") {
    if (!harExperter(data)) {
      return data.omgang.avgjord ? "Experternas system sparades inte för den här omgången – förslaget är samma som Oddsen."
        : "Experternas system har inte publicerats än – förslaget är samma som Oddsen.";
    }
    const namn = data.experter.map((e) => e.namn);
    return `Bygger på ${namn.length} expertsystem: ${namn.join(", ")}.`;
  }
  if (kalla === "skrall" && res?.ok) {
    const s = res.val.filter((v) => v.skrall != null);
    if (!s.length) return "Inga skrällchanser i omgången just nu – förslaget är samma som Oddsen.";
    const namn = (v) => data.avdelningar[v.avd - 1].hastar.find((h) => h.nr === v.skrall)?.namn;
    return `Skrällar i systemet: ${s.map((v) => `${v.skrall} ${namn(v)} (avd ${v.avd})`).join(" och ")}.`;
  }
  return "";
}

function byggForslag(box, valj) {
  for (const b of box.querySelectorAll("button")) {
    b.addEventListener("click", () => valj(b.dataset.kalla));
  }
}
function markeraForslag() {
  for (const b of document.querySelectorAll(".forslag button")) b.setAttribute("aria-checked", String(b.dataset.kalla === state.kalla));
}

/** Chans och streck som andelar bland de hästar som startar (samma som optimeraren räknar med). */
const andelar = (optAvd) => Object.fromEntries(deltagare(optAvd).map((h) => [h.nr, h]));

// ---------- kupongen ----------

async function start() {
  initMeny();
  window.addEventListener("hashchange", visaVy);
  visaVy();
  const tvingaExempel = new URLSearchParams(location.search).has("exempel");
  try {
    if (tvingaExempel) throw new Error("exempel begärt");
    state.data = await hamta("omgang.json");
  } catch (e) {
    try {
      state.data = await hamta("exempel-omgang.json");
      state.exempel = true;
    } catch (e2) {
      $("rubrik").textContent = "Kunde inte ladda omgången";
      $("underrubrik").textContent = "Försök igen om en stund.";
      console.error(e, e2);
      return;
    }
  }
  const lagrat = lasLagring();
  if (BUDGETAR.includes(lagrat.budget)) state.budget = lagrat.budget;
  if (FORSLAG[lagrat.kalla]) state.kalla = lagrat.kalla;
  for (const box of document.querySelectorAll(".forslag")) {
    byggForslag(box, (k) => {
      state.kalla = k;
      markeraForslag();
      uppdatera();
      if (state.senaste) renderaRattning();
    });
  }
  markeraForslag();
  state.lasningar = (lagrat.lasningar || {})[state.data.omgang.id] || {};
  byggBudgetknappar($("budgetknappar"), () => state.budget, (b) => { state.budget = b; uppdatera(); });
  $("avdelningar").addEventListener("click", klickKupong);
  $("rensa").addEventListener("click", () => { state.lasningar = {}; uppdatera(); });
  renderaOmStatistik();
  uppdatera();
  setInterval(renderaTopp, 60_000);
}

function byggBudgetknappar(box, hamtaVald, valj) {
  box.replaceChildren(...BUDGETAR.map((b) => el("button", {
    type: "button", role: "radio", "data-budget": b, "aria-checked": String(b === hamtaVald()),
    "aria-label": `${b} kronor, upp till ${b / RADPRIS} rader`,
    onclick: () => { valj(b); markeraBudget(box, b); },
  }, `${b} kr`, el("small", { text: `${b / RADPRIS} rader` }))));
}
function markeraBudget(box, b) {
  for (const k of box.querySelectorAll("button")) k.setAttribute("aria-checked", String(Number(k.dataset.budget) === b));
}

function uppdatera() {
  const d = state.data;
  state.resultat = optimeraForslag(d, state.kalla, state.budget, state.lasningar);
  if (!state.resultat.ok && Object.keys(state.lasningar).length) {
    $("fel").textContent = state.resultat.fel;
    $("fel").hidden = false;
    state.resultat = optimeraForslag(d, state.kalla, state.budget, {});   // visa förslaget utan låsningar
  } else {
    $("fel").hidden = true;
  }
  const r = state.resultat;
  $("sammanfattning").textContent = r.ok ? sammanfattning(r) : r.fel;
  $("systemchans").textContent = r.ok ? `Chans att systemet ger 8 rätt: ${chansText(r.chans)}` : "";
  const info = forslagInfo(d, state.kalla, r);
  $("forslag-info").textContent = info;
  $("forslag-info").hidden = !info;
  $("rensa").hidden = !Object.values(state.lasningar).some((l) => l.length);
  renderaTopp();
  ritaAvdelningar($("avdelningar"), d, r.ok ? r.val : [], state.lasningar, state.oppna, true, state.kalla);
  sparaLagring();
}

function chansText(p) {
  if (p >= 0.01) return `${decimal(p * 100, 1)} %`;
  return `1 på ${Math.round(1 / p).toLocaleString("sv-SE")}`;
}

function renderaTopp() {
  const o = state.data.omgang;
  const stopp = new Date(o.spelstopp);
  const kvar = stopp - Date.now();
  $("rubrik").textContent = `V85 · ${o.bana}`;
  $("underrubrik").textContent = `${versal(datumFmt.format(stopp))} · första start ${tidFmt.format(stopp)}` +
    (o.omsattning ? ` · omsättning ${kr(o.omsattning)}` : "");
  const status = $("status");
  status.hidden = false;
  status.className = "status" + (kvar > 0 ? " oppen" : "");
  status.textContent = state.exempel ? "Exempel" : o.avgjord ? "Avgjord" : kvar > 0 ? "Öppen" : "Stängd";
  const ned = $("nedrakning");
  ned.hidden = kvar <= 0 || state.exempel;
  if (kvar > 0) {
    const t = Math.floor(kvar / 3_600_000), m = Math.floor((kvar % 3_600_000) / 60_000);
    ned.textContent = t >= 48 ? `Spelstopp om ${Math.floor(t / 24)} dagar` : `Spelstopp om ${t} h ${m} min`;
  }
  const banner = $("banner");
  if (state.exempel) {
    banner.hidden = false;
    banner.textContent = "Det här är en exempelomgång. Den riktiga visas när pipelinen har hämtat veckans V85.";
  } else if (kvar <= 0 && !o.avgjord) {
    banner.hidden = false;
    banner.textContent = "Spelstopp har passerat. Förslaget visar läget vid spelstopp – resultaten kommer under kvällen.";
  } else banner.hidden = true;
  $("fot-uppdaterad").textContent = state.data.uppdaterad
    ? `Uppdaterad ${versal(kortDatum.format(new Date(state.data.uppdaterad)))} ${tidFmt.format(new Date(state.data.uppdaterad))}` : "";
}
const versal = (s) => s.charAt(0).toUpperCase() + s.slice(1);

/**
 * Ritar avdelningarna. val: [{avd, nr: [...]}] från optimeraren; interaktiv = låsning och detaljer på klick.
 */
function ritaAvdelningar(lista, data, val, lasningar, oppna, interaktiv, kalla) {
  const valPer = Object.fromEntries(val.map((v) => [v.avd, new Set(v.nr)]));
  const optAvd = avdelningarFor(data, kalla);
  const skrallar = kalla === "skrall" ? skrallchanser(avdelningarFor(data, "modell")) : {};
  const experter = expertInfo(data);
  lista.replaceChildren(...data.avdelningar.map((a, i) => {
    const valda = valPer[a.avd] || new Set();
    const last = new Set(lasningar[a.avd] || []);
    const andel = andelar(optAvd[i]);
    const skrall = skrallar[a.avd]?.nr;
    const vinnare = new Set(a.vinnare || []);
    const avgjord = vinnare.size > 0;
    const traff = avgjord && [...valda].some((n) => vinnare.has(n));
    const start = a.starttid ? tidFmt.format(new Date(a.starttid)) : "";
    const typ = valda.size === 1 ? el("span", { class: "avd-typ spik", text: "SPIK" })
      : el("span", { class: "avd-typ", text: valda.size ? `${valda.size} hästar` : "" });
    return el("li", { class: "avd" + (avgjord && valda.size ? (traff ? " traff" : " miss") : ""), "data-avd": a.avd },
      el("div", { class: "avd-huvud" },
        el("span", { class: "avd-nr", "aria-label": `Avdelning ${a.avd}`, text: a.avd }),
        el("div", { class: "avd-text" },
          el("b", { text: `Lopp ${a.loppnr} · ${a.distans} m ${METOD[a.startmetod] || a.startmetod || ""}${start ? " · " + start : ""}` }),
          el("span", { text: kortLoppnamn(a.namn), title: a.namn || "" })),
        typ),
      el("ul", { class: "hastar" }, ...a.hastar.map((h) => hastRad(a, h, andel[h.nr], valda.has(h.nr), last.has(h.nr),
        vinnare.has(h.nr), oppna.has(`${a.avd}-${h.nr}`), interaktiv, { skrall: skrall === h.nr, experter: experter(a, h) }))));
  }));
}

/** (avd, häst) -> {antal, totalt, namn: ["Mats E Djuse (spik)", ...]} om experternas system finns. */
function expertInfo(data) {
  if (!harExperter(data)) return () => null;
  const perAvd = {};          // "avd-expert" -> antal valda hästar
  for (const a of data.avdelningar) {
    for (const h of a.hastar) for (const e of h.experter || []) perAvd[`${a.avd}-${e}`] = (perAvd[`${a.avd}-${e}`] || 0) + 1;
  }
  return (a, h) => ({
    antal: (h.experter || []).length,
    totalt: data.experter.length,
    namn: (h.experter || []).map((e) => data.experter[e].namn + (perAvd[`${a.avd}-${e}`] === 1 ? " (spik)" : "")),
  });
}

function kortLoppnamn(namn) {
  if (!namn) return "";
  return namn.split(" - ").filter((d) => !/^\(.*\)$/.test(d)).slice(-2).join(" – ").replace(/\s*\(.*\)\s*$/, "");
}

function hastRad(a, h, andel, vald, last, vann, oppen, interaktiv, extra = {}) {
  const exp = extra.experter;
  const struken = Boolean(h.struken);
  const varde = andel && andel.chans - andel.streck >= VARDE_GRANS;
  const id = `d-${interaktiv ? "k" : "r"}-${a.avd}-${h.nr}`;
  const klass = ["hast", vald && "vald", last && "last", struken && "struken", vann && "vinnare"].filter(Boolean).join(" ");
  const undertext = [h.kusk, a.startmetod === "auto" && h.spar ? `spår ${h.spar}` : null,
    h.distans && a.distans && h.distans > a.distans ? `+${h.distans - a.distans} m` : null,
    exp && exp.antal ? `${exp.antal}/${exp.totalt} experter` : null,
    h.placering != null && !struken ? (h.placering ? `${h.placering}:a` : "oplac.") : null].filter(Boolean).join(" · ");
  return el("li", { class: klass, "data-nr": h.nr },
    el("div", { class: "hast-rad" },
      el("button", { type: "button", class: "hast-info", "data-detalj": "1", "aria-expanded": String(oppen), "aria-controls": id },
        el("span", { class: "startnr", text: h.nr }),
        el("span", { class: "namnblock" },
          el("span", { class: "hastnamn" }, h.namn, extra.skrall && !struken ? el("span", { class: "skrall-mark", text: " SKRÄLL" }) : null,
            vann ? el("span", { class: "vinnar-mark", text: " ✓ vann" }) : null),
          el("span", { class: "kusk", text: struken ? "Struken" : undertext }))),
      el("button", {
        type: "button", class: "valruta", "data-las": interaktiv ? "1" : null, disabled: struken || !interaktiv || null,
        "aria-pressed": interaktiv ? String(last) : null,
        "aria-label": `${h.namn}: streck ${procent(h.streck)} %, chans ${procent(andel?.chans)} %${vald ? ", med i systemet" : ""}${last ? ", låst" : ""}`,
      },
        last ? el("span", { class: "las", "aria-hidden": "true", text: "🔒" }) : null,
        varde ? el("span", { class: "prick", "aria-hidden": "true" }) : null,
        el("span", { class: "del" }, el("b", { text: procent(h.streck) }), el("small", { text: "streck" })),
        el("span", { class: "del" }, el("b", { text: struken ? "–" : procent(andel?.chans) }), el("small", { text: "chans" })))),
    oppen ? detaljer(h, andel, id, exp) : null);
}

function detaljer(h, andel, id, exp) {
  const [ls, lv, lp] = h.livs || [];
  const [as, av] = h.ar || [];
  const rader = [
    ["Kusk", h.kusk ? `${h.kusk}${h.kusk_proc != null ? ` (${Math.round(h.kusk_proc * 100)} % segrar i år)` : ""}` : null],
    ["Tränare", h.tranare],
    ["Häst", [h.alder ? `${h.alder} år` : null, h.kon].filter(Boolean).join(", ") || null],
    ["Karriär", ls != null ? `${ls} starter, ${lv ?? 0} segrar, ${lp ?? 0} pallplatser` : null],
    ["I år", as != null ? `${as} starter, ${av ?? 0} segrar` : null],
    ["Rekord", h.rekord],
    ["Intjänat", h.intjant != null ? kr(h.intjant) : null],
    ["Snittodds, 5 senaste", h.snittodds ? decimal(h.snittodds) : null],
    ["Vinnarodds nu", h.odds ? decimal(h.odds) : null],
    ["Slutodds", h.slutodds ? decimal(h.slutodds) : null],
    ["Km-tid", h.km_tid],
    ["Experter", exp ? (exp.namn.length ? `${exp.antal} av ${exp.totalt}: ${exp.namn.join(", ")}` : `ingen av ${exp.totalt}`) : null],
  ].filter(([, v]) => v);
  const v = andel ? andel.chans - andel.streck : null;
  return el("div", { class: "detaljer", id },
    el("dl", {}, ...rader.flatMap(([k, val]) => [el("dt", { text: k }), el("dd", { text: val })])),
    v != null && !h.struken ? el("p", {
      text: v >= VARDE_GRANS ? `Understreckad: chansen är ${Math.round(v * 100)} procentenheter högre än strecken.`
        : v <= -VARDE_GRANS ? `Överstreckad: strecken är ${Math.round(-v * 100)} procentenheter högre än chansen.`
          : "Strecken och chansen är ungefär lika.",
    }) : null);
}

function klickKupong(e) {
  const li = e.target.closest(".hast");
  const avd = Number(e.target.closest(".avd")?.dataset.avd);
  if (!li || !avd) return;
  const nr = Number(li.dataset.nr);
  if (e.target.closest("[data-las]")) {
    const lista = new Set(state.lasningar[avd] || []);
    lista.has(nr) ? lista.delete(nr) : lista.add(nr);
    if (lista.size) state.lasningar[avd] = [...lista].sort((a, b) => a - b);
    else delete state.lasningar[avd];
    uppdatera();
  } else if (e.target.closest("[data-detalj]")) {
    const k = `${avd}-${nr}`;
    state.oppna.has(k) ? state.oppna.delete(k) : state.oppna.add(k);
    uppdatera();
  }
}

// ---------- förra omgången ----------

async function oppnaRattning() {
  if (!state.senaste) {
    try {
      state.senaste = await hamta("senaste.json");
    } catch (e) {
      $("r-resultat").replaceChildren(el("p", { class: "dampad", text: "Ingen avgjord omgång finns ännu." }));
      return;
    }
    const sparad = (lasLagring().budgetar || {})[state.senaste.omgang.id];
    state.rBudget = BUDGETAR.includes(sparad) ? sparad : state.budget;
    byggBudgetknappar($("r-budgetknappar"), () => state.rBudget, (b) => { state.rBudget = b; renderaRattning(); });
    $("r-avdelningar").addEventListener("click", (e) => {
      const li = e.target.closest(".hast");
      const avd = e.target.closest(".avd")?.dataset.avd;
      if (!li || !avd || !e.target.closest("[data-detalj]")) return;
      const k = `${avd}-${li.dataset.nr}`;
      state.rOppna.has(k) ? state.rOppna.delete(k) : state.rOppna.add(k);
      renderaRattning();
    });
  }
  renderaRattning();
}

function renderaRattning() {
  const d = state.senaste;
  const o = d.omgang;
  $("r-rubrik").textContent = `V85 · ${o.bana}`;
  $("r-underrubrik").textContent = versal(datumFmt.format(new Date(o.spelstopp))) +
    (o.omsattning ? ` · omsättning ${kr(o.omsattning)}` : "");
  const res = optimeraForslag(d, state.kalla, state.rBudget, {});
  if (!res.ok) { $("r-resultat").replaceChildren(el("p", { class: "fel", text: res.fel })); return; }
  const vinnare = Object.fromEntries(d.avdelningar.map((a) => [a.avd, a.vinnare || []]));
  const ersattare = Object.fromEntries(d.avdelningar.map((a) => {
    const kvar = a.hastar.filter((h) => !h.struken && h.streck != null);
    const fav = kvar.reduce((b, h) => (!b || h.streck > b.streck ? h : b), null);
    return [a.avd, { struken: a.hastar.filter((h) => h.struken).map((h) => h.nr), favorit: fav?.nr }];
  }));
  const r = ratta(res.val, vinnare, ersattare);
  const utd = Object.fromEntries(Object.entries(d.utdelning).map(([k, u]) => [k, u.kr]));
  const v = vinst(r.perRatt, utd);
  const info = forslagInfo(d, state.kalla, res);
  $("r-resultat").replaceChildren(
    el("p", { class: "sammanfattning", text: sammanfattning(res) }),
    info ? el("p", { class: "forklaring-kort", text: info }) : null,
    el("div", { class: "r-stort" },
      el("div", {}, el("b", { text: `${r.ratt} rätt` }), el("span", { text: "bästa raden" })),
      el("div", {}, el("b", { class: v - res.kostnad >= 0 ? "plus" : "", text: kr(v) }),
        el("span", { text: `tillbaka · netto ${plusKr(v - res.kostnad)}` }))),
    Object.keys(r.perRatt).some((k) => k >= 5)
      ? el("p", { class: "forklaring-kort", text: Object.entries(r.perRatt).filter(([k]) => k >= 5).sort((a, b) => b[0] - a[0])
        .map(([k, n]) => `${n} ${n === 1 ? "rad" : "rader"} med ${k} rätt`).join(" · ") }) : null);
  $("r-utdelning").hidden = !Object.keys(d.utdelning).length;
  $("r-utdelning-innehall").replaceChildren(el("table", { class: "stat-tabell" },
    el("thead", {}, el("tr", {}, el("th", { text: "Rätt" }), el("th", { class: "tal", text: "Per rad" }),
      el("th", { class: "tal", text: "Vinnande rader" }), el("th", { class: "tal", text: "Dina" }))),
    el("tbody", {}, ...Object.entries(d.utdelning).sort((a, b) => b[0] - a[0]).map(([k, u]) =>
      el("tr", { class: r.perRatt[k] ? "har-vinst" : "" }, el("td", { text: `${k} rätt` }), el("td", { class: "tal", text: kr(u.kr) }),
        el("td", { class: "tal", text: u.antal != null ? u.antal.toLocaleString("sv-SE") : "–" }),
        el("td", { class: "tal", text: r.perRatt[k] || "–" }))))));
  ritaAvdelningar($("r-avdelningar"), d, res.val, {}, state.rOppna, false, state.kalla);
}

// ---------- backtest ----------

async function oppnaBacktest() {
  if (!state.historik) {
    try {
      state.historik = await (await fetch("historik.json", { cache: "no-cache" })).json();
    } catch (e) {
      $("backtest-innehall").replaceChildren(el("p", { class: "fel", text: "Kunde inte ladda historiken." }));
      return;
    }
    state.btBudget = state.budget;
    byggBudgetknappar($("bt-budgetknappar"), () => state.btBudget, (b) => { state.btBudget = b; renderaBacktest(); });
  }
  renderaBacktest();
}

function renderaBacktest() {
  const box = $("backtest-innehall");
  if (!state.historik.omgangar.length) {
    box.replaceChildren(el("p", { class: "dampad", text: "Ingen historik ännu." }));
    return;
  }
  const serier = Object.keys(KALLOR).map((k, i) => {
    const spel = backtesta(state.historik, state.btBudget, k);
    return { k, namn: KALLOR[k].namn, spel, sum: sammanstall(spel), farg: `var(--serie-${i + 1})` };
  }).filter((s) => s.spel.length);
  const utanExperter = !serier.some((s) => s.k === "experter");
  const [m] = serier;
  const forsta = m.spel[0]?.datum;
  box.replaceChildren(
    el("div", { class: "r-stort" }, ...serier.map((s) => el("div", {},
      el("span", {}, el("i", { class: "nyckel", style: `background:${s.farg}` }), s.namn),
      el("b", { class: s.sum.netto >= 0 ? "plus" : "minus", text: plusKr(s.sum.netto) }),
      el("span", { text: `${kr(s.sum.insats)} in · ${kr(s.sum.tillbaka)} tillbaka · ${Math.round(s.sum.aterbetalning * 100)} % återbetalning` })))),
    diagram(serier),
    el("div", { class: "tabell-scroll" }, el("table", { class: "stat-tabell", style: "margin-top:12px" },
      el("thead", {}, el("tr", {}, el("th", { text: "" }), ...[8, 7, 6, 5].map((k) => el("th", { class: "tal", text: `${k} rätt` })),
        el("th", { class: "tal", text: "Med vinst" }))),
      el("tbody", {}, ...serier.map((s) => el("tr", {}, el("td", { text: s.namn }),
        ...[8, 7, 6, 5].map((k) => el("td", { class: "tal", text: s.sum.fordelning[k] })),
        el("td", { class: "tal", text: `${s.sum.medVinst} av ${s.sum.omgangar}` })))))),
    el("h2", { class: "kort-rubrik", style: "margin-top:18px", text: "Omgång för omgång (Oddsen)" }),
    el("div", { class: "tabell-scroll" }, el("table", { class: "stat-tabell" },
      el("thead", {}, el("tr", {}, el("th", { text: "Datum" }), el("th", { text: "Bana" }), el("th", { class: "tal", text: "Rätt" }),
        el("th", { class: "tal", text: "Tillbaka" }), el("th", { class: "tal", text: "Saldo" }))),
      el("tbody", {}, ...[...m.spel].reverse().map((s) => el("tr", { class: s.vinst > 0 ? "har-vinst" : "" },
        el("td", { text: s.datum }), el("td", { text: s.bana }), el("td", { class: "tal", text: s.ratt }),
        el("td", { class: "tal", text: s.vinst ? kr(s.vinst) : "–" }),
        el("td", { class: "tal", text: plusKr(s.saldo) })))))),
    utanExperter ? el("p", { class: "bt-not", text: "Experterna saknas i backtestet: ATG raderar experternas kuponger efter loppet, " +
      "så de har bara sparats sedan oktober 2026. Förslaget kommer med här när de första omgångarna med expertsystem är avgjorda." }) : null,
    el("p", { class: "bt-not", text: `${m.sum.omgangar} omgångar sedan ${forsta}. Chanserna i backtestet är räknade med vikter som bara sett ` +
      "lopp före omgångens månad, och utan vinnarodds (de finns inte sparade från före spelstopp i historiken). " +
      "Utdelningen per rad är ordinarie (utan Boost). Ett fåtal stora vinster avgör mycket, så läs resultatet som en riktning, inte en garanti." }),
  );
}

function diagram(serier) {
  const B = 640, H = 220, P = { v: 56, h: 8, t: 10, b: 22 };
  const n = Math.max(...serier.map((s) => s.spel.length));
  const alla = serier.flatMap((s) => s.spel.map((x) => x.saldo)).concat(0);
  const min = Math.min(...alla), max = Math.max(...alla);
  const sp = max - min || 1;
  const x = (i) => P.v + (i / Math.max(n - 1, 1)) * (B - P.v - P.h);
  const y = (v) => P.t + (1 - (v - min) / sp) * (H - P.t - P.b);
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", `0 0 ${B} ${H}`);
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", "Saldo över tid: " + serier.map((s) => `${s.namn} ${plusKr(s.sum.netto)}`).join(", "));
  const add = (tag, attrs, text) => {
    const e = document.createElementNS(ns, tag);
    for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
    if (text != null) e.textContent = text;
    svg.append(e);
  };
  for (const v of [max, (max + min) / 2, min]) {
    add("line", { class: "grid", x1: P.v, x2: B - P.h, y1: y(v), y2: y(v) });
    add("text", { class: "axel", x: P.v - 6, y: y(v) + 3, "text-anchor": "end" }, plusKr(v));
  }
  add("line", { class: "noll", x1: P.v, x2: B - P.h, y1: y(0), y2: y(0) });
  for (const s of serier) {
    add("polyline", { class: "linje", stroke: s.farg, points: s.spel.map((p, i) => `${x(i)},${y(p.saldo)}`).join(" ") });
  }
  const forst = serier[0].spel[0], sist = serier[0].spel.at(-1);
  if (forst) add("text", { class: "axel", x: P.v, y: H - 6 }, forst.datum);
  if (sist) add("text", { class: "axel", x: B - P.h, y: H - 6, "text-anchor": "end" }, sist.datum);
  return el("div", { class: "bt-diagram" }, svg);
}

// ---------- om ----------

function renderaOmStatistik() {
  const s = state.data?.statistik;
  if (!s || !s.lopp) return;
  const bra = s.forbattring > 2 * s.standardfel;
  $("om-statistik").replaceChildren(
    el("p", { text: `Utvärdering på ${s.lopp} V85-lopp, där varje månad bedömts med vikter som bara sett tidigare lopp: ` +
      `strecken gav vinnaren i snitt logloss ${decimal(s.logloss_streck, 3)}, Oddsen ${decimal(s.logloss_modell, 3)} (lägre är bättre). ` +
      (bra ? "Skillnaden är tydlig." : "Skillnaden är liten och inte säkerställd än – den blir tydligare med fler omgångar.") +
      ` Favoriten vann ${Math.round(s.favorit_vann * 100)} % av loppen.` }),
    s.vikter ? el("p", { class: "dampad", text: `Aktuella vikter: a = ${decimal(s.vikter.log_streck, 2)}` +
      (s.vikter.odds_mot_streck ? `, vinnarodds ${decimal(s.vikter.odds_mot_streck, 2)}` : "") +
      ` (skattade på ${s.traningslopp.toLocaleString("sv-SE")} lopp).` }) : null);
}

// ---------- meny och vyer ----------

const VYER = { kupong: "Kupongen", rattning: "Förra omgången", backtest: "Varje omgång", om: "Om" };

function initMeny() {
  const knapp = $("meny-knapp"), lista = $("meny-lista");
  const stang = () => { lista.hidden = true; knapp.setAttribute("aria-expanded", "false"); };
  knapp.addEventListener("click", (e) => {
    e.stopPropagation();
    lista.hidden = !lista.hidden;
    knapp.setAttribute("aria-expanded", String(!lista.hidden));
  });
  lista.addEventListener("click", stang);
  document.addEventListener("click", (e) => { if (!lista.hidden && !lista.contains(e.target)) stang(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") stang(); });
}

function visaVy() {
  const vy = location.hash.slice(1) in VYER ? location.hash.slice(1) : "kupong";
  document.body.dataset.vy = vy;
  for (const s of document.querySelectorAll("main > .vy")) s.hidden = s.dataset.vy !== vy;
  for (const a of document.querySelectorAll("#meny-lista a")) {
    if (a.dataset.vy === vy) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
  }
  $("meny-aktuell").textContent = VYER[vy];
  if (vy === "rattning") oppnaRattning();
  if (vy === "backtest") oppnaBacktest();
  window.scrollTo(0, 0);
}

start();
