// Radoptimering för V85. Ren logik utan DOM – körs både i webbläsaren och i `node --test`.
//
// Ett system väljer en eller flera hästar i var och en av de 8 avdelningarna. Antalet rader är
// produkten av antalet hästar per avdelning, och varje rad kostar RADPRIS kr.
//
// Poäng per avdelning med hästarna S (summeras över avdelningarna):
//   (1 − λ) · log(Σ chans)          → sannolikheten att avdelningen sitter
// +      λ · log(Σ chans / streck)  → förväntad utdelning: understreckade hästar betalar mer
// Produkten över avdelningarna är (träffchans)^(1−λ) · (förväntad utdelning)^λ.
//
// Inom en avdelning prövas alla delmängder (högst 2^16), så för varje antal hästar k hittas den
// bästa uppsättningen. Över avdelningarna väljer dynamisk programmering på antalet rader den
// kombination som ger högst total poäng utan att gå över budgeten.

export const RADPRIS = 0.5;                     // kr per rad
export const BUDGETAR = [50, 100, 200, 300, 500, 1000];   // kr
export const LAMBDA = 0.3;                      // risknivå, se README (backtest)
export const VARDE_GRANS = 0.02;                // orange prick från 2 procentenheter understreckad
export const ANTAL_AVD = 8;

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
 * @returns {ok: true, val: [{avd, nr: [..], last: [..]}], rader, kostnad, chans}
 *        | {ok: false, fel: "text"}
 */
export function optimera(avdelningar, budget, lasningar = {}, lambda = LAMBDA) {
  if (avdelningar.length !== ANTAL_AVD) return { ok: false, fel: `Omgången har ${avdelningar.length} avdelningar, väntade ${ANTAL_AVD}.` };
  const maxRader = Math.floor(budget / RADPRIS + 1e-9);
  if (maxRader < 1) return { ok: false, fel: "Budgeten räcker inte till en rad." };

  const alternativ = avdelningar.map((a) => bastaPerAntal(a, lasningar[a.avd] || [], lambda));
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
  if (!tillstand.size) return { ok: false, fel: lasningsfel(avdelningar, lasningar, maxRader) };

  let bast = null, bastRader = 0;
  for (const [rader, s] of tillstand) if (!bast || s.poang > bast.poang) { bast = s; bastRader = rader; }
  let chans = 1;
  const val = avdelningar.map((a, i) => {
    const v = alternativ[i][bast.val[i]];
    chans *= v.chans;
    return { avd: a.avd, nr: v.nr, last: (lasningar[a.avd] || []).filter((n) => v.nr.includes(n)) };
  });
  return { ok: true, val, rader: bastRader, kostnad: bastRader * RADPRIS, chans };
}

function lasningsfel(avdelningar, lasningar, maxRader) {
  const kravd = avdelningar.reduce((a, x) => a * Math.max(1, (lasningar[x.avd] || []).length), 1);
  return kravd > maxRader
    ? `Dina låsningar kräver minst ${kravd} rader (${kronor(kravd * RADPRIS)}). Välj en större budget eller lås upp något.`
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
