"""Modellversioner och beräkning av prognoser (chans per häst) till tabellen prognoser.

Ändra aldrig en befintlig version – skapa en ny, så att versionerna kan jämföras i backtest.

- streck:          chansen är V85-strecken (folkets bedömning). Referens.
- kalibrerad-v1:   villkorad logit på log(streck) och, när de finns, vinnaroddsen
                   (chans ∝ streck^a · (oddschans/streck)^b). Exponenten a skattas separat för V85 och V75. Vikterna skattas i statistik.py. "Oddsen" i appen.
- experter-v1:     kalibrerad-v1 plus experternas system (chans ∝ … · (expertandel + 0,05)^c). Räknas bara
                   för lopp där expertsystem finns. "Experterna" i appen.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from typing import Dict, List, Optional

from ..tid import nu_utc
from . import data, sannolikhet

log = logging.getLogger(__name__)

AKTIV = "kalibrerad-v1"
EXPERTMODELL = "experter-v1"
EGENSKAPER = ["log_streck", "log_streck_v85", "odds_mot_streck"]
EXPERTEGENSKAPER = EGENSKAPER + ["experter"]
# Experternas vikt innan det finns tillräckligt många avgjorda lopp att skatta den på (statistik.MIN_EXPERTLOPP).
# Försiktig: experterna publicerar tidigt i veckan och strecken har redan tagit in mycket av deras bedömning.
# c = 0,15 gör att en häst alla fem tar som spik får knappt 1,7 gånger så hög chans (före normering)
# som en häst ingen tar med.
STANDARD_EXPERTVIKT = 0.15
# Används tills statistik.py har skattat vikter: V75-strecken som de är, V85-strecken något utplattade
STANDARDVIKTER = {"log_streck": 1.0, "log_streck_v85": -0.1, "odds_mot_streck": 0.0}
MODELLER = {
    "streck": "Strecken",
    "kalibrerad-v1": "Oddsen",
    "experter-v1": "Experterna",
}


def vikter(conn: sqlite3.Connection, manad: Optional[str] = None) -> Dict[str, float]:
    """Senaste vikterna, eller (manad = 'YYYY-MM') de som skattats på data före den månaden."""
    nyckel = f"vikter:{AKTIV}"
    r = conn.execute("SELECT varde FROM installningar WHERE nyckel = ?", (nyckel,)).fetchone()
    if not r:
        return dict(STANDARDVIKTER)
    sparat = json.loads(r[0])
    if manad is None:
        return sparat["senaste"]
    tidigare = [m for m in sparat.get("per_manad", {}) if m <= manad]
    return sparat["per_manad"][max(tidigare)] if tidigare else dict(STANDARDVIKTER)


def expertvikter(conn: sqlite3.Connection, oddsvikter: Dict[str, float], manad: Optional[str] = None) -> Dict[str, float]:
    """Skattade vikter för experter-v1 (walk-forward som vikter()), annars Oddsens vikter plus standardvikten."""
    standard = {**oddsvikter, "experter": STANDARD_EXPERTVIKT}
    r = conn.execute("SELECT varde FROM installningar WHERE nyckel = ?", (f"vikter:{EXPERTMODELL}",)).fetchone()
    if not r:
        return standard
    sparat = json.loads(r[0])
    if manad is None:
        return sparat["senaste"]
    tidigare = [m for m in sparat.get("per_manad", {}) if m <= manad]
    return sparat["per_manad"][max(tidigare)] if tidigare else standard


def _odds_fore_spelstopp(conn, lopp: List[dict]) -> None:
    """Ersätt vinnaroddsen med den senaste ögonblicksbilden före spelstopp (inga odds efter stängning)."""
    for l in lopp:
        for h in l["hastar"]:
            r = conn.execute(
                """SELECT v.odds FROM vinnarodds v JOIN starter s ON s.id = v.start_id
                   JOIN avdelningar a ON a.id = s.avdelning_id JOIN omgangar o ON o.id = a.omgang_id
                   WHERE v.start_id = ? AND v.tidpunkt <= o.spelstopp ORDER BY v.tidpunkt DESC LIMIT 1""",
                (h["start_id"],)).fetchone()
            h["vinnarodds"] = r[0] if r else None


def berakna_prognoser(conn: sqlite3.Connection, alla: bool = False) -> int:
    """Räkna chans per häst för båda modellerna. Utan `alla` bara för omgångar som inte är avgjorda."""
    lopp = data.lopp(conn, "1" if alla else "o.avgjord = 0")
    _odds_fore_spelstopp(conn, lopp)
    nu = nu_utc()
    n = 0
    with conn:
        for l in lopp:
            # Avgjorda omgångar räknas om med vikterna från före sin månad, så att backtestet aldrig
            # använder vikter som sett resultatet. Kommande omgångar använder de senaste vikterna.
            w = vikter(conn, l["datum"][:7]) if alla else vikter(conn)
            modeller = [("streck", sannolikhet.normalisera([h["streck"] for h in l["hastar"]])),
                        (AKTIV, sannolikhet.chanser(l, w))]
            if any(h.get("expertandel") is not None for h in l["hastar"]):
                ew = expertvikter(conn, w, l["datum"][:7] if alla else None)
                modeller.append((EXPERTMODELL, sannolikhet.chanser(l, ew)))
            for modell, p in modeller:
                for h, c in zip(l["hastar"], p):
                    conn.execute("""INSERT INTO prognoser (start_id, modellversion, chans, skapad) VALUES (?, ?, ?, ?)
                                    ON CONFLICT(start_id, modellversion) DO UPDATE SET chans = excluded.chans,
                                        skapad = excluded.skapad""", (h["start_id"], modell, c, nu))
            n += 1
    log.info("Prognoser: %d lopp", n)
    return n
