import {
  BUDGETAR, RADPRIS, VARDE_GRANS, deltagare, kronor, optimera, ratta, sammanfattning, skrallchanser,
  skrallKrav, vinst,
} from "./optimizer.js?v=20261017b";
import { KALLOR, PERIODER, backtesta, iPeriod, sammanstall } from "./backtest.js?v=20261017b";

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
  utfallda: new Set(),  // avdelningar med utfälld hästlista
  rUtfallda: new Set(),
  historik: null,       // historik.json, laddas först när backtestet öppnas
  btBudget: null,
  btPeriod: "alla",
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
  if (d.avdelningar && d.avdelningar.length !== spelFor(d).antal_avd) throw new Error(`${fil}: fel antal avdelningar`);
  return d;
}

// Förslagen. Experterna = Oddsen plus experternas system (chans_exp, där systemen finns). Skrällchansen =
// Experternas chans (Oddsens om expertsystem saknas), men systemet måste ha med omgångens bästa skrällar
// (1 upp till 200 kr, annars 2).
const FORSLAG = {
  modell: { namn: "Oddsen", under: "Streck + vinnarodds" },
  experter: { namn: "Experterna", under: "Oddsen + expertsystem" },
  skrall: { namn: "Skrällchansen", under: "Experterna + 1–2 skrällar" },
};
const harExperter = (data) => Boolean(data?.experter?.length);
const chansFor = (h, kalla) => ((kalla === "experter" || kalla === "skrall") && h.chans_exp != null ? h.chans_exp : h.chans);

/** Avdelningarna i optimerarens format, med chansen enligt valt förslag. */
const avdelningarFor = (data, kalla = state.kalla) => data.avdelningar.map((a) => ({
  avd: a.avd,
  hastar: a.hastar.map((h) => ({ nr: h.nr, chans: chansFor(h, kalla), streck: h.streck, struken: Boolean(h.struken) })),
}));

/** Optimera enligt ett förslag. Skrällchansen får krav på skrällar. */
/** Spelreglerna för omgången (V85: 8 avdelningar och 50 öre; nya V75: 7 avdelningar och 60 öre). */
function spelFor(data) {
  return data?.spel ?? { spelform: data?.omgang?.spelform ?? "V85", antal_avd: data?.avdelningar?.length ?? 8,
    radpris: RADPRIS, vinstgrupper: [8, 7, 6, 5] };
}

function optimeraForslag(data, kalla, budget, lasningar) {
  const avd = avdelningarFor(data, kalla);
  return optimera(avd, budget, lasningar, undefined, kalla === "skrall" ? skrallKrav(avd, budget, lasningar) : {},
    spelFor(data).radpris);
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
    return `Skrällar i systemet: ${s.map((v) => `${v.skrall} ${namn(v)} (avd ${v.avd})`).join(" och ")}.` +
      (harExperter(data) ? " Chansen bygger på oddsen och experternas system." : "");
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
  byggBudgetknappar($("budgetknappar"), () => state.budget, (b) => { state.budget = b; uppdatera(); }, spelFor(state.data).radpris);
  $("avdelningar").addEventListener("click", klickKupong);
  fallText = fallKnapp($("fall-alla"), state.utfallda, uppdatera, spelFor(state.data).antal_avd);
  $("rensa").addEventListener("click", () => { state.lasningar = {}; uppdatera(); });
  renderaOmStatistik();
  renderaDrift(state.data);
  uppdatera();
  setInterval(renderaTopp, 60_000);
}

