// Backtest: om du spelat Travguidens förslag varje omgång. Ren logik utan DOM.
//
// historik.json: {omgangar: [{id, datum, bana, utdelning: {antal rätt: kr}, avd: [{v, f, s, h}]}]}
//   v = vinnare (startnummer), f = mest streckade häst (ersätter strukna), s = strukna,
//   h = [[nr, chans, streck], ...] för hästarna som startade.
// Chanserna är walk-forward: räknade med vikter som bara sett lopp före omgångens månad.

import { LAMBDA, optimera, ratta, vinst } from "./optimizer.js?v=20261014b";

// Förslag att jämföra: Travguiden (modellens chans) och Strecken (folkets bedömning som chans).
export const KALLOR = {
  modell: { namn: "Travguiden", chans: (h) => h[1] },
  streck: { namn: "Strecken", chans: (h) => h[2] },
};

export function avdelningarFran(omg, kalla = "modell") {
  const c = KALLOR[kalla].chans;
  return omg.avd.map((a, i) => ({
    avd: i + 1,
    hastar: a.h.map((h) => ({ nr: h[0], chans: c(h), streck: h[2] })),
  }));
}

/** En omgång: systemet, antal rätt, insats och vinst. */
export function spelaOmgang(omg, budget, kalla = "modell", lambda = LAMBDA) {
  const res = optimera(avdelningarFran(omg, kalla), budget, {}, lambda);
  if (!res.ok) return null;
  const vinnare = Object.fromEntries(omg.avd.map((a, i) => [i + 1, a.v]));
  const ersattare = Object.fromEntries(omg.avd.map((a, i) => [i + 1, { struken: a.s, favorit: a.f }]));
  const r = ratta(res.val, vinnare, ersattare);
  return { id: omg.id, datum: omg.datum, bana: omg.bana, rader: res.rader, insats: res.kostnad,
    ratt: r.ratt, perRatt: r.perRatt, vinst: vinst(r.perRatt, omg.utdelning), val: res.val };
}

/** Alla omgångar i ordning, med löpande saldo. */
export function backtesta(historik, budget, kalla = "modell", lambda = LAMBDA) {
  let saldo = 0;
  const ut = [];
  for (const omg of historik.omgangar) {
    const s = spelaOmgang(omg, budget, kalla, lambda);
    if (!s) continue;
    saldo += s.vinst - s.insats;
    ut.push({ ...s, saldo });
  }
  return ut;
}

export function sammanstall(spel) {
  const insats = spel.reduce((a, s) => a + s.insats, 0);
  const tillbaka = spel.reduce((a, s) => a + s.vinst, 0);
  const fordelning = { 8: 0, 7: 0, 6: 0, 5: 0 };
  for (const s of spel) if (s.ratt >= 5) fordelning[s.ratt]++;
  return { omgangar: spel.length, insats, tillbaka, netto: tillbaka - insats,
    aterbetalning: insats ? tillbaka / insats : 0, fordelning,
    medVinst: spel.filter((s) => s.vinst > 0).length };
}
