"""Skriver validerad data till databasen. Allt är idempotent: att spara samma sak två gånger
ger inga dubbletter. Ögonblicksbilder (streck, vinnarodds) sparas bara när värdet faktiskt ändrats."""
from __future__ import annotations

import logging
import sqlite3
from typing import Dict, List

from .modeller import Omgang

log = logging.getLogger(__name__)

_STARTFALT = ("hast_id", "hast", "alder", "kon", "kusk", "tranare", "spar", "distans", "struken",
              "livs_starter", "livs_segrar", "livs_platser", "ar_starter", "ar_segrar", "intjant", "rekord",
              "snittodds_5", "kusk_segerproc", "tranare_segerproc", "placering", "slutodds", "km_tid")


def spara_omgang(conn: sqlite3.Connection, o: Omgang) -> Dict[str, int]:
    """Spara omgång, avdelningar, hästar, streck, vinnarodds och utdelning i en transaktion."""
    nya = {"starter": 0, "streck": 0, "odds": 0}
    with conn:
        conn.execute(
            """INSERT INTO omgangar (id, spelform, datum, bana, spelstopp, status, omsattning, avgjord)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET datum = excluded.datum, bana = excluded.bana,
                   spelstopp = excluded.spelstopp, status = excluded.status,
                   omsattning = COALESCE(excluded.omsattning, omgangar.omsattning),
                   avgjord = MAX(omgangar.avgjord, excluded.avgjord)""",
            (o.id, o.spelform, o.datum, o.bana, o.spelstopp, o.status, o.omsattning, int(o.avgjord)))
        for ratt, kr in o.utdelning.items():
            conn.execute("""INSERT INTO utdelning (omgang_id, ratt, kr, antal) VALUES (?, ?, ?, ?)
                            ON CONFLICT(omgang_id, ratt) DO UPDATE SET kr = excluded.kr, antal = excluded.antal""",
                         (o.id, ratt, kr, o.vinnande_rader.get(ratt)))

        for a in o.avdelningar:
            conn.execute(
                """INSERT INTO avdelningar (omgang_id, avd, lopp_id, loppnr, namn, distans, startmetod, starttid, vinnare)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(omgang_id, avd) DO UPDATE SET lopp_id = excluded.lopp_id, loppnr = excluded.loppnr,
                       namn = excluded.namn, distans = excluded.distans, startmetod = excluded.startmetod,
                       starttid = excluded.starttid, vinnare = COALESCE(excluded.vinnare, avdelningar.vinnare)""",
                (o.id, a.avd, a.lopp_id, a.loppnr, a.namn, a.distans, a.startmetod, a.starttid,
                 ",".join(map(str, a.vinnare)) or None))
            avd_id = conn.execute("SELECT id FROM avdelningar WHERE omgang_id = ? AND avd = ?",
                                  (o.id, a.avd)).fetchone()[0]
            for s in a.starter:
                varden = [getattr(s, f) for f in _STARTFALT]
                varden[_STARTFALT.index("struken")] = int(s.struken)
                rad = conn.execute("SELECT id, hast_id FROM starter WHERE avdelning_id = ? AND nr = ?",
                                   (avd_id, s.nr)).fetchone()
                if rad is None:
                    cur = conn.execute(
                        f"INSERT INTO starter (avdelning_id, nr, {', '.join(_STARTFALT)}) "
                        f"VALUES (?, ?, {', '.join('?' * len(_STARTFALT))})", [avd_id, s.nr, *varden])
                    start_id = cur.lastrowid
                    nya["starter"] += 1
                else:
                    start_id = rad["id"]
                    if rad["hast_id"] and s.hast_id and rad["hast_id"] != s.hast_id:
                        log.warning("%s avd %s nr %s: hästen bytt – rensar gamla streck och odds", o.id, a.avd, s.nr)
                        for tabell in ("streck", "vinnarodds", "prognoser"):
                            conn.execute(f"DELETE FROM {tabell} WHERE start_id = ?", (start_id,))
                    # Resultatfälten skrivs bara över när det finns något nytt
                    conn.execute(
                        f"UPDATE starter SET {', '.join(f'{f} = ?' for f in _STARTFALT[:-3])}, "
                        "placering = COALESCE(?, placering), slutodds = COALESCE(?, slutodds), "
                        "km_tid = COALESCE(?, km_tid) WHERE id = ?", [*varden, start_id])
                if s.streck is not None:
                    nya["streck"] += _ny_bild(conn, "streck", "andel", start_id, o.tidpunkt, s.streck)
                if s.vinnarodds is not None and not s.struken:
                    nya["odds"] += _ny_bild(conn, "vinnarodds", "odds", start_id, o.tidpunkt, s.vinnarodds)
    return nya


def _ny_bild(conn, tabell: str, falt: str, start_id: int, tidpunkt: str, varde: float) -> int:
    sist = conn.execute(f"SELECT tidpunkt, {falt} FROM {tabell} WHERE start_id = ? ORDER BY tidpunkt DESC LIMIT 1",
                        (start_id,)).fetchone()
    if sist and (sist[0] >= tidpunkt or sist[1] == varde):
        return 0
    conn.execute(f"INSERT OR IGNORE INTO {tabell} (start_id, tidpunkt, {falt}) VALUES (?, ?, ?)",
                 (start_id, tidpunkt, varde))
    return 1


def ej_avgjorda(conn: sqlite3.Connection, nu: str) -> List[str]:
    """Omgångar vars spelstopp har passerat men som inte är avgjorda."""
    return [r[0] for r in conn.execute(
        "SELECT id FROM omgangar WHERE spelstopp < ? AND avgjord = 0 ORDER BY spelstopp", (nu,))]