/** radpris = null: antalet rader skrivs inte ut (backtestet blandar V85 och V75 med olika radpris). */
function byggBudgetknappar(box, hamtaVald, valj, radpris = null) {
  const rader = (b) => Math.floor(b / radpris + 1e-9);
  box.replaceChildren(...BUDGETAR.map((b) => el("button", {
    type: "button", role: "radio", "data-budget": b, "aria-checked": String(b === hamtaVald()),
    "aria-label": radpris ? `${b} kronor, upp till ${rader(b)} rader` : `${b} kronor`,
    onclick: () => { valj(b); markeraBudget(box, b); },
  }, `${b} kr`, radpris ? el("small", { text: `${rader(b)} rader` }) : null)));
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
  $("systemchans").textContent = r.ok ? `Chans att systemet ger ${spelFor(d).antal_avd} rätt: ${chansText(r.chans)}` : "";
  const info = forslagInfo(d, state.kalla, r);
  $("forslag-info").textContent = info;
  $("forslag-info").hidden = !info;
  $("rensa").hidden = !Object.values(state.lasningar).some((l) => l.length);
  renderaTopp();
  ritaAvdelningar($("avdelningar"), d, r.ok ? r.val : [], state.lasningar, state.oppna, true, state.kalla, state.utfallda);
  fallText();
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
  const spel = spelFor(state.data);
  $("rubrik").textContent = `${spel.spelform} · ${o.bana}`;
  $("undertitel").textContent = `Systemförslag till ${spel.spelform}`;
  $("lamna-in").href = `https://www.atg.se/spel/${spel.spelform}`;
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
    banner.textContent = "Det här är en exempelomgång. Den riktiga visas när pipelinen har hämtat veckans omgång.";
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
function ritaAvdelningar(lista, data, val, lasningar, oppna, interaktiv, kalla, utfallda) {
  const valPer = Object.fromEntries(val.map((v) => [v.avd, new Set(v.nr)]));
  const optAvd = avdelningarFor(data, kalla);
  const skrallar = kalla === "skrall" ? skrallchanser(optAvd) : {};
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
    const utfalld = utfallda.has(a.avd);
    const id = `avd-${interaktiv ? "k" : "r"}-${a.avd}`;
    const hast = (nr) => a.hastar.find((h) => h.nr === nr);
    const valdaSorterade = [...valda].sort((x, y) => x - y);
    const brickor = valdaSorterade.map((nr) => el("span", {
      class: ["bricka", last.has(nr) && "last", skrall === nr && "skrall", vinnare.has(nr) && "vann"].filter(Boolean).join(" "),
      title: hast(nr)?.namn,
    }, el("b", { text: nr }), valda.size === 1 ? ` ${hast(nr)?.namn ?? ""}` : null));
    const vinnartext = avgjord && !traff
      ? el("span", { class: "vann-annan", text: `Vann: ${[...vinnare].map((nr) => `${nr} ${hast(nr)?.namn ?? ""}`).join(", ")}` }) : null;
    return el("li", { class: "avd" + (avgjord && valda.size ? (traff ? " traff" : " miss") : "") + (utfalld ? " utfalld" : ""), "data-avd": a.avd },
      el("button", { type: "button", class: "avd-huvud", "data-avd-toggle": "1", "aria-expanded": String(utfalld), "aria-controls": id },
        el("span", { class: "avd-nr", "aria-label": `Avdelning ${a.avd}`, text: a.avd }),
        el("span", { class: "avd-text" },
          el("b", { text: `Lopp ${a.loppnr} · ${start}${start ? " · " : ""}${a.distans} m ${METOD[a.startmetod] || a.startmetod || ""}` }),
          el("span", { class: "brickor" }, ...brickor, vinnartext)),
        typ,
        el("span", { class: "pil", "aria-hidden": "true", text: "▾" })),
      utfalld ? el("div", { class: "avd-kropp", id },
        el("p", { class: "loppnamn", text: kortLoppnamn(a.namn), title: a.namn || "" }),
        a.kommentar ? el("p", { class: "ai-kommentar" }, el("span", { class: "ai-etikett", text: "AI" }), a.kommentar) : null,
        el("ul", { class: "hastar" }, ...a.hastar.map((h) => hastRad(a, h, andel[h.nr], valda.has(h.nr), last.has(h.nr),
          vinnare.has(h.nr), oppna.has(`${a.avd}-${h.nr}`), interaktiv, { skrall: skrall === h.nr, experter: experter(a, h) })))) : null);
  }));
}

