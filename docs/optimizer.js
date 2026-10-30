// Radoptimering för V85 och V75. Ren logik utan DOM – körs både i webbläsaren och i `node --test`.
//
// Ett system väljer en eller flera hästar i varje avdelning (8 i V85, 7 i V75). Antalet rader är
// produkten av antalet hästar per avdelning, och varje rad kostar radpriset (50 öre; nya V75 från
// 28 november 2026: 60 öre). Radpris och antal avdelningar kommer från omgången (omgang.json → "spel").
//
// Poäng per avdelning med hästarna S (summeras över avdelningarna):
//   (1 − λ) · log(Σ chans)          → sannolikheten att avdelningen sitter
// +      λ · log(Σ chans / streck)  → förväntad utdelning: understreckade hästar betalar mer
// Produkten över avdelningarna är (träffchans)^(1−λ) · (förväntad utdelning)^λ.
//
// Inom en avdelning prövas alla delmängder (högst 2^16), så för varje antal hästar k hittas den
// bästa uppsättningen. Över avdelningarna väljer dynamisk programmering på antalet rader den
// kombination som ger högst total poäng utan att gå över budgeten.

export const RADPRIS = 0.5;                     // kr per rad, om omgången inte anger annat
export const BUDGETAR = [25, 50, 100, 120, 150, 200, 300, 500];   // kr; 120 kr = 240 rader i V85 (som Fem tippar)
export const LAMBDA = 0.3;                      // risknivå, se README (backtest)
export const VARDE_GRANS = 0.02;                // orange prick från 2 procentenheter understreckad

// Skrällchans: en häst som inte är favorit, har högst SKRALL_MAX_STRECK av strecken, minst SKRALL_MIN_CHANS
// chans och tydligt högre chans än streck (kvot minst SKRALL_MIN_KVOT). Bästa kandidaten per avdelning,
// högst SKRALL_MAX per omgång. Förslaget Skrällchansen kräver 1–2 av dem i systemet. Chansen är Experternas
// när expertsystemen finns, annars Oddsens. Se README (backtest och analys av skrällarna).
export const SKRALL = { maxStreck: 0.15, minChans: 0.05, minKvot: 1.15, max: 3 };
export const skrallarForBudget = (kr) => (kr <= 200 ? 1 : 2);

const MIN_STRECK = 0.002;                       // skydd mot division med ~0 för nästan ostreckade hästar
const MAX_HASTAR = 16;

/** Hästar som kan väljas (inte strukna), med chans och streck som andelar som summerar till 1. */
export function deltagare(avd) {
  const kvar = avd.hastar.filter((h) => !h.struken);
  const sc = kvar.reduce((a, h) => a + (h.chans || 0), 0) || 1;
  const ss = kvar.reduce((a, h) => a + (h.streck || 0), 0);
  return kvar.map((h) => ({
    nr: h.nr,
    chans: Math.max((h.chans || 0) / sc, 1e-6),
    streck: Math.max(ss > 0 ? (h.streck || 0) / ss : (h.chans || 0) / sc, MIN_STRECK),
  }));
}

/** Omgångens skrällchanser: {avd: {avd, nr, chans, streck, kvot}}. */
export function skrallchanser(avdelningar, regler = SKRALL) {
  const kandidater = [];
  for (const a of avdelningar) {
    const h = deltagare(a);
    if (h.length < 3) continue;
    const favorit = h.reduce((b, x) => (x.chans > b.chans ? x : b));
    let bast = null;
    for (const x of h) {
      if (x === favorit || x.streck > regler.maxStreck || x.chans < regler.minChans) continue;
      const kvot = x.chans / x.streck;
      if (kvot >= regler.minKvot && (!bast || kvot > bast.kvot)) bast = { avd: a.avd, nr: x.nr, chans: x.chans, streck: x.streck, kvot };
    }
    if (bast) kandidater.push(bast);
  }
  kandidater.sort((a, b) => b.kvot - a.kvot);
  return Object.fromEntries(kandidater.slice(0, regler.max).map((k) => [k.avd, k]));
}

