"""SQLite-anslutning och versionerade migreringar.

Migreringar är filer i pipeline/migrations med namnet NNN_beskrivning.sql. De körs i
nummerordning, var och en i en egen transaktion, och registreras i schema_migreringar.
En migrering som redan körts körs aldrig igen. Ändra aldrig en redan körd fil – lägg till en ny.
"""
from __future__ import annotations

import logging
import re
import sqlite3
from pathlib import Path

from . import config
from .tid import nu_utc

log = logging.getLogger(__name__)

_MIGRERINGSNAMN = re.compile(r"^(\d{3})_[\w-]+\.sql$")


def anslut(path: Path | str | None = None) -> sqlite3.Connection:
    path = Path(path or config.DB_PATH)
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def migrera(conn: sqlite3.Connection, katalog: Path = config.MIGRATIONS_DIR) -> list[int]:
    """Kör alla migreringar som inte redan körts. Returnerar de versioner som kördes."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migreringar ("
        " version INTEGER PRIMARY KEY, namn TEXT NOT NULL, korad TEXT NOT NULL)"
    )
    korda = {r[0] for r in conn.execute("SELECT version FROM schema_migreringar")}
    filer = []
    for f in sorted(katalog.glob("*.sql")):
        m = _MIGRERINGSNAMN.match(f.name)
        if not m:
            raise RuntimeError(f"Ogiltigt migreringsnamn: {f.name}")
        filer.append((int(m.group(1)), f))
    versioner = [v for v, _ in filer]
    if len(versioner) != len(set(versioner)):
        raise RuntimeError("Två migreringar har samma nummer")

    nya = []
    for version, f in filer:
        if version in korda:
            continue
        log.info("Kör migrering %s", f.name)
        sql = f.read_text(encoding="utf-8")
        # executescript committar själv, så vi styr transaktionen explicit.
        try:
            conn.executescript(
                "BEGIN;\n" + sql + "\n"
                f"INSERT INTO schema_migreringar (version, namn, korad) VALUES ({version}, '{f.name}', '{nu_utc()}');\n"
                "COMMIT;"
            )
        except sqlite3.Error:
            conn.rollback()
            log.error("Migrering %s misslyckades och rullades tillbaka", f.name)
            raise
        nya.append(version)
    return nya
