"""Vinnaroddsen före spelstopp och sena pengar.

Sedan 24 oktober 2026 sparas vinnarodds i alla avdelningar under tävlingsdagen (tidigare bara slutodds i avdelning 1).
Två frågor, som kan besvaras när ett åttatal omgångar finns (färdplanen: december–januari):

1. Vinnaroddsens vikt: träffar Oddsen bättre med förhandsodds än utan, och vilken vikt b ger datan? b skattas ovanpå
   Oddsens övriga vikter (fasta), med felmarginal genom omsampling av omgångarna.
2. Sena pengar: hur mycket ändrades hästens chans enligt vinnarpoolen från första till sista bilden före spelstopp?
   Vinner hästar vars odds faller kraftigt oftare än Oddsen räknade med (som redan tagit in de sista oddsen)?

    python -m pipeline oddsanalys [--fran 2026-10-24]
"""
from __future__ import annotations

import math
import random
import sqlite3
import statistics as st
from collections import defaultdict
from typing import Dict, List

from . import data, modeller, sannolikhet

FRAN = "2026-10-24"
MIN_MINUTER = 30           # första och sista bilden måste skilja minst så mycket för att räknas som "sena pengar"
GRUPPER = [("kraftigt oddsfall (chansen +30 %)", 1.3, 99), ("oddsfall (+10–30 %)", 1.1, 1.3),
           ("oförändrat (±10 %)", 0.9, 1.1), ("oddsstigning (−10–30 %)", 0.7, 0.9), ("kraftig oddsstigning (−30 %)", 0, 0.7)]


def _bilder(conn: sqlite3.Connection, fran: str) -> Dict[int, List[tuple]]:
    """start_id -> [(tidpunkt, odds)] före spelstopp, i tidsordning."""
    ut: Dict[int, List[tuple]] = defaultdict(list)
    for r in conn.execute("""SELECT v.start_id, v.tidpunkt, v.odds FROM vinnarodds v JOIN starter s ON s.id = v.start_id
                             JOIN avdelningar a ON a.id = s.avdelning_id JOIN omgangar o ON o.id = a.omgang_id
                             WHERE o.datum >= ? AND v.tidpunkt <= o.spelstopp ORDER BY v.tidpunkt""", (fran,)):
        ut[r[0]].append((r[1], r[2]))
    return ut


def _minuter(a: str, b: str) -> float:
    from datetime import datetime
    t = lambda s: datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ")  # noqa: E731
    return (t(b) - t(a)).total_seconds() / 60


def lopp_med_odds(conn: sqlite3.Connection, fran: str = FRAN) -> List[dict]:
    """Avgjorda lopp där de flesta hästar har vinnarodds före spelstopp. Varje häst får vinnarodds (sista bilden),
    oddschans_tidig/sen (normerade i loppet) och Oddsens chans."""
    bilder = _bilder(conn, fran)
    chans = {r[0]: r[1] for r in conn.execute("SELECT start_id, chans FROM prognoser WHERE modellversion = ?",
                                              (modeller.AKTIV,))}
    ut = []
    for l in data.lopp(conn, "o.datum >= ?", (fran,), bara_avgjorda=True):
        hs = l["hastar"]
        if sum(1 for h in hs if bilder.get(h["start_id"])) < len(hs) / 2:
            continue
        for h in hs:
            b = bilder.get(h["start_id"], [])
            h["vinnarodds"] = b[-1][1] if b else None
            h["_tidig"] = b[0] if b else None
            h["_sen"] = b[-1] if b else None
            h["oddsen"] = chans.get(h["start_id"])
        for nyckel in ("_tidig", "_sen"):
            inv = [1 / h[nyckel][1] if h[nyckel] else 1 / 100 for h in hs]
            tot = sum(inv)
            for h, x in zip(hs, inv):
                h["oddschans" + nyckel] = x / tot
        ut.append(l)
    return ut