/** Krav för Skrällchansen: {avd: nr} för de bästa skrällarna (1 eller 2 beroende på insats).
 *  Avdelningar där användaren låst något får inget krav – låsningen gäller. */
export function skrallKrav(avdelningar, budget, lasningar = {}, regler = SKRALL) {
  return Object.fromEntries(Object.values(skrallchanser(avdelningar, regler))
    .filter((s) => !(lasningar[s.avd] || []).length)
    .slice(0, skrallarForBudget(budget))
    .map((s) => [s.avd, s.nr]));
}

export function poang(chansSumma, kvotSumma, lambda = LAMBDA) {
  return (1 - lambda) * Math.log(chansSumma) + lambda * Math.log(kvotSumma);
}

/**
 * Bästa uppsättning hästar för varje antal k i en avdelning.
 * @returns [{k, nr: [..], poang, chans}] för de k som är möjliga (låsta hästar måste vara med)
 */
export function bastaPerAntal(avd, lasta = [], lambda = LAMBDA) {
  const h = deltagare(avd).sort((a, b) => b.chans - a.chans).slice(0, MAX_HASTAR);
  const n = h.length;
  const lasMask = h.reduce((m, x, i) => (lasta.includes(x.nr) ? m | (1 << i) : m), 0);
  const P = new Float64Array(1 << n), V = new Float64Array(1 << n), K = new Uint8Array(1 << n);
  const bast = new Array(n + 1).fill(null);
  for (let mask = 1; mask < 1 << n; mask++) {
    const low = mask & -mask, i = 31 - Math.clz32(low), rest = mask ^ low;
    P[mask] = P[rest] + h[i].chans;
    V[mask] = V[rest] + h[i].chans / h[i].streck;
    K[mask] = K[rest] + 1;
    if ((mask & lasMask) !== lasMask) continue;
    const p = poang(P[mask], V[mask], lambda);
    const k = K[mask];
    if (!bast[k] || p > bast[k].poang) bast[k] = { k, mask, poang: p, chans: P[mask] };
  }
  return bast.filter(Boolean).map((b) => ({
    k: b.k, poang: b.poang, chans: b.chans,
    nr: h.filter((_, i) => b.mask & (1 << i)).map((x) => x.nr).sort((a, b2) => a - b2),
  }));
}

/**
 * @param avdelningar [{avd, hastar: [{nr, chans, streck, struken}]}]
 * @param budget      kr, t.ex. 200
 * @param lasningar   {avd: [nr, ...]} – hästar som användaren låst (måste vara med)
 * @param krav        {avd: nr} – häst som måste vara med (Skrällchansen)
 * @param radpris     kr per rad (V85 0,5; nya V75 0,6)
 * @param cache       valfri Map: avdelningarnas alternativ (det tunga steget) återanvänds mellan insatser
 * @returns {ok: true, val: [{avd, nr: [..], last: [..], skrall}], rader, kostnad, chans}
 *        | {ok: false, fel: "text"}
 */
export function optimera(avdelningar, budget, lasningar = {}, lambda = LAMBDA, krav = {}, radpris = RADPRIS, cache = null) {
  if (avdelningar.length < 2) return { ok: false, fel: "Omgången saknar avdelningar." };
  const maxRader = Math.floor(budget / radpris + 1e-9);
  if (maxRader < 1) return { ok: false, fel: "Budgeten räcker inte till en rad." };

  const maste = (a) => [...(lasningar[a.avd] || []), ...(krav[a.avd] != null ? [krav[a.avd]] : [])];
  const alternativ = avdelningar.map((a) => {
    if (!cache) return bastaPerAntal(a, maste(a), lambda);
    const nyckel = `${a.avd}|${maste(a).join(",")}|${lambda}`;
    if (!cache.has(nyckel)) cache.set(nyckel, bastaPerAntal(a, maste(a), lambda));
    return cache.get(nyckel);
  });
  const tom = alternativ.findIndex((alt) => !alt.length);
  if (tom >= 0) return { ok: false, fel: `Avdelning ${avdelningar[tom].avd} saknar hästar att välja.` };

  // tillstand: rader -> {poang, val: [index per avdelning]}
  let tillstand = new Map([[1, { poang: 0, val: [] }]]);
  for (const alt of alternativ) {
    const nytt = new Map();
    for (const [rader, s] of tillstand) {
      for (let j = 0; j < alt.length; j++) {
        const r = rader * alt[j].k;
        if (r > maxRader) break;           // alt är sorterad på k
        const p = s.poang + alt[j].poang;
        const fore = nytt.get(r);
        if (!fore || p > fore.poang) nytt.set(r, { poang: p, val: [...s.val, j] });
      }
    }
    tillstand = nytt;
  }
  if (!tillstand.size) return { ok: false, fel: lasningsfel(avdelningar, lasningar, maxRader, radpris) };

  let bast = null, bastRader = 0;
  for (const [rader, s] of tillstand) if (!bast || s.poang > bast.poang) { bast = s; bastRader = rader; }
  let chans = 1;
  const val = avdelningar.map((a, i) => {
    const v = alternativ[i][bast.val[i]];
    chans *= v.chans;
    return { avd: a.avd, nr: v.nr, last: (lasningar[a.avd] || []).filter((n) => v.nr.includes(n)),
      skrall: krav[a.avd] ?? null };
  });
  return { ok: true, val, rader: bastRader, kostnad: Math.round(bastRader * radpris * 100) / 100, chans };
}

