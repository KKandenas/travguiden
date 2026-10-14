"""Skattning av modellvikterna och utvärdering mot strecken.

- Vikterna skattas på alla avgjorda lopp (V85 och, om de finns, äldre V75). Vinnaroddsen används bara i
  avdelning 1, där slutoddsen sattes i samma ögonblick som V85 stängde. I senare avdelningar är
  slutoddsen satta efter spelstopp och skulle läcka information.
- Walk-forward: för varje månad med V85 skattas vikter på data före månaden. Backtestet använder dem.
- Utvärderingen är också walk-forward: logloss för vinnaren per V85-lopp, modell mot streck.
"""
from __future__ import annotations

import json
import logging
import math
import sqlite3
import statistics as st
from typing import Dict, List

from ..tid import nu_utc
from . import data, modeller, sannolikhet

log = logging.getLogger(__name__)

MIN_LOPP = 150          # färre lopp än så före en månad: använd standardvikterna


def traningslopp(conn: sqlite3.Connection) -> List[dict]:
    ut = []
    for l in data.lopp(conn, bara_avgjorda=True):
        for h in l["hastar"]:
            h["vinnarodds"] = h["slutodds"] if l["avd"] == 1 else None
        ut.append(l)
    return ut


def _skatta(lopp: List[dict]) -> Dict[str, float]:
    return sannolikhet.skatta(lopp, modeller.EGENSKAPER, l2=2.0)


def utvardera(lopp: List[dict], per_manad: Dict[str, Dict[str, float]]) -> dict:
    """Walk-forward-utvärdering på V85-lopp utan odds (som backtestet ser dem)."""
    bas, mod, traff_s, traff_m = [], [], 0, 0
    for l in lopp:
        if l["spelform"] != "V85":
            continue
        l = {**l, "hastar": [{**h, "vinnarodds": None} for h in l["hastar"]]}
        w = per_manad.get(l["datum"][:7], modeller.STANDARDVIKTER)
        ps = sannolikhet.normalisera([h["streck"] for h in l["hastar"]])
        pm = sannolikhet.chanser(l, w)
        vinn = [i for i, h in enumerate(l["hastar"]) if h["nr"] in l["vinnare"]]
        bas.append(-math.log(max(sum(ps[i] for i in vinn) / len(vinn), 1e-9)))
        mod.append(-math.log(max(sum(pm[i] for i in vinn) / len(vinn), 1e-9)))
        traff_s += max(range(len(ps)), key=ps.__getitem__) in vinn
        traff_m += max(range(len(pm)), key=pm.__getitem__) in vinn
    if len(bas) < 2:
        return {"lopp": len(bas)}
    d = [b - m for b, m in zip(bas, mod)]
    return {
        "lopp": len(bas),
        "logloss_streck": round(st.mean(bas), 4), "logloss_modell": round(st.mean(mod), 4),
        "forbattring": round(st.mean(d), 4), "standardfel": round(st.stdev(d) / math.sqrt(len(d)), 4),
        "favorit_vann": round(traff_s / len(bas), 3),
    }


def kor(conn: sqlite3.Connection) -> dict:
    lopp = traningslopp(conn)
    if len(lopp) < MIN_LOPP:
        log.info("Statistik: bara %d avgjorda lopp – behåller standardvikterna", len(lopp))
        return {}
    manader = sorted({l["datum"][:7] for l in lopp if l["spelform"] == "V85"})
    per_manad = {}
    for m in manader:
        fore = [l for l in lopp if l["datum"][:7] < m]
        if len(fore) >= MIN_LOPP:
            per_manad[m] = _skatta(fore)
    senaste = _skatta(lopp)
    utv = utvardera(lopp, per_manad)
    log.info("Statistik: vikter %s, utvärdering %s", {k: round(v, 3) for k, v in senaste.items()}, utv)
    with conn:
        for nyckel, varde in ((f"vikter:{modeller.AKTIV}", {"senaste": senaste, "per_manad": per_manad}),
                              ("statistik", {**utv, "vikter": senaste, "traningslopp": len(lopp),
                                             "senast_avgjord": max(l["datum"] for l in lopp)})):
            conn.execute("""INSERT INTO installningar (nyckel, varde, uppdaterad) VALUES (?, ?, ?)
                            ON CONFLICT(nyckel) DO UPDATE SET varde = excluded.varde, uppdaterad = excluded.uppdaterad""",
                         (nyckel, json.dumps(varde, ensure_ascii=False), nu_utc()))
    return utv


def behover_traning(conn: sqlite3.Connection) -> bool:
    """Sant om en omgång har avgjorts sedan vikterna senast skattades."""
    r = conn.execute("SELECT varde FROM installningar WHERE nyckel = 'statistik'").fetchone()
    senast = conn.execute("SELECT MAX(datum) FROM omgangar WHERE avgjord = 1").fetchone()[0]
    if senast is None:
        return False
    return r is None or json.loads(r[0]).get("senast_avgjord", "") < senast