def vikt_for_odds(lopp: List[dict], bas: Dict[str, float], omsamplingar: int = 200) -> dict:
    """Logloss för vinnaren med och utan förhandsodds, och skattad vikt b (ovanpå fasta basvikter) med 90 % intervall."""
    utan = {**bas, "odds_mot_streck": 0.0}
    streck = sannolikhet.logloss(lopp, {"log_streck": 1.0})
    med_nu = sannolikhet.logloss(lopp, bas)
    utan_odds = sannolikhet.logloss(lopp, utan)
    fast = {k: v for k, v in bas.items() if k != "odds_mot_streck"}
    b = sannolikhet.skatta(lopp, ["odds_mot_streck"], l2=0.5, fast=fast)["odds_mot_streck"]
    rng = random.Random(1)
    per_omgang: Dict[str, List[dict]] = defaultdict(list)
    for l in lopp:
        per_omgang[l["omgang_id"]].append(l)
    nycklar = list(per_omgang)
    prover = []
    for _ in range(omsamplingar if len(nycklar) >= 3 else 0):
        urval = [l for k in rng.choices(nycklar, k=len(nycklar)) for l in per_omgang[k]]
        prover.append(sannolikhet.skatta(urval, ["odds_mot_streck"], l2=0.5, fast=fast)["odds_mot_streck"])
    prover.sort()
    return {
        "omgangar": len(nycklar), "lopp": len(lopp),
        "logloss_streck": st.mean(streck), "logloss_utan_odds": st.mean(utan_odds), "logloss_med_odds": st.mean(med_nu),
        "b_nu": bas.get("odds_mot_streck", 0.0), "b_skattad": b,
        "b_intervall": (prover[len(prover) // 20], prover[-len(prover) // 20 - 1]) if prover else None,
    }


def sena_pengar(lopp: List[dict]) -> Dict[str, tuple]:
    """{grupp: (vinster, summa Oddsens chans, summa streck, antal)} efter hur vinnarpoolens chans ändrats."""
    ut: Dict[str, List] = defaultdict(lambda: [0, 0.0, 0.0, 0])
    for l in lopp:
        hs = [h for h in l["hastar"] if h.get("oddsen") is not None]
        if not hs:
            continue
        otot, stot = sum(h["oddsen"] for h in hs), sum(h["streck"] for h in hs)
        for h in hs:
            if not h["_tidig"] or not h["_sen"] or _minuter(h["_tidig"][0], h["_sen"][0]) < MIN_MINUTER:
                continue
            kvot = h["oddschans_sen"] / max(h["oddschans_tidig"], 1e-6)
            for namn, lag, hog in GRUPPER:
                if lag <= kvot < hog:
                    g = ut[namn]
                    g[0] += int(h["nr"] in l["vinnare"])
                    g[1] += h["oddsen"] / otot
                    g[2] += h["streck"] / stot
                    g[3] += 1
    return {k: tuple(v) for k, v in ut.items()}


def rapport(conn: sqlite3.Connection, fran: str = FRAN) -> str:
    lopp = lopp_med_odds(conn, fran)
    if not lopp:
        return f"Inga avgjorda lopp med vinnarodds före spelstopp från {fran} än."
    bas = modeller.vikter(conn)
    v = vikt_for_odds(lopp, bas)
    rader = [f"Vinnarodds före spelstopp: {v['omgangar']} omgångar, {v['lopp']} lopp från {fran}"
             + (" – för lite data för slutsatser (vänta till cirka 8 omgångar)." if v["omgangar"] < 8 else "."), "",
             "1. Vinnaroddsens vikt (logloss för vinnaren, lägre är bättre)",
             f"   Strecken {v['logloss_streck']:.4f} · Oddsen utan odds {v['logloss_utan_odds']:.4f} · "
             f"Oddsen med odds (b = {v['b_nu']:.2f}) {v['logloss_med_odds']:.4f}",
             f"   Skattad b ovanpå Oddsens övriga vikter: {v['b_skattad']:.2f}"
             + (f" (90 % intervall {v['b_intervall'][0]:.2f} – {v['b_intervall'][1]:.2f})" if v["b_intervall"] else ""),
             "", "2. Sena pengar: chansen enligt vinnarpoolen, första mot sista bilden före spelstopp",
             f"   {'grupp':36} {'hästar':>7} {'vann':>6} {'Oddsen':>7} {'streck':>7}  vann/Oddsen"]
    g = sena_pengar(lopp)
    for namn, _, _ in GRUPPER:
        if namn not in g:
            continue
        vinster, oc, sc, n = g[namn]
        k, se = (vinster / oc, math.sqrt(max(vinster, 1)) / oc) if oc else (0, 0)
        rader.append(f"   {namn:36} {n:7} {vinster / n * 100:5.1f}% {oc / n * 100:6.1f}% {sc / n * 100:6.1f}%  {k:4.2f} ± {se:4.2f}")
    return "\n".join(rader)
