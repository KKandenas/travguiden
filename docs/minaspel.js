// Mina spel: system som användaren sparat ("Jag spelade det här") och deras rättning. Allt ligger i webbläsarens
// localStorage – inget konto och ingen server. Raderna sparas som de var (inte förslaget), eftersom strecken och
// därmed förslaget ändras fram till spelstopp. Rättningen använder senaste.json för förra omgången och
// historik.json för äldre omgångar.

import { ratta, vinst } from "./optimizer.js?v=20261103g";

export const NYCKEL = "travguiden-mina-spel";
export const MAX_SPEL = 500;

/** Ett sparat spel ur kupongens optimering. val: [{avd, nr: [...]}]. */
export function nyttSpel(data, kalla, kallnamn, budget, res, nu = new Date()) {
  return {
    id: `${data.omgang.id}:${nu.getTime()}`,
    omgang: data.omgang.id, datum: data.omgang.datum, bana: data.omgang.bana, spelform: data.omgang.spelform,
    kalla, kallnamn, budget, rader: res.rader, kostnad: res.kostnad,
    val: res.val.map((v) => ({ avd: v.avd, nr: [...v.nr].sort((a, b) => a - b) })),
    sparad: nu.toISOString(),
  };
}

const samma = (a, b) => a.omgang === b.omgang && JSON.stringify(a.val) === JSON.stringify(b.val);

/** Lägg till ett spel; ett likadant system för samma omgång ersätts. De äldsta tas bort över MAX_SPEL. */
export function laggTill(lista, spel) {
  return [...lista.filter((s) => !samma(s, spel)), spel].slice(-MAX_SPEL);
}

export const harSparat = (lista, spel) => lista.some((s) => samma(s, spel));

/** Resultatet för en omgång ur senaste.json (omgang_data). Struken häst ersätts av favoriten (mest streckad). */
export function resultatFranOmgang(d) {
  if (!d?.avdelningar?.some((a) => a.vinnare?.length)) return null;
  return {
    vinnare: Object.fromEntries(d.avdelningar.map((a) => [a.avd, a.vinnare || []])),
    ersattare: Object.fromEntries(d.avdelningar.map((a) => {
      const kvar = a.hastar.filter((h) => !h.struken && h.streck != null);
      const fav = kvar.reduce((b, h) => (!b || h.streck > b.streck ? h : b), null);
      return [a.avd, { struken: a.hastar.filter((h) => h.struken).map((h) => h.nr), favorit: fav?.nr }];
    })),
    utdelning: Object.fromEntries(Object.entries(d.utdelning || {}).map(([k, u]) => [k, u.kr])),
  };
}

/** Resultatet för en omgång ur historik.json (v = vinnare, s = strukna, f = favorit). */
export function resultatFranHistorik(o) {
  return {
    vinnare: Object.fromEntries(o.avd.map((a, i) => [i + 1, a.v || []])),
    ersattare: Object.fromEntries(o.avd.map((a, i) => [i + 1, { struken: a.s || [], favorit: a.f }])),
    utdelning: o.utdelning || {},
  };
}

/** {ratt, perRatt, tillbaka, netto} för ett sparat spel. */
export function rattaSpel(spel, resultat) {
  const r = ratta(spel.val, resultat.vinnare, resultat.ersattare);
  const tillbaka = vinst(r.perRatt, resultat.utdelning);
  return { ratt: r.ratt, perRatt: r.perRatt, tillbaka, netto: tillbaka - spel.kostnad };
}

/** Rätta alla spel som har ett resultat; resultat: {omgang-id: resultat}. Spel utan resultat väntar. */
export function sammanstall(lista, resultat) {
  const rattade = [], vantar = [];
  for (const s of lista) {
    if (resultat[s.omgang]) rattade.push({ ...s, ...rattaSpel(s, resultat[s.omgang]) });
    else vantar.push(s);
  }
  const insats = rattade.reduce((a, s) => a + s.kostnad, 0), tillbaka = rattade.reduce((a, s) => a + s.tillbaka, 0);
  return { rattade, vantar, insats, tillbaka, netto: tillbaka - insats, omgangar: new Set(rattade.map((s) => s.omgang)).size };
}
