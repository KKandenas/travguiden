"""Kommandorad för pipelinen.

    python -m pipeline planerad                          # det som schemat startar: kör auto bara om en planerad tid passerats
    python -m pipeline auto                              # det som schemat kör: allt som är aktuellt just nu
    python -m pipeline atg                               # kommande omgångar: hästar, streck, vinnarodds
    python -m pipeline experter                          # experternas system ur ATG:s tipsartiklar
    python -m pipeline kommentarer                       # AI-kommentarer per avdelning (kräver GEMINI_API_KEY)
    python -m pipeline hastinfo [--max 600]              # utrustning och senaste starter (kommande + historik)
    python -m pipeline hastkoll                          # Hästkoll: AI bedömer senaste loppen (kräver GEMINI_API_KEY)
    python -m pipeline skrallanalys [--fran D] [--min N] # vad hade skrällarna gemensamt? (mot Oddsens chans)
    python -m pipeline oddsanalys [--fran D]             # vinnaroddsens vikt och sena pengar (förhandsodds)
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

from . import config, db, export, lagring, schema
from .ai import klient as ai_klient
from .ai import hastkoll as ai_hastkoll
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


# Lopp hämtade före den här tidpunkten saknar förstapris och underlag (migrering 008) och hämtas om. Vissa lopp
# saknar en prissträng som går att tolka; de ska inte hämtas om vid varje körning.
HASTINFO_VERSION = "2026-10-30T16:50:00Z"   # när migrering 008 pushades


def steg_hastinfo(conn, max_historik: int = 16) -> None:
    """Utrustning och de senaste starterna per häst (Hästkoll). Kommande omgångar uppdateras alltid; historiken
    fylls på med högst max_historik lopp per körning, nyast först. Valfritt: fel loggas men stoppar inget."""
    kommande = conn.execute(
        f"""SELECT a.id, a.lopp_id FROM avdelningar a JOIN omgangar o ON o.id = a.omgang_id
            WHERE o.spelform IN ({_SPELFORMER}) AND o.avgjord = 0 AND o.spelstopp > ?""", (nu_utc(),)).fetchall()
    historik = conn.execute(
        f"""SELECT a.id, a.lopp_id FROM avdelningar a JOIN omgangar o ON o.id = a.omgang_id
            WHERE o.spelform IN ({_SPELFORMER}) AND o.avgjord = 1
              AND (a.hastinfo_hamtad IS NULL OR a.hastinfo_hamtad < ?)      -- hämtat före migrering 008
            ORDER BY o.spelstopp DESC, a.avd LIMIT ?""", (HASTINFO_VERSION, max_historik)).fetchall()
    hamtade = fel = 0
    for i, (avd_id, lopp_id) in enumerate(list(kommande) + list(historik)):
        if i:
            time.sleep(0.3)
        try:
            info, forstapris = atg.hamta_hastinfo(lopp_id)
            lagring.spara_hastinfo(conn, avd_id, info, nu_utc(), forstapris)
            hamtade += 1
        except (HamtningsFel, ValideringsFel, KeyError, ValueError, TypeError) as e:
            log.warning("Hästinfo: %s – %s", lopp_id, e)
            fel += 1
    kvar = conn.execute("SELECT COUNT(*) FROM avdelningar a JOIN omgangar o ON o.id = a.omgang_id "
                        f"WHERE o.spelform IN ({_SPELFORMER}) AND o.avgjord = 1 "
                        "AND (a.hastinfo_hamtad IS NULL OR a.hastinfo_hamtad < ?)", (HASTINFO_VERSION,)).fetchone()[0]
    log.info("Hästinfo: %d lopp hämtade (%d kommande), %d fel, %d historiska lopp kvar", hamtade, len(kommande), fel, kvar)


def steg_hastkoll(conn) -> None:
    """Hästkoll för omgångar där loppkommentarer finns och hästar saknar bedömning: kommande först, sedan
    nyss avgjorda (kommentarerna försvinner inom en vecka). Högst två omgångar per körning."""
    ok, orsak = ai_klient.tillganglig()
    if not ok:
        log.info("Hästkoll: hoppar över – %s", orsak)
        return
    # Kommande omgångar varje gång (nya kommentarer ger nya bedömningar), och nyss avgjorda med obedömda hästar
    kommande = [r[0] for r in conn.execute(
        f"""SELECT id FROM omgangar WHERE spelform IN ({_SPELFORMER}) AND avgjord = 0 AND spelstopp > ?""", (nu_utc(),))]
    obedomda = [r[0] for r in conn.execute(
        f"""SELECT DISTINCT o.id FROM omgangar o JOIN avdelningar a ON a.omgang_id = o.id
            JOIN starter s ON s.avdelning_id = a.id JOIN tidigare_starter t ON t.start_id = s.id
            WHERE o.spelform IN ({_SPELFORMER}) AND t.kommentar IS NOT NULL AND s.struken = 0
              AND NOT EXISTS (SELECT 1 FROM hastkoll k WHERE k.start_id = s.id)
            ORDER BY o.avgjord, o.spelstopp DESC LIMIT 2""")]
    omgangar = list(dict.fromkeys(kommande + obedomda))
    for sid in omgangar:
        try:
            n = ai_hastkoll.uppdatera(conn, ai_klient.anropa_json, sid, ny_version=sid in kommande)
            log.info("Hästkoll: %s – %d bedömningar", sid, n)
        except ai_klient.AiFel as e:
            log.warning("Hästkoll: %s – %s", sid, e)


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
    for k in ("auto", "planerad", "atg", "experter", "kommentarer", "resultat", "statistik", "migrera"):
        sub.add_parser(k)
    oa = sub.add_parser("oddsanalys")
    oa.add_argument("--fran", default="2026-10-24", help="bara omgångar från detta datum")
    sa = sub.add_parser("skrallanalys")
    sa.add_argument("--fran", default="", help="bara lopp från detta datum (YYYY-MM-DD)")
    sa.add_argument("--min", type=int, default=100, help="visa bara grupper med minst så många hästar")
    hk = sub.add_parser("hastkoll")
    hk.add_argument("--omgang", help="bedöm om alla hästar i omgången med nuvarande instruktion (från sparade kommentarer)")
    hi = sub.add_parser("hastinfo")
    hi.add_argument("--max", type=int, default=600, help="högst så många historiska lopp")
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
    if a.kommando == "oddsanalys":
        from .model import oddsanalys
        print(oddsanalys.rapport(conn, a.fran))
        return 0
    if a.kommando == "skrallanalys":
        from .model import skrallanalys
        print(skrallanalys.rapport(conn, a.fran, a.min))
        return 0
    planerad = None
    if a.kommando == "planerad":
        r = conn.execute("SELECT varde FROM installningar WHERE nyckel = 'senaste_planerade'").fetchone()
        planerad = schema.forfallen(r[0] if r else None, datetime.now(timezone.utc))
        if planerad is None:
            log.info("Planerad: inget att göra – den senaste planerade uppdateringen är redan körd")
            return 0
        log.info("Planerad: kör uppdateringen för %s (svensk tid)",
                 planerad.astimezone(schema.SVENSK_TID).strftime("%a %d %b %H:%M"))
        a.kommando = "auto"
    if a.kommando == "backfill":
        ok = steg_backfill(conn, a.fran, a.till, a.spelform)
    if a.kommando in ("auto", "atg"):
        ok &= steg_atg(conn)
    if a.kommando in ("auto", "experter"):
        steg_experter(conn)
    if a.kommando == "auto":
        steg_hastinfo(conn)
    if a.kommando == "hastinfo":
        steg_hastinfo(conn, a.max)
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
    if a.kommando == "hastkoll" and a.omgang:
        ok_ai, orsak = ai_klient.tillganglig()
        if not ok_ai:
            log.error("Hästkoll: %s", orsak)
        else:
            try:
                n = ai_hastkoll.uppdatera(conn, ai_klient.anropa_json, a.omgang, alla=True)
                log.info("Hästkoll: %s – %d bedömningar (om, med faktorer)", a.omgang, n)
            except ai_klient.AiFel as e:
                log.warning("Hästkoll: %s – %s", a.omgang, e)
        spara_ai_status(conn)
    elif a.kommando in ("auto", "hastkoll"):
        steg_hastkoll(conn)
        spara_ai_status(conn)
    if a.kommando in ("auto", "atg", "experter", "kommentarer", "hastkoll", "hastinfo", "resultat", "export", "statistik"):
        try:
            if getattr(a, "till", None):
                export.exportera_omgang(conn, a.omgang, a.till, dolj_resultat=a.dolj_resultat)
            else:
                export.exportera_allt(conn)
        except Exception as e:
            log.exception("Export misslyckades: %s", e)
            ok = False
    if planerad is not None:
        # Markeras som körd även om något steg misslyckades, så att nästa start inte gör om samma sak
        with conn:
            conn.execute("""INSERT INTO installningar (nyckel, varde, uppdaterad) VALUES ('senaste_planerade', ?, ?)
                            ON CONFLICT(nyckel) DO UPDATE SET varde = excluded.varde, uppdaterad = excluded.uppdaterad""",
                         (planerad.strftime("%Y-%m-%dT%H:%M:%SZ"), nu_utc()))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
