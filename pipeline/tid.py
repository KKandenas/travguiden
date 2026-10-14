"""Tidshjälp. Allt lagras i UTC; svensk tid används bara för visning och datum."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

STOCKHOLM = ZoneInfo("Europe/Stockholm")


def parse_iso(s: str) -> datetime:
    """Tolka ISO 8601 med tidszon (klarar 'Z' även på Python 3.9)."""
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    # Python 3.9 kräver 3 eller 6 decimaler; Svenska Spel skickar ibland 1–7 ("16:01:10.1+01:00").
    s = re.sub(r"\.(\d+)(?=[+-]\d\d:\d\d$)", lambda m: "." + m.group(1)[:6].ljust(6, "0"), s)
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        raise ValueError(f"Tidsstämpel saknar tidszon: {s!r}")
    return dt


def till_utc(s: str) -> str:
    """'2026-10-10T15:59:00+02:00' -> '2026-10-10T13:59:00Z'."""
    return parse_iso(s).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def nu_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def svenskt_datum(s: str) -> str:
    return parse_iso(s).astimezone(STOCKHOLM).strftime("%Y-%m-%d")


def lokal_till_utc(s: str) -> str:
    """ATG:s tider saknar tidszon och är svensk tid: '2026-10-17T15:00:00' -> '2026-10-17T13:00:00Z'."""
    dt = datetime.fromisoformat(s[:19])
    return dt.replace(tzinfo=STOCKHOLM).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