/** Knappen "Fäll ut alla / Fäll ihop alla" för en avdelningslista. */
function fallKnapp(knapp, utfallda, rita, antal) {
  const uppdateraText = () => { knapp.textContent = utfallda.size === antal ? "Fäll ihop alla" : "Fäll ut alla"; };
  knapp.addEventListener("click", () => {
    const alla = utfallda.size === antal;
    utfallda.clear();
    if (!alla) for (let i = 1; i <= antal; i++) utfallda.add(i);
    rita();
  });
  return uppdateraText;
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

// ---------- utrustning och form (Hästkoll) ----------

const SKOR = { "false,false": "barfota runt", "false,true": "barfota fram", "true,false": "barfota bak", "true,true": "skor runt" };
const skorText = (u) => (u && u.skor_fram != null ? SKOR[`${Boolean(u.skor_fram)},${Boolean(u.skor_bak)}`] : null);
/** "1-1-2-1g-1": senaste starten först, g = galopp, d = diskad, 0 = oplacerad. */
const formText = (tid) => (tid || []).map((t) => (t.diskad ? "d" : t.plac ?? "?") + (t.galopp ? "g" : "")).join("-");
const kuskbyte = (h) => Boolean(h.tidigare?.[0]?.kusk && h.kusk && h.tidigare[0].kusk !== h.kusk);
const dagarSedan = (h, a) => (h.tidigare?.[0] && a.starttid
  ? Math.round((new Date(a.starttid) - new Date(h.tidigare[0].datum)) / 86_400_000) : null);

/** Korta markeringar i hästraden för det som ändrats sedan förra starten. */
function andringar(h) {
  const u = h.utrustning || {};
  const ut = [];
  if (u.skor_andrad) ut.push(skorText(u)?.startsWith("barfota") ? `${skorText(u)} ny` : "skobyte");
  if (u.vagn_andrad) ut.push("vagnbyte");
  if (kuskbyte(h)) ut.push("ny kusk");
  if (h.hastkoll?.bedomning === 1) ut.push("AI ↑");
  if (h.hastkoll?.bedomning === -1) ut.push("AI ↓");
  return ut;
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
    h.tidigare?.length ? `form ${formText(h.tidigare)}` : null,
    h.placering != null && !struken ? (h.placering ? `${h.placering}:a` : "oplac.") : null].filter(Boolean).join(" · ");
  return el("li", { class: klass, "data-nr": h.nr },
    el("div", { class: "hast-rad" },
      el("button", { type: "button", class: "hast-info", "data-detalj": "1", "aria-expanded": String(oppen), "aria-controls": id },
        el("span", { class: "startnr", text: h.nr }),
        el("span", { class: "namnblock" },
          el("span", { class: "hastnamn" }, h.namn, extra.skrall && !struken ? el("span", { class: "skrall-mark", text: " SKRÄLL" }) : null,
            vann ? el("span", { class: "vinnar-mark", text: " ✓ vann" }) : null),
          el("span", { class: "kusk" }, struken ? "Struken" : undertext,
            ...(struken ? [] : andringar(h).map((t) => el("span", { class: "andring", text: t })))))),
      el("button", {
        type: "button", class: "valruta", "data-las": interaktiv ? "1" : null, disabled: struken || !interaktiv || null,
        "aria-pressed": interaktiv ? String(last) : null,
        "aria-label": `${h.namn}: streck ${procent(h.streck)} %, chans ${procent(andel?.chans)} %${vald ? ", med i systemet" : ""}${last ? ", låst" : ""}`,
      },
        last ? el("span", { class: "las", "aria-hidden": "true", text: "🔒" }) : null,
        varde ? el("span", { class: "prick", "aria-hidden": "true" }) : null,
        el("span", { class: "del" }, el("b", { text: procent(h.streck) }), el("small", { text: "streck" })),
        el("span", { class: "del" }, el("b", { text: struken ? "–" : procent(andel?.chans) }), el("small", { text: "chans" })))),
    oppen ? detaljer(h, andel, id, exp, a) : null);
}

const kortDag = new Intl.DateTimeFormat("sv-SE", { day: "numeric", month: "short" });
const HASTKOLL = { 1: "Bättre än resultaten", 0: "Som resultaten", "-1": "Sämre än resultaten" };

