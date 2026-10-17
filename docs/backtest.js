// Backtest: om du spelat Travguidens förslag varje omgång. Ren logik utan DOM.
//
// historik.json: {omgangar: [{id, datum, bana, spelform, radpris, utdelning: {antal rätt: kr}, avd: [{v, f, s, h}]}]}
//   V75 har 7 avdelningar och utdelning för 7–5 rätt, V85 8 avdelningar och 8–5 rätt.
//   v = vinnare (startnummer), f = mest streckade häst (ersätter strukna), s = strukna,
//   h = [[nr, chans, streck], ...] för hästarna som startade.
// Chanserna är walk-forward: räknade med vikter som bara sett lopp före omgångens månad.

import { LAMBDA, RADPRIS, SKRALL, optimera, ratta, skrallKrav, vinst } from "./optimizer.js?v=20261017a";

// Förslagen i appen plus Strecken (folkets bedömning som chans) som jämförelse. Experterna finns bara för
// omgångar där experternas system sparades (h har då ett fjärde värde).
export const KALLOR = {
  modell: { namn: "Oddsen", chans: (h) => h[1] },
  experter: { namn: "Experterna", chans: (h) => h[3], kraver: (omg) => omg.avd.every((a) => a.h.every((h) => h.length > 3)) },
  skrall: { namn: "Skrällchansen", chans: (h) => h[3] ?? h[1], skrall: true },   // Experternas chans där den finns
  streck: { namn: "Strecken", chans: (h) => h[2] },
};

// Perioder i backtestet. Premiären = första omgången efter att Travguiden publicerades (14 oktober 2026).
export const PREMIAR = "2026-10-17";
export const PERIODER = {
  alla: { namn: "Alla omgångar (V75 och V85 sedan 2023)", fran: "" },
  premiar: { namn: "Sedan premiären (17 oktober 2026)", fran: PREMIAR },
  v85: { namn: "Bara V85 (25 oktober 2025 – )", fran: "2025-10-25", spelform: "V85" },
  2026: { namn: "Från 2026", fran: "2026-01-01" },
  2025: { namn: "Från 2025", fran: "2025-01-01" },
  2024: { namn: "Från 2024", fran: "2024-01-01" },
};
export const iPeriod = (omg, period) => {
  const p = PERIODER[period] || PERIODER.alla;
  return omg.datum >= p.fran && (!p.spelform || (omg.spelform || "V85") === p.spelform);
};

export function avdelningarFran(omg, kalla = "modell") {
  const c = KALLOR[kalla].chans;
  return omg.avd.map((a, i) => ({
    avd: i + 1,
    hastar: a.h.map((h) => ({ nr: h[0], chans: c(h), streck: h[2] })),
  }));
}

/** En omgång: systemet, antal rätt, insats och vinst. */
export function spelaOmgang(omg, budget, kalla = "modell", lambda = LAMBDA, regler = SKRALL) {
  if (KALLOR[kalla].kraver && !KALLOR[kalla].kraver(omg)) return null;
  const avd = avdelningarFran(omg, kalla);
  const krav = KALLOR[kalla].skrall ? skrallKrav(avd, budget, {}, regler) : {};
  const res = optimera(avd, budget, {}, lambda, krav, omg.radpris ?? RADPRIS);
  if (!res.ok) return null;
  const vinnare = Object.fromEntries(omg.avd.map((a, i) => [i + 1, a.v]));
  const ersattare = Object.fromEntries(omg.avd.map((a, i) => [i + 1, { struken: a.s, favorit: a.f }]));
  const r = ratta(res.val, vinnare, ersattare);
  return { id: omg.id, datum: omg.datum, bana: omg.bana, spelform: omg.spelform || "V85", avdelningar: omg.avd.length,
    rader: res.rader, insats: res.kostnad,
    ratt: r.ratt, perRatt: r.perRatt, vinst: vinst(r.perRatt, omg.utdelning), val: res.val };
}

/** Alla omgångar i ordning, med löpande saldo. */
export function backtesta(historik, budget, kalla = "modell", lambda = LAMBDA, regler = SKRALL) {
  let saldo = 0;
  const ut = [];
  for (const omg of historik.omgangar) {
    const s = spelaOmgang(omg, budget, kalla, lambda, regler);
    if (!s) continue;
    saldo += s.vinst - s.insats;
    ut.push({ ...s, saldo });
  }
  return ut;
}

export function sammanstall(spel) {
  const insats = spel.reduce((a, s) => a + s.insats, 0);
  const tillbaka = spel.reduce((a, s) => a + s.vinst, 0);
  // Räknas som antal fel, så att V75 (7 avdelningar) och V85 (8) kan läggas ihop: 0 fel = alla rätt.
  const fordelning = { 0: 0, 1: 0, 2: 0, 3: 0 };
  for (const s of spel) {
    const fel = s.avdelningar - s.ratt;
    if (fel <= 3) fordelning[fel]++;
  }
  return { omgangar: spel.length, insats, tillbaka, netto: tillbaka - insats,
    aterbetalning: insats ? tillbaka / insats : 0, fordelning,
    medVinst: spel.filter((s) => s.vinst > 0).length };
}
