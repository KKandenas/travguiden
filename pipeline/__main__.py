"""Kommandorad för pipelinen.

    python -m pipeline auto                              # det som schemat kör: allt som är aktuellt just nu
    python -m pipeline atg                               # kommande omgångar: hästar, streck, vinnarodds
    python -m pipeline experter                          # experternas system ur ATG:s tipsartiklar
    python -m pipeline kommentarer                       # AI-kommentarer per avdelning (kräver GEMINI_API_KEY)
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
import json
import logging
import sys
import time
from datetime import date, datetime, timedelta, timezone

from . import config, db, export, lagring
from .ai import klient as ai_klient
from .ai import kommentarer as ai_kommentarer
from .http import HamtningsFel
from .model import modeller, statistik
from .modeller import ValideringsFel
from .sources import atg, atgtips
from .tid import nu_utc

log = logging.getLogger("pipeline")
_SPELFORMER = ", ".join(f"'{s}'" for s in config.SPELFORMER)


def _utc_om(timmar: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=timmar)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _satt_status(conn, nyckel: str, varde: dict) -> None:
    """Driftstatus för om-sidan (installningar, se export.bygg_drift)."""
    with conn:
        conn.execute("""INSERT INTO installningar (nyckel, varde, uppdaterad) VALUES (?, ?, ?)
                        ON CONFLICT(nyckel) DO UPDATE SET varde = excluded.varde, uppdaterad = excluded.uppdaterad""",
                     (nyckel, json.dumps(varde, ensure_ascii=False), nu_utc()))


def spara_ai_status(conn) -> None:
    """Hur AI-anropen gick i den här körningen. Sparas bara om AI användes eller saknas."""
    k = ai_klient.KORNING
    ok, orsak = ai_klient.tillganglig()
    if not ok:
        _satt_status(conn, "status:ai", {"konfigurerad": False, "orsak": orsak})
    elif k["lyckade"] or k["misslyckade"] or k["stoppad"]:
        _satt_status(conn, "status:ai", {"konfigurerad": True, **k})


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
    kommande, fel = [], []
    for spelform in config.SPELFORMER:
        try:
            produkt = atg.hamta_produkt(spelform)
        except HamtningsFel as e:      # en spelform som strular får inte stoppa de andra
            log.error("ATG: kunde inte hämta kommande %s: %s", spelform, e)
            fel.append(str(e)[:200])
            continue
        kommande += [g["id"] for g in produkt.get("upcoming") or [] if g.get("id")]
    if not kommande:
        log.info("ATG: ingen kommande %s just nu", " eller ".join(config.SPELFORMER))
    ok = all([_spara_spel(conn, sid) for sid in kommande]) and not fel
    _satt_status(conn, "status:atg", {"ok": ok, "fel": None if ok else ("; ".join(fel) or "minst en omgång gick inte att spara")})
    # Nyss stängda omgångar: hämta igen inom 48 h så att slutstrecken kommer med.
    for (sid,) in conn.execute("SELECT id FROM omgangar WHERE spelstopp BETWEEN ? AND ? AND avgjord = 0",
                               (_utc_om(-48), nu_utc())).fetchall():
        if sid not in kommande:
            _spara_spel(conn, sid)
    return ok


def steg_experter(conn) -> None:
    """Experternas system för kommande omgångar. Valfri källa: fel loggas men stoppar aldrig pipelinen."""
    kommande = [r[0] for r in conn.execute(
        f"SELECT id FROM omgangar WHERE spelform IN ({_SPELFORMER}) AND avgjord = 0 AND spelstopp > ?", (nu_utc(),))]
    if not kommande:
        return
    try:
        system, varningar = atgtips.hamta_expertsystem(kommande)
    except Exception as e:  # en valfri källa får aldrig stoppa pipelinen
        log.error("Experter: kunde inte hämta systemen: %s", e)
        _satt_status(conn, "status:experter", {"ok": False, "fel": str(e)[:200]})
        return
    for v in varningar:
        log.warning("Experter: %s", v)
    n = lagring.spara_expertsystem(conn, system, nu_utc())
    _satt_status(conn, "status:experter", {"ok": True, "fel": None, "hittade": n})
    log.info("Experter: %d system sparade (%s)", n, ", ".join(sorted({f"{s.namn}" for s in system})) or "inga")


def steg_kommentarer(conn) -> None:
    """AI-kommentarer för kommande omgångar. Valfritt: utan nyckel eller vid fel loggas det och körningen fortsätter."""
    ok, orsak = ai_klient.tillganglig()
    if not ok:
        log.info("Kommentarer: hoppar över – %s", orsak)
        spara_ai_status(conn)
        return
    for (sid,) in conn.execute(f"SELECT id FROM omgangar WHERE spelform IN ({_SPELFORMER}) AND avgjord = 0 "
                               "AND spelstopp > ?", (nu_utc(),)).fetchall():
        try:
            n = ai_kommentarer.uppdatera(conn, ai_klient.anropa_json, export.omgang_data(conn, sid))
            log.info("Kommentarer: %s – %d nya", sid, n)
        except ai_klient.AiFel as e:
            log.warning("Kommentarer: %s – %s", sid, e)
    spara_ai_status(conn)


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
    for k in ("auto", "atg", "experter", "kommentarer", "resultat", "statistik", "migrera"):
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
    if a.kommando in ("auto", "experter"):
        steg_experter(conn)
    if a.kommando in ("auto", "resultat"):
        ok &= steg_resultat(conn)
    tranad = False
    if a.kommando in ("statistik", "backfill") or (a.kommando == "auto" and statistik.behover_traning(conn)):
        statistik.kor(conn)
        tranad = True
    if a.kommando in ("auto", "atg", "experter", "resultat", "backfill", "prognos", "statistik"):
        # Efter ny träning räknas även avgjorda omgångar om (walk-forward-vikter, se statistik.py)
        modeller.berakna_prognoser(conn, alla=tranad or getattr(a, "alla", False))
    if a.kommando in ("auto", "kommentarer"):
        steg_kommentarer(conn)
    if a.kommando in ("auto", "atg", "experter", "kommentarer", "resultat", "export", "statistik"):
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