function detaljer(h, andel, id, exp, a) {
  const u = h.utrustning;
  const dagar = dagarSedan(h, a);
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
    ["Skor", u && skorText(u) ? skorText(u) + (u.skor_andrad ? " – ändrat sedan förra starten" : "") : null],
    ["Vagn", u?.vagn ? u.vagn + (u.vagn_andrad ? " – ny sedan förra starten" : "") : null],
    ["Senaste starter", h.tidigare?.length ? `${formText(h.tidigare)} (senaste först)` : null],
    ["Hästkoll (AI, test)", h.hastkoll ? `${HASTKOLL[h.hastkoll.bedomning]}${h.hastkoll.motivering ? ` – ${h.hastkoll.motivering}` : ""}` : null],
    ["Senast", dagar != null ? `${dagar} dagar sedan${kuskbyte(h) ? ` · kördes då av ${h.tidigare[0].kusk}` : ""}` : null],
    ["Experter", exp ? (exp.namn.length ? `${exp.antal} av ${exp.totalt}: ${exp.namn.join(", ")}` : `ingen av ${exp.totalt}`) : null],
  ].filter(([, v]) => v);
  const v = andel ? andel.chans - andel.streck : null;
  return el("div", { class: "detaljer", id },
    el("dl", {}, ...rader.flatMap(([k, val]) => [el("dt", { text: k }), el("dd", { text: val })])),
    h.tidigare?.length ? el("ul", { class: "tidigare" }, ...h.tidigare.map((t) => el("li", {},
      el("b", { text: t.diskad ? "d" : t.plac ? `${t.plac}:a` : t.plac === 0 ? "0" : "–" }),
      ` ${kortDag.format(new Date(t.datum))} ${t.bana ?? ""}` + (t.galopp ? " · galopp" : "") +
        (t.odds ? ` · odds ${decimal(t.odds)}` : "") + (t.kusk ? ` · ${t.kusk}` : "")))) : null,
    v != null && !h.struken ? el("p", {
      text: v >= VARDE_GRANS ? `Understreckad: chansen är ${Math.round(v * 100)} procentenheter högre än strecken.`
        : v <= -VARDE_GRANS ? `Överstreckad: strecken är ${Math.round(-v * 100)} procentenheter högre än chansen.`
          : "Strecken och chansen är ungefär lika.",
    }) : null);
}

let fallText = () => {};
let rFallText = () => {};

