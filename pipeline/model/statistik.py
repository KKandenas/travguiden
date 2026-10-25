"""Skattning av modellvikterna och utvärdering mot strecken.

- Vikterna skattas på alla avgjorda lopp (V85 och, om de finns, äldre V75). Vinnaroddsen används bara i
  avdelning 1, där slutoddsen sattes i samma ögonblick som V85 stängde. I senare avdelningar är
  slutoddsen satta efter spelstopp och skulle läcka information.
- Walk-forward: för varje månad skattas vikter på data före månaden (när det finns minst MIN_LOPP lopp).
  Backtestet använder dem.
- Utvärderingen är också walk-forward: logloss för vinnaren per lopp, modell mot streck, på alla lopp som har
  walk-forward-vikter (V75 från 2023 och V85).
"""
from __future__ import annotations

import json
import logging
import math
import sqlite3
import statistics as st
from typing import Dict, List, Tuple

from ..tid import nu_utc
from . import data, modeller, sannolikhet

log = logging.getLogger(__name__)

MIN_LOPP = 150          # färre lopp än så före en månad: använd standardvikterna
MIN_EXPERTLOPP = 150    # avgjorda lopp med expertsystem innan experternas vikt skattas (ungefär 19 omgångar)

# Kandidater: egenskaper som följs men inte vägs in förrän de klarat kravet: walk-forward, på alla lopp sammantaget
# (V75 och V85), minst MIN_TESTLOPP testlopp och mer än KRAV_SE standardfel bättre än nuvarande modell – och inte
# tydligt sämre (mer än KRAV_SE standardfel) i någon spelform. Spelformerna skiljer sig bara i hur spelarna streckar,
# och det har nuvarande modell redan kalibrerat per spelform (beslut 25 oktober 2026). Klarar en kandidat kravet läggs
# den in som en ny modellversion – den nuvarande ändras aldrig.
#
# "fran": kandidater som hittats genom att leta i historiken avgörs bara på lopp efter det datumet. Walk-forward
# skyddar vikten mot framtiden, men inte idén – den valdes efter att ha sett facit. Historiken visas som bakgrund.
KANDIDATER = {
    "barfota_runt_ny": {"namn": "Barfota runt för första gången", "har": lambda l: l.get("har_hastinfo"),
                        "fran": "2026-10-17"},
    "formfalla": {"namn": "Formfällan: lågt streckad häst som vann senast eller vinner ofta i år",
                  "har": lambda l: l.get("har_hastinfo"), "fran": "2026-10-25"},
    "hastkoll": {"namn": "Hästkoll: AI:ns bedömning av de senaste loppen",
                 "har": lambda l: any(h.get("hastkoll") is not None for h in l["hastar"])},
}
MIN_KANDIDATLOPP = 100  # kandidatens egna lopp före en månad innan dess vikt kan skattas (en enda vikt)
MIN_TESTLOPP = 200
KRAV_SE = 2.0


def traningslopp(conn: sqlite3.Connection) -> List[dict]:
    ut = []
    for l in data.lopp(conn, bara_avgjorda=True):
        for h in l["hastar"]:
            h["vinnarodds"] = h["slutodds"] if l["avd"] == 1 else None
        ut.append(l)
    return ut


def _skatta(lopp: List[dict]) -> Dict[str, float]:
    return sannolikhet.skatta(lopp, modeller.EGENSKAPER, l2=2.0)


def _sammanfatta(bas: List[float], mod: List[float], traff: int) -> dict:
    if len(bas) < 2:
        return {"lopp": len(bas)}
    d = [b - m for b, m in zip(bas, mod)]
    return {
        "lopp": len(bas),
        "logloss_streck": round(st.mean(bas), 4), "logloss_modell": round(st.mean(mod), 4),
        "forbattring": round(st.mean(d), 4), "standardfel": round(st.stdev(d) / math.sqrt(len(d)), 4),
        "favorit_vann": round(traff / len(bas), 3),
    }


def utvardera(lopp: List[dict], per_manad: Dict[str, Dict[str, float]]) -> dict:
    """Walk-forward-utvärdering utan odds (som backtestet ser dem), på lopp vars månad har vikter.
    Totalt och per spelform."""
    per: Dict[str, Tuple[list, list, list]] = {}
    for l in lopp:
        if l["datum"][:7] not in per_manad:
            continue
        l = {**l, "hastar": [{**h, "vinnarodds": None} for h in l["hastar"]]}
        ps = sannolikhet.normalisera([h["streck"] for h in l["hastar"]])
        pm = sannolikhet.chanser(l, per_manad[l["datum"][:7]])
        vinn = [i for i, h in enumerate(l["hastar"]) if h["nr"] in l["vinnare"]]
        bas, mod, traff = per.setdefault(l["spelform"], ([], [], []))
        bas.append(-math.log(max(sum(ps[i] for i in vinn) / len(vinn), 1e-9)))
        mod.append(-math.log(max(sum(pm[i] for i in vinn) / len(vinn), 1e-9)))
        traff.append(max(range(len(ps)), key=ps.__getitem__) in vinn)
    alla = [sum((per[k][i] for k in per), []) for i in range(3)]
    return {**_sammanfatta(alla[0], alla[1], sum(alla[2])),
            "per_spelform": {k: _sammanfatta(b, m, sum(t)) for k, (b, m, t) in sorted(per.items())}}


