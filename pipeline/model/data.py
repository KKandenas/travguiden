"""Läser lopp ur databasen i det format modellen använder."""
from __future__ import annotations

import sqlite3
from typing import List, Optional

_SENASTE_STRECK = "(SELECT andel FROM streck WHERE start_id = s.id ORDER BY tidpunkt DESC LIMIT 1)"
_SENASTE_ODDS = "(SELECT odds FROM vinnarodds WHERE start_id = s.id ORDER BY tidpunkt DESC LIMIT 1)"


def lopp(conn: sqlite3.Connection, villkor: str = "1", params=(), bara_avgjorda: bool = False,
         spelform: Optional[str] = None) -> List[dict]:
    """Lopp med hästar som inte är strukna. Odds i senare avdelningar av en avgjord omgång är slutodds
    efter spelstopp – därför används vinnaroddsen i träningen bara i avdelning 1 (se statistik.py)."""
    sql = f"""
        SELECT a.id AS avd_id, a.omgang_id, a.avd, a.distans AS lopp_distans, a.startmetod, a.vinnare,
               o.datum, o.spelform,
               s.id AS start_id, s.nr, s.spar, s.distans, s.kusk_segerproc, s.livs_starter, s.livs_segrar, s.slutodds,
               {_SENASTE_STRECK} AS streck, {_SENASTE_ODDS} AS vinnarodds
        FROM avdelningar a JOIN omgangar o ON o.id = a.omgang_id JOIN starter s ON s.avdelning_id = a.id
        WHERE s.struken = 0 AND ({villkor})
          {"AND o.avgjord = 1 AND a.vinnare IS NOT NULL" if bara_avgjorda else ""}
          {"AND o.spelform = ?" if spelform else ""}
        ORDER BY o.spelstopp, a.avd, s.nr"""
    rader = conn.execute(sql, (*params, *([spelform] if spelform else []))).fetchall()
    ut: dict = {}
    for r in rader:
        l = ut.get(r["avd_id"])
        if l is None:
            l = ut[r["avd_id"]] = {
                "avd_id": r["avd_id"], "omgang_id": r["omgang_id"], "avd": r["avd"], "datum": r["datum"],
                "spelform": r["spelform"], "distans": r["lopp_distans"], "startmetod": r["startmetod"],
                "vinnare": [int(x) for x in (r["vinnare"] or "").split(",") if x], "hastar": [],
            }
        l["hastar"].append({
            "start_id": r["start_id"], "nr": r["nr"], "spar": r["spar"], "distans": r["distans"],
            "kusk_segerproc": r["kusk_segerproc"], "livs_starter": r["livs_starter"], "livs_segrar": r["livs_segrar"],
            "streck": r["streck"], "vinnarodds": r["vinnarodds"], "slutodds": r["slutodds"],
        })
    _expertandelar(conn, ut)
    # Lopp där strecken saknas helt (t.ex. trasig ögonblicksbild) går inte att modellera
    return [l for l in ut.values() if len(l["hastar"]) >= 2 and all(h["streck"] is not None for h in l["hastar"])]


def _expertandelar(conn: sqlite3.Connection, lopp: dict) -> None:
    """Sätt h["expertandel"] och h["experter"] (antal system med hästen) för lopp där expertsystem finns."""
    omgangar = {l["omgang_id"] for l in lopp.values()}
    if not omgangar:
        return
    rader = conn.execute(f"""SELECT es.omgang_id, ev.system_id, ev.avd, ev.nr FROM expertval ev
                             JOIN expertsystem es ON es.id = ev.system_id
                             WHERE es.omgang_id IN ({",".join("?" * len(omgangar))})""", tuple(omgangar)).fetchall()
    system: dict = {}           # omgang -> system -> avd -> [nr]
    for r in rader:
        system.setdefault(r["omgang_id"], {}).setdefault(r["system_id"], {}).setdefault(r["avd"], []).append(r["nr"])
    for l in lopp.values():
        alla = system.get(l["omgang_id"])
        if not alla:
            continue
        for h in l["hastar"]:
            val = [s.get(l["avd"], []) for s in alla.values()]
            h["expertandel"] = sum(1 / len(v) for v in val if h["nr"] in v) / len(alla)
            h["experter"] = sum(1 for v in val if h["nr"] in v)