function klickKupong(e) {
  const huvud = e.target.closest("[data-avd-toggle]");
  if (huvud) {
    const avd = Number(huvud.closest(".avd").dataset.avd);
    state.utfallda.has(avd) ? state.utfallda.delete(avd) : state.utfallda.add(avd);
    uppdatera();
    return;
  }
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
    byggBudgetknappar($("r-budgetknappar"), () => state.rBudget, (b) => { state.rBudget = b; renderaRattning(); },
      spelFor(state.senaste).radpris);
    rFallText = fallKnapp($("r-fall-alla"), state.rUtfallda, renderaRattning, spelFor(state.senaste).antal_avd);
    $("r-avdelningar").addEventListener("click", (e) => {
      const huvud = e.target.closest("[data-avd-toggle]");
      if (huvud) {
        const avd = Number(huvud.closest(".avd").dataset.avd);
        state.rUtfallda.has(avd) ? state.rUtfallda.delete(avd) : state.rUtfallda.add(avd);
        renderaRattning();
        return;
      }
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
  $("r-rubrik").textContent = `${spelFor(d).spelform} · ${o.bana}`;
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
  ritaAvdelningar($("r-avdelningar"), d, res.val, {}, state.rOppna, false, state.kalla, state.rUtfallda);
  rFallText();
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
    const val = $("bt-period");
    val.replaceChildren(...Object.entries(PERIODER).map(([k, p]) => el("option", { value: k, text: p.namn })));
    val.value = state.btPeriod;
    val.addEventListener("change", () => { state.btPeriod = val.value; renderaBacktest(); });
  }
  renderaBacktest();
}

function renderaBacktest() {
  const box = $("backtest-innehall");
  if (!state.historik.omgangar.length) {
    box.replaceChildren(el("p", { class: "dampad", text: "Ingen historik ännu." }));
    return;
  }
  const historik = { omgangar: state.historik.omgangar.filter((o) => iPeriod(o, state.btPeriod)) };
  const serier = Object.keys(KALLOR).map((k, i) => {
    const spel = backtesta(historik, state.btBudget, k);
    return { k, namn: KALLOR[k].namn, spel, sum: sammanstall(spel), farg: `var(--serie-${i + 1})` };
  });
  const [m] = serier;
  if (!m.spel.length) {
    box.replaceChildren(el("p", { class: "dampad", style: "margin-top:12px",
      text: "Inga avgjorda omgångar i den här perioden än. Den första räknas när lördagens omgång är avgjord." }));
    return;
  }
  const exp = serier.find((s) => s.k === "experter");
  const forsta = m.spel[0]?.datum;
  box.replaceChildren(
    el("div", { class: "r-stort" }, ...serier.map((s) => el("div", {},
      el("span", {}, el("i", { class: "nyckel", style: `background:${s.farg}` }), s.namn),
      s.spel.length ? el("b", { class: s.sum.netto >= 0 ? "plus" : "minus", text: plusKr(s.sum.netto) }) : el("b", { class: "dampad", text: "–" }),
      el("span", { text: s.spel.length
        ? `${kr(s.sum.insats)} in · ${kr(s.sum.tillbaka)} tillbaka · ${Math.round(s.sum.aterbetalning * 100)} % återbetalning`
          + (s.spel.length < m.spel.length ? ` · ${s.spel.length} omgångar` : "")
        : "Inga avgjorda omgångar med expertsystem än" })))),
    diagram(serier.filter((s) => s.spel.length)),
    el("div", { class: "tabell-scroll" }, el("table", { class: "stat-tabell", style: "margin-top:12px" },
      el("thead", {}, el("tr", {}, el("th", { text: "" }),
        ...["Alla rätt", "1 fel", "2 fel", "3 fel"].map((t) => el("th", { class: "tal", text: t })),
        el("th", { class: "tal", text: "Med vinst" }))),
      el("tbody", {}, ...serier.map((s) => el("tr", {}, el("td", { text: s.namn }),
        ...[0, 1, 2, 3].map((k) => el("td", { class: "tal", text: s.spel.length ? s.sum.fordelning[k] : "–" })),
        el("td", { class: "tal", text: s.spel.length ? `${s.sum.medVinst} av ${s.sum.omgangar}` : "–" })))))),
    el("h2", { class: "kort-rubrik", style: "margin-top:18px", text: "Omgång för omgång (Oddsen)" }),
    el("div", { class: "tabell-scroll" }, el("table", { class: "stat-tabell" },
      el("thead", {}, el("tr", {}, el("th", { text: "Datum" }), el("th", { text: "Bana" }), el("th", { class: "tal", text: "Rätt" }),
        el("th", { class: "tal", text: "Tillbaka" }), el("th", { class: "tal", text: "Saldo" }))),
      el("tbody", {}, ...[...m.spel].reverse().map((s) => el("tr", { class: s.vinst > 0 ? "har-vinst" : "" },
        el("td", { text: s.datum }), el("td", { text: s.bana }), el("td", { class: "tal", text: s.ratt }),
        el("td", { class: "tal", text: s.vinst ? kr(s.vinst) : "–" }),
        el("td", { class: "tal", text: plusKr(s.saldo) })))))),
    exp.spel.length < m.spel.length ? el("p", { class: "bt-not", text: "Experterna räknas bara för omgångar där experternas " +
      "system sparades, alltså sedan 14 oktober 2026 (ATG raderar kupongerna efter loppet). Jämför därför Experterna med de " +
      "andra under \"Sedan premiären\"." }) : null,
    el("p", { class: "bt-not", text: `${m.sum.omgangar} omgångar sedan ${forsta}. Chanserna i backtestet är räknade med vikter som bara sett ` +
      "lopp före omgångens månad, och utan vinnarodds (de finns inte sparade från före spelstopp i historiken). " +
      "Utdelningen per rad är ordinarie (utan Boost). Ett fåtal stora vinster avgör mycket, så läs resultatet som en riktning, inte en garanti." }),
  );
}

function diagram(serier) {
  const B = 640, H = 220, P = { v: 56, h: 8, t: 10, b: 22 };
  const datum = [...new Set(serier.flatMap((s) => s.spel.map((x) => x.datum + x.id)))].sort();
  const pos = Object.fromEntries(datum.map((d, i) => [d, i]));
  const n = datum.length;
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
    add("polyline", { class: "linje", stroke: s.farg, points: s.spel.map((p) => `${x(pos[p.datum + p.id])},${y(p.saldo)}`).join(" ") });
  }
  const forst = serier[0].spel[0], sist = serier[0].spel.at(-1);
  if (forst) add("text", { class: "axel", x: P.v, y: H - 6 }, forst.datum);
  if (sist) add("text", { class: "axel", x: B - P.h, y: H - 6, "text-anchor": "end" }, sist.datum);
  return el("div", { class: "bt-diagram" }, svg);
}

