"""Exporterar JSON till appen i docs/.

- omgang.json:   närmaste kommande V85-omgång (annars den senaste), med alla hästar och chanser
- senaste.json:  senast avgjorda V85-omgången, för rättningen
- historik.json: alla avgjorda V85-omgångar i kompakt form, för backtestet
"""
from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Optional

from . import config
from .model import modeller
from .tid import nu_utc

log = logging.getLogger(__name__)

KON = {"stallion": "hingst", "mare": "sto", "gelding": "valack"}
_SENASTE = "(SELECT {f} FROM {t} WHERE start_id = s.id ORDER BY tidpunkt DESC LIMIT 1)"


def _skriv(sokvag: Path, data) -> None:
    sokvag.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    tmp = sokvag.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(sokvag)
    log.info("Skrev %s (%d kB)", sokvag.name, len(text) // 1024)


def _installning(conn, nyckel):
    r = conn.execute("SELECT varde FROM installningar WHERE nyckel = ?", (nyckel,)).fetchone()
    return json.loads(r[0]) if r else None


def omgang_data(conn: sqlite3.Connection, omgang_id: str, dolj_resultat: bool = False) -> dict:
    o = conn.execute("SELECT * FROM omgangar WHERE id = ?", (omgang_id,)).fetchone()
    if o is None:
        raise ValueError(f"Omgången {omgang_id} finns inte")
    system = conn.execute("SELECT id, kalla, namn, artikel, rader FROM expertsystem WHERE omgang_id = ? "
                          "ORDER BY kalla DESC, namn", (omgang_id,)).fetchall()
    valda: dict = {}            # (avd, nr) -> [index i system]
    for i, e in enumerate(system):
        for v in conn.execute("SELECT avd, nr FROM expertval WHERE system_id = ?", (e["id"],)):
            valda.setdefault((v["avd"], v["nr"]), []).append(i)
    avdelningar = []
    for a in conn.execute("SELECT * FROM avdelningar WHERE omgang_id = ? ORDER BY avd", (omgang_id,)):
        hastar = []
        for s in conn.execute(f"""
                SELECT s.*, {_SENASTE.format(f='andel', t='streck')} AS streck,
                       {_SENASTE.format(f='odds', t='vinnarodds')} AS odds,
                       (SELECT chans FROM prognoser WHERE start_id = s.id AND modellversion = ?) AS chans,
                       (SELECT chans FROM prognoser WHERE start_id = s.id AND modellversion = ?) AS chans_exp
                FROM starter s WHERE s.avdelning_id = ? ORDER BY s.nr""",
                (modeller.AKTIV, modeller.EXPERTMODELL, a["id"])):
            h = {
                "nr": s["nr"], "namn": s["hast"], "kusk": s["kusk"], "tranare": s["tranare"],
                "spar": s["spar"], "distans": s["distans"], "alder": s["alder"], "kon": KON.get(s["kon"], s["kon"]),
                "streck": round(s["streck"], 4) if s["streck"] is not None else None,
                "chans": round(s["chans"], 4) if s["chans"] is not None and not s["struken"] else None,
                "odds": s["odds"], "rekord": s["rekord"],
                "livs": [s["livs_starter"], s["livs_segrar"], s["livs_platser"]],
                "ar": [s["ar_starter"], s["ar_segrar"]], "intjant": s["intjant"],
                "snittodds": s["snittodds_5"], "kusk_proc": s["kusk_segerproc"],
            }
            if s["chans_exp"] is not None and not s["struken"]:
                h["chans_exp"] = round(s["chans_exp"], 4)
            if system:
                h["experter"] = valda.get((a["avd"], s["nr"]), [])     # index i "experter" nedan
            if s["struken"]:
                h["struken"] = True
            if not dolj_resultat and s["placering"] is not None:
                h.update(placering=s["placering"], slutodds=s["slutodds"], km_tid=s["km_tid"])
            hastar.append(h)
        avd = {"avd": a["avd"], "loppnr": a["loppnr"], "namn": a["namn"], "distans": a["distans"],
               "startmetod": a["startmetod"], "starttid": a["starttid"], "hastar": hastar}
        if a["vinnare"] and not dolj_resultat:
            avd["vinnare"] = [int(x) for x in a["vinnare"].split(",")]
        avdelningar.append(avd)
    utdelning = {} if dolj_resultat else {
        r["ratt"]: {"kr": r["kr"], "antal": r["antal"]}
        for r in conn.execute("SELECT * FROM utdelning WHERE omgang_id = ? ORDER BY ratt DESC", (omgang_id,))}
    return {
        "omgang": {"id": o["id"], "spelform": o["spelform"], "datum": o["datum"], "bana": o["bana"],
                   "spelstopp": o["spelstopp"], "status": o["status"], "omsattning": o["omsattning"],
                   "avgjord": bool(o["avgjord"]) and not dolj_resultat},
        "modell": {"version": modeller.AKTIV, "namn": modeller.MODELLER[modeller.AKTIV]},
        "uppdaterad": nu_utc(),
        "avdelningar": avdelningar,
        "experter": [{"namn": e["namn"], "kalla": e["kalla"], "artikel": e["artikel"], "rader": e["rader"]}
                     for e in system],
        "utdelning": utdelning,
    }


def historik(conn: sqlite3.Connection) -> dict:
    ut = []
    for o in conn.execute("SELECT * FROM omgangar WHERE spelform = 'V85' AND avgjord = 1 ORDER BY spelstopp"):
        avd = []
        for a in conn.execute("SELECT * FROM avdelningar WHERE omgang_id = ? ORDER BY avd", (o["id"],)):
            rader = conn.execute(f"""
                SELECT s.nr, s.struken, {_SENASTE.format(f='andel', t='streck')} AS streck,
                       (SELECT chans FROM prognoser WHERE start_id = s.id AND modellversion = ?) AS chans,
                       (SELECT chans FROM prognoser WHERE start_id = s.id AND modellversion = ?) AS chans_exp
                FROM starter s WHERE s.avdelning_id = ? ORDER BY s.nr""",
                (modeller.AKTIV, modeller.EXPERTMODELL, a["id"])).fetchall()
            kvar = [r for r in rader if not r["struken"] and r["streck"] is not None and r["chans"] is not None]
            if not kvar:
                break
            avd.append({
                "v": [int(x) for x in a["vinnare"].split(",")],
                "f": max(kvar, key=lambda r: r["streck"])["nr"],
                "s": [r["nr"] for r in rader if r["struken"]],
                # [nr, chans, streck] och, om experternas system fanns, Experternas chans som fjärde värde
                "h": [[r["nr"], round(r["chans"], 4), round(r["streck"], 4)]
                      + ([round(r["chans_exp"], 4)] if r["chans_exp"] is not None else []) for r in kvar],
            })
        if len(avd) != 8:
            continue
        utd = {r["ratt"]: r["kr"] for r in conn.execute("SELECT ratt, kr FROM utdelning WHERE omgang_id = ?", (o["id"],))}
        ut.append({"id": o["id"], "datum": o["datum"], "bana": o["bana"], "utdelning": utd, "avd": avd})
    return {"uppdaterad": nu_utc(), "omgangar": ut}


def exportera_omgang(conn: sqlite3.Connection, omgang_id: Optional[str], till: str, dolj_resultat: bool = False) -> None:
    if not omgang_id:
        omgang_id = conn.execute("SELECT id FROM omgangar WHERE spelform = 'V85' AND avgjord = 1 "
                                 "ORDER BY spelstopp DESC LIMIT 1").fetchone()[0]
    _skriv(Path(till), omgang_data(conn, omgang_id, dolj_resultat))


def exportera_allt(conn: sqlite3.Connection) -> None:
    nu = nu_utc()
    rad = conn.execute("SELECT id FROM omgangar WHERE spelform = 'V85' AND avgjord = 0 AND spelstopp > ? "
                       "ORDER BY spelstopp LIMIT 1", (nu,)).fetchone() or \
        conn.execute("SELECT id FROM omgangar WHERE spelform = 'V85' ORDER BY spelstopp DESC LIMIT 1").fetchone()
    if rad:
        d = omgang_data(conn, rad[0])
        d["statistik"] = _installning(conn, "statistik")
        _skriv(config.DOCS_DIR / "omgang.json", d)
    senaste = conn.execute("SELECT id FROM omgangar WHERE spelform = 'V85' AND avgjord = 1 "
                           "ORDER BY spelstopp DESC LIMIT 1").fetchone()
    if senaste:
        _skriv(config.DOCS_DIR / "senaste.json", omgang_data(conn, senaste[0]))
    _skriv(config.DOCS_DIR / "historik.json", historik(conn))
