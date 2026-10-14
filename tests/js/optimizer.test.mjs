import { test } from "node:test";
import assert from "node:assert/strict";
import { bastaPerAntal, deltagare, optimera, ratta, sammanfattning, vinst } from "../../docs/optimizer.js";

/** 8 avdelningar med 6 hästar där chans = streck utom där annat anges. */
function omgang(andra = {}) {
  return Array.from({ length: 8 }, (_, i) => ({
    avd: i + 1,
    hastar: (andra[i + 1] || [0.4, 0.2, 0.15, 0.12, 0.08, 0.05].map((s) => [s, s])).map(([chans, streck], j) => ({
      nr: j + 1, chans, streck, struken: false,
    })),
  }));
}

test("antalet rader håller sig inom budgeten och kostar 50 öre", () => {
  for (const budget of [50, 100, 200, 500, 1000]) {
    const r = optimera(omgang(), budget);
    assert.ok(r.ok);
    assert.equal(r.rader, r.val.reduce((a, v) => a * v.nr.length, 1));
    assert.ok(r.rader <= budget * 2);
    assert.equal(r.kostnad, r.rader * 0.5);
    assert.ok(r.rader > budget * 2 * 0.6, `${budget} kr ska utnyttjas: ${r.rader} rader`);
  }
});

test("utan värde (chans = streck) väljs favoriterna först", () => {
  const r = optimera(omgang(), 50, {}, 0);
  for (const v of r.val) assert.ok(v.nr.includes(1));
});

test("en spik väljs där favoriten är stor", () => {
  const stor = [[0.85, 0.85], [0.05, 0.05], [0.04, 0.04], [0.03, 0.03], [0.02, 0.02], [0.01, 0.01]];
  const r = optimera(omgang({ 3: stor }), 100);
  assert.deepEqual(r.val[2].nr, [1]);
});

test("understreckad häst tas med före en lika trolig överstreckad", () => {
  const avd = [[0.4, 0.4], [0.2, 0.35], [0.2, 0.05], [0.1, 0.1], [0.05, 0.05], [0.05, 0.05]];
  const b = bastaPerAntal({ hastar: avd.map(([chans, streck], j) => ({ nr: j + 1, chans, streck })) }, [], 0.3);
  const tva = b.find((x) => x.k === 2);
  assert.deepEqual(tva.nr, [1, 3]);
});

test("låsta hästar kommer alltid med", () => {
  const r = optimera(omgang(), 100, { 2: [6], 5: [4, 5] });
  assert.ok(r.val[1].nr.includes(6));
  assert.ok(r.val[4].nr.includes(4) && r.val[4].nr.includes(5));
  assert.deepEqual(r.val[1].last, [6]);
});

test("för många låsningar ger begripligt fel", () => {
  const r = optimera(omgang(), 50, { 1: [1, 2, 3], 2: [1, 2, 3], 3: [1, 2, 3], 4: [1, 2, 3, 4, 5] });
  assert.equal(r.ok, false);
  assert.match(r.fel, /minst 135 rader/);
});

test("strukna hästar väljs aldrig och chansen räknas om bland de övriga", () => {
  const o = omgang();
  o[0].hastar[0].struken = true;
  const r = optimera(o, 1000);
  assert.ok(!r.val[0].nr.includes(1));
  const d = deltagare(o[0]);
  assert.equal(d.length, 5);
  assert.ok(Math.abs(d.reduce((a, h) => a + h.chans, 0) - 1) < 1e-9);
});

test("rättning: rader per antal rätt och vinst", () => {
  const val = [[1, 2], [1], [1], [1], [1], [1], [1], [1, 2, 3]].map((nr, i) => ({ avd: i + 1, nr }));
  const vinnare = { 1: [2], 2: [1], 3: [1], 4: [1], 5: [1], 6: [1], 7: [5], 8: [3] };
  const r = ratta(val, vinnare);
  assert.equal(r.ratt, 7);
  // avd 1: 1 träff av 2, avd 8: 1 av 3 → 1 rad med 7 rätt, 1+2 rader med 6, 2 med 5
  assert.deepEqual(r.perRatt, { 5: 2, 6: 3, 7: 1 });
  assert.equal(vinst(r.perRatt, { 5: 10, 6: 100, 7: 1000, 8: 50000 }), 1320);
});

test("rättning: struken vald häst ersätts av favoriten", () => {
  const val = Array.from({ length: 8 }, (_, i) => ({ avd: i + 1, nr: [4] }));
  const vinnare = Object.fromEntries(val.map((v) => [v.avd, [4]]));
  vinnare[1] = [1];
  const r = ratta(val, vinnare, { 1: { struken: [4], favorit: 1 } });
  assert.equal(r.ratt, 8);
});

test("dött lopp: båda vinnarna ger rätt", () => {
  const val = Array.from({ length: 8 }, (_, i) => ({ avd: i + 1, nr: [1, 2] }));
  const vinnare = Object.fromEntries(val.map((v) => [v.avd, [1]]));
  vinnare[3] = [1, 2];
  const r = ratta(val, vinnare);
  assert.equal(r.perRatt[8], 2);
});

test("sammanfattning", () => {
  assert.equal(sammanfattning({ rader: 96, kostnad: 48, val: [{ nr: [1] }, { nr: [1, 2] }] }), "96 rader · 48 kr — 1 spik");
});
