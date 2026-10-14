"""Kommandorad för pipelinen.

    python -m pipeline auto                              # det som schemat kör: allt som är aktuellt just nu
    python -m pipeline atg                               # kommande omgångar: hästar, streck, vinnarodds
    python -m pipeline resultat                          # resultat och utdelning för omgångar efter spelstopp
    python -m pipeline backfill 2025-10-25 2026-10-10    # hämta historiska omgångar (1 s paus mellan anrop)
    python -m pipeline backfill 2023-01-01 2025-10-18 --spelform V75   # äldre V75 som träningsdata
    python -m pipeline prognos [--alla]                  # räkna chans per häst med aktiva modeller
    python -m pipeline statistik                         # träna kalibreringen och utvärdera modellerna
    python -m pipeline export                            # skriv docs/omgang.json, senaste.json, historik.json
    python -m pipeline migrera

Varje steg loggar tydligt och fortsätter med nästa om något går fel.
Avslutningskoden är 1 om ett kritiskt steg (ATG, resultat eller export) misslyckades.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date, datetime, timedelta, timezone

from . import config, db, export, lagring
from .http import HamtningsFel
from .model import modeller, statistik
from .modeller import ValideringsFel
from .sources import atg
from .tid import nu_utc

log = logging.getLogger("pipeline")


def _utc_om(timmar: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=timmar)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _spara_spel(conn, spel_id: str) -> bool:
    try:
        o = atg.tolka_spel(atg.hamta_spel(spel_id), hamtad=nu_utc())
    except (HamtningsFel, ValideringsFel, KeyError, ValueError) as e:
        log.error("ATG: kunde inte spara %s: %s", spel_id, e)
        return False
    nya = lagring.spara_omgang(conn, o)
    log.info("%s (%s, %s, spelstopp %s): nya hästar %d, streck %d, odds %d%s", o.id, o.bana, o.status,
             o.spelstopp, nya["starter"], nya["streck"], nya["odds"], " – avgjord" if o.avgjord else "")
    return True


def steg_atg(conn) -> bool:
    try:
        produkt = atg.hamta_produkt()
    except HamtningsFel as e:
        log.error("ATG: kunde inte hämta kommande omgångar: %s", e)
        return False
    kommande = [g["id"] for g in produkt.get("upcoming") or [] if g.get("id")]
    if not kommande:
        log.info("ATG: ingen kommande %s just nu", config.SPELFORM)
    ok = all([_spara_spel(conn, sid) for sid in kommande])
    # Nyss stängda omgångar: hämta igen inom 48 h så att slutstrecken kommer med.
    for (sid,) in conn.execute("SELECT id FROM omgangar WHERE spelstopp BETWEEN ? AND ? AND avgjord = 0",
                               (_utc_om(-48), nu_utc())).fetchall():
        if sid not in kommande:
            _spara_spel(conn, sid)
    return ok


def steg_resultat(conn) -> bool:
    ok = True
    for sid in lagring.ej_avgjorda(conn, nu_utc()):
        ok &= _spara_spel(conn, sid)
    return ok


def steg_backfill(conn, fran: str, till: str, spelform: str) -> bool:
    """Hämta alla omgångar av spelformen mellan två datum (lördagar och andra dagar)."""
    d, slut = date.fromisoformat(fran), date.fromisoformat(till)
    redan = {r[0] for r in conn.execute("SELECT id FROM omgangar WHERE avgjord = 1")}
    ok = True
    while d <= slut:
        try:
            spel = atg.spel_for_dag(d.isoformat(), spelform)
        except HamtningsFel as e:
            log.warning("Backfill: kalendern för %s gick inte att hämta: %s", d, e)
            spel = []
        time.sleep(0.3)
        for sid in spel:
            if sid in redan:
                continue
            ok &= _spara_spel(conn, sid)
            time.sleep(1)
        d += timedelta(days=1)
    return ok


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="pipeline", description="Travguidens datapipeline")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="kommando", required=True)
    for k in ("auto", "atg", "resultat", "statistik", "migrera"):
        sub.add_parser(k)
    b = sub.add_parser("backfill")
    b.add_argument("fran")
    b.add_argument("till")
    b.add_argument("--spelform", default=config.SPELFORM)
    pr = sub.add_parser("prognos")
    pr.add_argument("--alla", action="store_true")
    ex = sub.add_parser("export")
    ex.add_argument("--omgang")
    ex.add_argument("--till")
    ex.add_argument("--dolj-resultat", action="store_true")
    a = p.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s", datefmt="%H:%M:%S")
    conn = db.anslut()
    db.migrera(conn)

    ok = True
    if a.kommando == "migrera":
        return 0
    if a.kommando == "backfill":
        ok = steg_backfill(conn, a.fran, a.till, a.spelform)
    if a.kommando in ("auto", "atg"):
        ok &= steg_atg(conn)
    if a.kommando in ("auto", "resultat"):
        ok &= steg_resultat(conn)
    tranad = False
    if a.kommando in ("statistik", "backfill") or (a.kommando == "auto" and statistik.behover_traning(conn)):
        statistik.kor(conn)
        tranad = True
    if a.kommando in ("auto", "atg", "resultat", "backfill", "prognos", "statistik"):
        # Efter ny träning räknas även avgjorda omgångar om (walk-forward-vikter, se statistik.py)
        modeller.berakna_prognoser(conn, alla=tranad or getattr(a, "alla", False))
    if a.kommando in ("auto", "atg", "resultat", "export", "statistik"):
        try:
            if getattr(a, "till", None):
                export.exportera_omgang(conn, a.omgang, a.till, dolj_resultat=a.dolj_resultat)
            else:
                export.exportera_allt(conn)
        except Exception as e:
            log.exception("Export misslyckades: %s", e)
            ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