// ---------- om ----------

const driftFmt = new Intl.DateTimeFormat("sv-SE", { timeZone: TZ, weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
const timmarSedan = (iso) => (Date.now() - new Date(iso).getTime()) / 3_600_000;

/** Driftstatus på om-sidan: en rad per del, grön/orange/röd. */
function renderaDrift(d) {
  const rader = [];
  const rad = (niva, rubrik, text) => rader.push(el("li", { class: `drift-${niva}` },
    el("span", { class: "drift-ikon", "aria-hidden": "true", text: { ok: "✓", varning: "!", fel: "✕", info: "–" }[niva] }),
    el("div", {}, el("b", { text: rubrik }),
      el("span", { class: "sr-only", text: { ok: " (fungerar)", varning: " (varning)", fel: " (fel)", info: "" }[niva] }),
      el("p", { text }))));
  const nar = (iso) => driftFmt.format(new Date(iso));
  const drift = d.drift || {};

  // Schemat kör minst tre gånger om dagen, så mer än 14 timmar betyder att något stannat.
  const h = timmarSedan(d.uppdaterad);
  rad(h > 14 ? "fel" : "ok", "Senaste uppdatering",
    `${nar(d.uppdaterad)}${h > 14 ? " – längre sedan än schemat säger. Pipelinen kan ha stannat." : ""}`);

  const atg = drift.atg;
  rad(!atg ? "info" : atg.ok ? "ok" : "fel", "ATG: startlista och streck",
    !atg ? "Ingen körning registrerad än." : atg.ok ? `Hämtades ${nar(atg.tid)}.` : `Misslyckades ${nar(atg.tid)}: ${atg.fel}`);

  const medOdds = d.avdelningar.filter((a) => a.hastar.some((x) => x.odds)).length;
  const timmarKvar = (new Date(d.omgang.spelstopp).getTime() - Date.now()) / 3_600_000;
  rad(medOdds ? "ok" : "info", "Vinnarodds", medOdds ? `Finns för ${medOdds} av 8 avdelningar och vägs in i chansen.`
    : timmarKvar > 0 ? "Kommer på tävlingsdagen, när vinnarpoolen har pengar. Tills dess bygger chansen på strecken."
      : "Inga vinnarodds sparades före spelstopp.");

  const exp = drift.experter;
  const system = d.experter || [];
  rad(exp && !exp.ok ? "fel" : system.length ? "ok" : "info", "Experternas system",
    exp && !exp.ok ? `Hämtningen misslyckades ${nar(exp.tid)}: ${exp.fel}`
      : system.length ? `${system.length} system: ${system.map((e) => e.namn).join(", ")}.`
        : `Inga än – Fem tippar ${spelFor(d).spelform} publiceras oftast måndag eller tisdag.`);

  const ai = drift.ai;
  if (!ai) {
    rad("info", "AI", "Ingen körning med AI registrerad än.");
  } else if (!ai.konfigurerad) {
    rad("fel", "AI", `Inte igång: ${ai.orsak}.`);
  } else {
    const tot = ai.lyckade + ai.misslyckade;
    const modeller = Object.entries(ai.modeller || {}).map(([m, n]) => `${m} ${n}`).join(", ");
    rad(ai.lyckade === 0 ? "fel" : ai.misslyckade || ai.stoppad ? "varning" : "ok", "AI",
      `${ai.lyckade} av ${tot} anrop lyckades ${nar(ai.tid)}${modeller ? ` (${modeller})` : ""}.` +
      (ai.stoppad ? ` Avbröts: ${ai.stoppad} – resten tas vid nästa körning.` : "") +
      (ai.lyckade === 0 ? " Googles AI svarade inte – försöker igen vid nästa körning." : ""));
  }

  const komm = d.avdelningar.filter((a) => a.kommentar).length;
  rad(komm === 8 ? "ok" : komm ? "varning" : "info", "AI-kommentarer", `${komm} av 8 avdelningar har en kommentar.`);

  const vantar = drift.vantar_resultat || [];
  const senast = drift.senast_avgjord;
  rad(vantar.length ? "varning" : senast ? "ok" : "info", "Resultat och utdelning",
    (senast ? `Senast avgjord: ${senast.bana} ${senast.datum}.` : "Ingen avgjord omgång än.") +
    (vantar.length ? ` ${vantar.length} omgång väntar fortfarande på resultat.` : ""));

  $("drift").replaceChildren(...rader);
}

/** Kandidater som följs men inte vägs in än (statistik.KANDIDATER). */
function kandidatrader(kandidater) {
  if (!kandidater) return [];
  const rader = Object.values(kandidater).map((k) => {
    const delar = Object.entries(k.per_spelform || {}).map(([f, u]) =>
      `${f}: ${u.forbattring >= 0 ? "+" : "−"}${decimal(Math.abs(u.forbattring), 4)} ± ${decimal(u.standardfel, 4)} (${u.lopp} lopp)`);
    const lage = k.uppfyllt ? "uppfyller kravet och kan vägas in" : !k.lopp ? "samlar data" : "inte säkerställd än";
    return el("li", {}, el("b", { text: k.namn }), ` – ${lage}${delar.length ? `. ${delar.join(", ")}` : ""}.`);
  });
  return [el("p", { text: "Under test (vägs in först när de slår nuvarande modell med mer än två standardfel i både V75 och V85, " +
    "walk-forward):" }), el("ul", {}, ...rader)];
}

function renderaOmStatistik() {
  const s = state.data?.statistik;
  if (!s || !s.lopp) return;
  const bra = s.forbattring > 2 * s.standardfel;
  $("om-statistik").replaceChildren(
    el("p", { text: `Utvärdering på ${s.lopp.toLocaleString("sv-SE")} lopp, där varje månad bedömts med vikter som bara sett ` +
      `tidigare lopp: strecken gav vinnaren i snitt logloss ${decimal(s.logloss_streck, 3)}, Oddsen ${decimal(s.logloss_modell, 3)} ` +
      `(lägre är bättre). Favoriten vann ${Math.round(s.favorit_vann * 100)} % av loppen.` }),
    ...Object.entries(s.per_spelform || {}).map(([form, u]) => el("p", { text: `${form} (${u.lopp.toLocaleString("sv-SE")} lopp): ` +
      (u.forbattring > 2 * u.standardfel ? `Oddsen är tydligt bättre än strecken (${decimal(u.logloss_modell, 3)} mot ${decimal(u.logloss_streck, 3)}).`
        : `ingen säker skillnad mot strecken (${decimal(u.logloss_modell, 3)} mot ${decimal(u.logloss_streck, 3)}).`) })),
    !s.per_spelform ? el("p", { text: bra ? "Skillnaden är tydlig." : "Skillnaden är liten och inte säkerställd än." }) : null,
    ...kandidatrader(s.kandidater),
    s.vikter ? el("p", { class: "dampad", text: `Aktuella vikter: a = ${decimal(s.vikter.log_streck + (s.vikter.log_streck_v85 || 0), 2)} i V85` +
      ` och ${decimal(s.vikter.log_streck, 2)} i V75` +
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
