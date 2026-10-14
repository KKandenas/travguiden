"""Gemensam konfiguration. Hemligheter läses från miljövariabler, aldrig från filer i repot."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("TRAV_DB", ROOT / "data" / "trav.db"))
MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
DOCS_DIR = ROOT / "docs"

USER_AGENT = "Travguiden/0.1 (hobbyprojekt)"
HTTP_TIMEOUT = 30

# ATG:s öppna API (det som atg.se själv använder). Se DATAKALLOR.md.
ATG_BASE = "https://www.atg.se/services/racinginfo/v1/api"

# Lördagens V-spel. V85 ersatte V75 den 25 oktober 2025, och V75 kommer tillbaka den 28 november 2026
# (V85 pausas då). Pipelinen följer båda, så bytet sker av sig självt när ATG lägger ut den första V75:an.
SPELFORMER = ["V85", "V75"]
SPELFORM = "V85"                 # förval för backfill
V75_NY_START = "2026-11-28"      # nya V75: radpris 60 öre


def radpris(spelform: str, datum: str) -> float:
    """Kr per rad. Nya V75 från 28 november 2026 kostar 60 öre, allt annat 50 öre."""
    return 0.6 if spelform == "V75" and datum >= V75_NY_START else 0.5


def vinstgrupper(antal_avd: int) -> list:
    """Antal rätt som ger utdelning: V85 8–5, V75 7–5."""
    return list(range(antal_avd, 4, -1))
