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

SPELFORM = "V85"
RADPRIS = 0.5                    # kr per rad
