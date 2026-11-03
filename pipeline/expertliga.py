"""Expertligan: experternas egna system rättade mot de riktiga utdelningarna.

Kupongerna sparas sedan premiären (17 oktober 2026). Varje system rättas för sig: bästa radens antal rätt, hur
många rader som gav varje vinstgrupp, vad systemet gav tillbaka och hur ofta spikarna höll. Återkommande serier
(TR Media, Fernlund, Åke Olsson – ett litet och ett stort system var) slås ihop under samma namn, och Fem tippar
får en samlad rad för alla gäster. Avdelningar som experten lämnat åt Harry Boy saknar val; sådana system rättas
bara på spikarna, eftersom slumpraderna inte är kända.
"""
from __future__ import annotations

import re
import sqlite3
from collections import defaultdict
from typing import Dict, List, Optional

from . import config

FEM_TIPPAR = "Fem tippar"
# Serier vars namn skrivs olika från vecka till vecka ("FERNLUNDS LILLA SYSTEMFÖRSLAG - V85 söndag")
SERIER = [("fernlund", "Patrik Fernlund"), ("olsson", "Åke Olsson"), ("tr media", "TR Media")]


def ligans_namn(namn: str) -> str:
    """"Åke Olssons Stora Systemförslag - V85 Lördag" -> "Åke Olsson · stora"; personnamn lämnas som de är."""
    liten = namn.lower()
    for nyckel, serie in SERIER:
        if nyckel in liten:
            storlek = "lilla" if "lilla" in liten else "stora" if "stora" in liten else None
            return f"{serie} · {storlek}" if storlek else serie
    return namn.strip()


def radfordelning(val: Dict[int, List[int]], vinnare: Dict[int, List[int]]) -> Dict[int, int]:
    """{antal rätt: antal rader}. Varje avdelning bidrar med (missar + träffar·x); produkten ger fördelningen."""
    poly = [1]
    for avd, nr in val.items():
        traff = sum(1 for n in nr if n in vinnare.get(avd, []))
        miss = len(nr) - traff
        ny = [0] * (len(poly) + 1)
        for k, c in enumerate(poly):
            ny[k] += c * miss
            ny[k + 1] += c * traff
        poly = ny
    return {k: c for k, c in enumerate(poly) if c}


def ratta_omgang(conn: sqlite3.Connection, omgang_id: str) -> List[dict]:
    """Varje expertsystem i en avgjord omgång: rätt, rader, insats, tillbaka, spikar."""
    o = conn.execute("SELECT * FROM omgangar WHERE id = ?", (omgang_id,)).fetchone()
    vinnare = {r["avd"]: [int(x) for x in r["vinnare"].split(",")] for r in conn.execute(
        "SELECT avd, vinnare FROM avdelningar WHERE omgang_id = ? AND vinnare IS NOT NULL AND vinnare != ''", (omgang_id,))}
    antal_avd = conn.execute("SELECT COUNT(*) FROM avdelningar WHERE omgang_id = ?", (omgang_id,)).fetchone()[0]
    if not o or not o["avgjord"] or len(vinnare) < antal_avd:
        return []
    kr = {r["ratt"]: r["kr"] for r in conn.execute("SELECT ratt, kr FROM utdelning WHERE omgang_id = ?", (omgang_id,))}
    radpris = config.radpris(o["spelform"], o["datum"])
    ut = []
    for s in conn.execute("SELECT * FROM expertsystem WHERE omgang_id = ? ORDER BY kalla DESC, namn", (omgang_id,)):
        val: Dict[int, List[int]] = defaultdict(list)
        for v in conn.execute("SELECT avd, nr FROM expertval WHERE system_id = ?", (s["id"],)):
            val[v["avd"]].append(v["nr"])
        spikar = [nr[0] for avd, nr in val.items() if len(nr) == 1]
        holl = sum(1 for avd, nr in val.items() if len(nr) == 1 and nr[0] in vinnare.get(avd, []))
        r = {"namn": s["namn"], "liga": ligans_namn(s["namn"]), "kalla": s["kalla"], "spikar": len(spikar), "holl": holl}
        if len(val) == antal_avd:              # komplett system: rätta raderna
            rader = 1
            for nr in val.values():
                rader *= len(nr)
            fordelning = radfordelning(val, vinnare)
            r.update(rader=rader, insats=round(rader * radpris, 2), ratt=max(fordelning),
                     tillbaka=round(sum(c * kr.get(k, 0) for k, c in fordelning.items()), 2))
        ut.append(r)
    return ut


def _summa(rader: List[dict], namn: str, kalla: str) -> dict:
    hela = [r for r in rader if "ratt" in r]
    insats, tillbaka = sum(r["insats"] for r in hela), sum(r["tillbaka"] for r in hela)
    return {
        "namn": namn, "kalla": kalla, "omgangar": len({r["omgang"] for r in rader}),
        "system": len(rader), "ratt_snitt": round(sum(r["ratt"] for r in hela) / len(hela), 2) if hela else None,
        "basta": max((r["ratt"] for r in hela), default=None),
        "spikar": sum(r["spikar"] for r in rader), "holl": sum(r["holl"] for r in rader),
        "insats": round(insats, 2), "tillbaka": round(tillbaka, 2),
    }


def liga(conn: sqlite3.Connection, senaste: Optional[str] = None) -> dict:
    """Ligan över alla avgjorda omgångar med expertsystem, och systemen i omgången `senaste`."""
    omgangar = [r[0] for r in conn.execute("""SELECT DISTINCT es.omgang_id FROM expertsystem es
                                              JOIN omgangar o ON o.id = es.omgang_id
                                              WHERE o.avgjord = 1 ORDER BY o.spelstopp""")]
    alla = []
    for o in omgangar:
        alla += [{**r, "omgang": o} for r in ratta_omgang(conn, o)]
    if not alla:
        return {}
    per_namn: Dict[str, List[dict]] = defaultdict(list)
    for r in alla:
        per_namn[r["liga"]].append(r)
    summor = [_summa(rs, n, rs[0]["kalla"]) for n, rs in per_namn.items()]
    aterbet = lambda d: (-(d["tillbaka"] / d["insats"]) if d["insats"] else 1, d["namn"])  # noqa: E731
    # Serierna och Fem tippar som helhet; gästerna i Fem tippar (oftast en omgång var) för sig
    deltagare = [d for d in summor if d["kalla"] != FEM_TIPPAR]
    fem = [r for r in alla if r["kalla"] == FEM_TIPPAR]
    if fem:
        deltagare.append(_summa(fem, f"{FEM_TIPPAR} – alla gäster", FEM_TIPPAR))
    return {
        "omgangar": len({r["omgang"] for r in alla}),
        "fran": conn.execute("SELECT datum FROM omgangar WHERE id = ?", (omgangar[0],)).fetchone()[0],
        "deltagare": sorted(deltagare, key=aterbet),
        "gaster": sorted((d for d in summor if d["kalla"] == FEM_TIPPAR), key=aterbet),
        "senaste": [{k: v for k, v in r.items() if k != "omgang"} for r in alla if r["omgang"] == senaste],
    }
