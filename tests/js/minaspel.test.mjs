import { test } from "node:test";
import assert from "node:assert/strict";
import { harSparat, laggTill, nyttSpel, rattaSpel, resultatFranHistorik, resultatFranOmgang, sammanstall } from "../../docs/minaspel.js";

const DATA = { omgang: { id: "V85_2026-11-07_9_5", datum: "2026-11-07", bana: "Bergsåker", spelform: "V85" } };
const RES = { rader: 4, kostnad: 2, val: [{ avd: 1, nr: [3, 1] }, { avd: 2, nr: [5, 7] }, { avd: 3, nr: [2] }] };

test("sparat spel får raderna sorterade och samma system ersätts", () => {
  const a = nyttSpel(DATA, "modell", "Oddsen", 200, RES, new Date("2026-11-07T10:00:00Z"));
  assert.deepEqual(a.val[0], { avd: 1, nr: [1, 3] });
  assert.equal(a.kostnad, 2);
  const b = nyttSpel(DATA, "modell", "Oddsen", 200, RES, new Date("2026-11-07T11:00:00Z"));
  const lista = laggTill(laggTill([], a), b);
  assert.equal(lista.length, 1);
  assert.equal(lista[0].sparad, "2026-11-07T11:00:00.000Z");
  assert.ok(harSparat(lista, a));
  const annat = nyttSpel(DATA, "skrall", "Skrällchansen", 200, { ...RES, val: [{ avd: 1, nr: [2] }] });
  assert.equal(laggTill(lista, annat).length, 2);
});

test("rättning: rader per antal rätt, ersättare för struken häst och utdelning", () => {
  const spel = nyttSpel(DATA, "modell", "Oddsen", 200, RES);
  const res = {
    vinnare: { 1: [1], 2: [9], 3: [4] },
    ersattare: { 3: { struken: [2], favorit: 4 } },        // vald häst 2 struken, favoriten 4 vann
    utdelning: { 2: 10, 3: 100 },
  };
  const r = rattaSpel(spel, res);
  assert.equal(r.ratt, 2);
  assert.deepEqual(r.perRatt, { 1: 2, 2: 2 });            // (1 + x) · 2 · x
  assert.equal(r.tillbaka, 20);
  assert.equal(r.netto, 18);
});

test("resultat ur senaste.json och historik.json ger samma rättning", () => {
  const senaste = {
    avdelningar: [
      { avd: 1, vinnare: [1], hastar: [{ nr: 1, streck: 0.5 }, { nr: 2, streck: 0.5 }] },
      { avd: 2, vinnare: [7], hastar: [{ nr: 5, streck: 0.6 }, { nr: 6, struken: true }, { nr: 7, streck: 0.4 }] },
    ],
    utdelning: { 2: { kr: 50, antal: 3 } },
  };
  const historik = { utdelning: { 2: 50 }, avd: [{ v: [1], s: [], f: 1 }, { v: [7], s: [6], f: 5 }] };
  const spel = { kostnad: 1, val: [{ avd: 1, nr: [1] }, { avd: 2, nr: [6, 7] }] };
  const a = rattaSpel(spel, resultatFranOmgang(senaste)), b = rattaSpel(spel, resultatFranHistorik(historik));
  assert.deepEqual(a, b);
  assert.equal(a.ratt, 2);
  assert.equal(resultatFranOmgang({ avdelningar: [{ avd: 1, hastar: [] }] }), null);   // inte avgjord
});

test("sammanställning: rättade och väntande spel", () => {
  const avgjord = { ...nyttSpel(DATA, "modell", "Oddsen", 200, RES), omgang: "A" };
  const kommande = { ...nyttSpel(DATA, "modell", "Oddsen", 200, RES), omgang: "B" };
  const s = sammanstall([avgjord, kommande], { A: { vinnare: { 1: [1], 2: [5], 3: [2] }, ersattare: {}, utdelning: { 3: 100 } } });
  assert.equal(s.rattade.length, 1);
  assert.equal(s.vantar.length, 1);
  assert.equal(s.tillbaka, 100);
  assert.equal(s.netto, 98);
  assert.equal(s.omgangar, 1);
});