def utvardera_kandidat(lopp: List[dict], egenskap: str, per_manad: Dict[str, Dict[str, float]],
                       fran: str = "") -> dict:
    """Walk-forward: för varje månad jämförs Oddsens vikter för månaden (skattade på alla tidigare lopp) med samma
    vikter plus kandidaten, vars vikt skattas på kandidatens tidigare lopp. Logloss för vinnaren på månadens lopp
    (utan odds, som i backtestet). Beslutet (uppfyllt) gäller bara lopp från och med `fran`."""
    per: Dict[str, List[float]] = {}
    hist: Dict[str, List[float]] = {}
    vikter = []
    for m in sorted({l["datum"][:7] for l in lopp}):
        fore = [l for l in lopp if l["datum"][:7] < m]
        if len(fore) < MIN_KANDIDATLOPP or m not in per_manad:
            continue
        utan = per_manad[m]
        med = sannolikhet.skatta(fore, [egenskap], l2=2.0, fast=utan)
        vikter.append(med[egenskap])
        test = [{**l, "hastar": [{**h, "vinnarodds": None} for h in l["hastar"]]} for l in lopp if l["datum"][:7] == m]
        for l, a, b in zip(test, sannolikhet.logloss(test, utan), sannolikhet.logloss(test, med)):
            hist.setdefault(l["spelform"], []).append(a - b)
            if l["datum"] >= fran:
                per.setdefault(l["spelform"], []).append(a - b)
    def summa(d):
        return {"lopp": len(d), "forbattring": round(st.mean(d), 4), "standardfel": round(st.stdev(d) / math.sqrt(len(d)), 4)}

    ut = {"lopp": len(lopp), "per_spelform": {form: summa(d) for form, d in sorted(per.items()) if len(d) >= 2}}
    alla = [x for d in per.values() for x in d]
    if len(alla) >= 2:
        ut["totalt"] = summa(alla)
    if fran:
        ut["fran"] = fran
        alla_hist = [x for d in hist.values() for x in d]
        if len(alla_hist) >= 2:
            ut["historik"] = summa(alla_hist)
    t = ut.get("totalt")
    ut["uppfyllt"] = bool(t and t["lopp"] >= MIN_TESTLOPP and t["forbattring"] > KRAV_SE * t["standardfel"]
                          and all(u["forbattring"] > -KRAV_SE * u["standardfel"] for u in ut["per_spelform"].values()))
    if vikter:
        ut["vikt"] = round(vikter[-1], 3)
    return ut


def kor(conn: sqlite3.Connection) -> dict:
    lopp = traningslopp(conn)
    if len(lopp) < MIN_LOPP:
        log.info("Statistik: bara %d avgjorda lopp – behåller standardvikterna", len(lopp))
        return {}
    manader = sorted({l["datum"][:7] for l in lopp})
    per_manad = {}
    for m in manader:
        fore = [l for l in lopp if l["datum"][:7] < m]
        if len(fore) >= MIN_LOPP:
            per_manad[m] = _skatta(fore)
    senaste = _skatta(lopp)
    utv = utvardera(lopp, per_manad)
    expertlopp = [l for l in lopp if any(h.get("expertandel") is not None for h in l["hastar"])]
    if len(expertlopp) >= MIN_EXPERTLOPP:
        ev = sannolikhet.skatta(expertlopp, modeller.EXPERTEGENSKAPER, l2=2.0)
        ev_manad = {}
        for m in manader:
            fore = [l for l in expertlopp if l["datum"][:7] < m]
            if len(fore) >= MIN_EXPERTLOPP:
                ev_manad[m] = sannolikhet.skatta(fore, modeller.EXPERTEGENSKAPER, l2=2.0)
        log.info("Statistik: expertvikter %s (%d lopp)", {k: round(v, 3) for k, v in ev.items()}, len(expertlopp))
        _spara(conn, f"vikter:{modeller.EXPERTMODELL}", {"senaste": ev, "per_manad": ev_manad})
    utv["expertlopp"] = len(expertlopp)
    kandidater = {}
    for namn, k in KANDIDATER.items():
        kl = [l for l in lopp if k["har"](l)]
        kandidater[namn] = {"namn": k["namn"],
                            **(utvardera_kandidat(kl, namn, per_manad, k.get("fran", "")) if kl else {"lopp": 0})}
        log.info("Statistik: kandidat %s: %s", namn, kandidater[namn])
    utv["kandidater"] = kandidater
    log.info("Statistik: vikter %s, utvärdering %s", {k: round(v, 3) for k, v in senaste.items()}, utv)
    _spara(conn, f"vikter:{modeller.AKTIV}", {"senaste": senaste, "per_manad": per_manad})
    _spara(conn, "statistik", {**utv, "vikter": senaste, "traningslopp": len(lopp),
                               "senast_avgjord": max(l["datum"] for l in lopp)})
    return utv


def _spara(conn, nyckel: str, varde) -> None:
    with conn:
        conn.execute("""INSERT INTO installningar (nyckel, varde, uppdaterad) VALUES (?, ?, ?)
                        ON CONFLICT(nyckel) DO UPDATE SET varde = excluded.varde, uppdaterad = excluded.uppdaterad""",
                     (nyckel, json.dumps(varde, ensure_ascii=False), nu_utc()))



def behover_traning(conn: sqlite3.Connection) -> bool:
    """Sant om en omgång har avgjorts sedan vikterna senast skattades."""
    r = conn.execute("SELECT varde FROM installningar WHERE nyckel = 'statistik'").fetchone()
    senast = conn.execute("SELECT MAX(datum) FROM omgangar WHERE avgjord = 1").fetchone()[0]
    if senast is None:
        return False
    return r is None or json.loads(r[0]).get("senast_avgjord", "") < senast
