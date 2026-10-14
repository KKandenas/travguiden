import { test } from "node:test";
import assert from "node:assert/strict";
import { backtesta, sammanstall, spelaOmgang } from "../../docs/backtest.js";

const avd = (v, f = 1, s = []) => ({ v, f, s, h: [[1, 0.5, 0.5], [2, 0.3, 0.3], [3, 0.2, 0.2]] });
const omg = (id, vinnare) => ({ id, datum: id, bana: "Solvalla", utdelning: { 5: 10, 6: 100, 7: 1000, 8: 100000 },
  avd: vinnare.map((v) => avd([v])) });

test("en omgång: favoriterna vinner och spiksystemet ger 8 rätt", () => {
  const s = spelaOmgang(omg("2026-01-01", [1, 1, 1, 1, 1, 1, 1, 1]), 50);
  assert.equal(s.ratt, 8);
  assert.ok(s.vinst >= 100000);
  assert.ok(s.insats <= 50);
});

test("saldot ackumuleras och sammanställningen stämmer", () => {
  const h = { omgangar: [omg("2026-01-01", [3, 3, 3, 3, 3, 3, 3, 3]), omg("2026-01-08", [1, 1, 1, 1, 1, 1, 1, 1])] };
  const spel = backtesta(h, 50);
  assert.equal(spel.length, 2);
  assert.equal(spel[1].saldo, spel[0].vinst - spel[0].insats + spel[1].vinst - spel[1].insats);
  const s = sammanstall(spel);
  assert.equal(s.omgangar, 2);
  assert.equal(s.netto, s.tillbaka - s.insats);
});

test("Experterna spelas bara på omgångar med expertsystem", () => {
  const utan = omg("2026-01-01", [1, 1, 1, 1, 1, 1, 1, 1]);
  const med = { ...omg("2026-01-08", [2, 2, 2, 2, 2, 2, 2, 2]) };
  med.avd = med.avd.map((a) => ({ ...a, h: [[1, 0.5, 0.5, 0.2], [2, 0.3, 0.3, 0.6], [3, 0.2, 0.2, 0.2]] }));
  const spel = backtesta({ omgangar: [utan, med] }, 50, "experter");
  assert.equal(spel.length, 1);
  assert.equal(spel[0].ratt, 8);          // experterna tror på nr 2 överallt
});

test("perioder: alla, sedan premiären och från 2026", async () => {
  const { iPeriod, PREMIAR } = await import("../../docs/backtest.js");
  const o = (datum) => ({ datum });
  assert.ok(iPeriod(o("2025-11-01"), "alla"));
  assert.ok(!iPeriod(o("2025-11-01"), "2026") && iPeriod(o("2026-01-03"), "2026"));
  assert.ok(!iPeriod(o("2026-10-10"), "premiar") && iPeriod(o(PREMIAR), "premiar"));
});

test("V75 i backtestet: 60 öre per rad och alla rätt = 7", () => {
  const v75 = { id: "V75_2026-11-28_5_5", datum: "2026-11-28", bana: "Solvalla", spelform: "V75", radpris: 0.6,
    utdelning: { 5: 10, 6: 100, 7: 50000 }, avd: [1, 1, 1, 1, 1, 1, 1].map((v) => avd([v])) };
  const s = spelaOmgang(v75, 120);
  assert.equal(s.ratt, 7);
  assert.ok(s.rader <= 200 && s.insats === Math.round(s.rader * 0.6 * 100) / 100);
  assert.equal(sammanstall([s]).fordelning[0], 1);    // 0 fel
});