function lasningsfel(avdelningar, lasningar, maxRader, radpris) {
  const kravd = avdelningar.reduce((a, x) => a * Math.max(1, (lasningar[x.avd] || []).length), 1);
  return kravd > maxRader
    ? `Dina låsningar kräver minst ${kravd} rader (${kronor(Math.round(kravd * radpris * 100) / 100)}). Välj en större budget eller lås upp något.`
    : "Dina låsningar går inte ihop med den här budgeten. Välj en annan budget eller lås upp något.";
}

export const kronor = (x) => `${Number.isInteger(x) ? x : x.toFixed(2).replace(".", ",")} kr`;

/** "6 spikar · 2 gardering · 192 rader · 96 kr" */
export function sammanfattning(res) {
  const spikar = res.val.filter((v) => v.nr.length === 1).length;
  const delar = [];
  if (spikar) delar.push(`${spikar} ${spikar === 1 ? "spik" : "spikar"}`);
  const rader = res.rader === 1 ? "1 rad" : `${res.rader} rader`;
  return `${rader} · ${kronor(res.kostnad)}${delar.length ? " — " + delar.join(" · ") : ""}`;
}

/**
 * Rättning av ett system. Strukna hästar man valt ersätts av avdelningens mest streckade häst (ATG:s
 * regel när ingen reserv angetts).
 * @param val       [{avd, nr: [..]}]
 * @param vinnare   {avd: [nr, ...]} (flera vid dött lopp)
 * @param ersattare {avd: {struken: [..], favorit: nr}} – valfritt
 * @returns {ratt: bästa antal rätt, perRatt: {antal rätt: antal rader}}
 */
export function ratta(val, vinnare, ersattare = {}) {
  let poly = [1];                       // poly[k] = antal rader med k rätt
  let ratt = 0;
  for (const v of val) {
    const e = ersattare[v.avd];
    const valda = new Set(v.nr.map((n) => (e && e.struken.includes(n) ? e.favorit : n)));
    const radPerHast = v.nr.length / valda.size;   // två valda strukna -> samma favorit, raderna finns kvar
    const vann = vinnare[v.avd] || [];
    const traff = [...valda].filter((n) => vann.includes(n)).length * radPerHast;
    const miss = v.nr.length - traff;
    if (traff) ratt++;
    const ny = new Array(poly.length + 1).fill(0);
    poly.forEach((c, k) => { ny[k] += c * miss; ny[k + 1] += c * traff; });
    poly = ny;
  }
  const perRatt = {};
  poly.forEach((c, k) => { if (c) perRatt[k] = c; });
  return { ratt, perRatt };
}

/** Vinst i kr för systemet: summan av utdelningen för varje rad (utdelning: {antal rätt: kr per rad}). */
export function vinst(perRatt, utdelning) {
  return Object.entries(perRatt).reduce((a, [k, n]) => a + n * (utdelning[k] || 0), 0);
}
