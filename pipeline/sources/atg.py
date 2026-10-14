"""ATG: V85-omgångar med lopp, hästar, streck, vinnarodds, resultat och utdelning.

Använder det öppna JSON-API som atg.se själv anropar (se DATAKALLOR.md). Ingen nyckel krävs.
Tolkningsfunktionerna (tolka_*) är rena och testas mot sparade svar i tests/fixtures.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from .. import config
from ..http import HamtningsFel, hamta_json
from ..modeller import Avdelning, Omgang, Start, ValideringsFel
from ..tid import lokal_till_utc

log = logging.getLogger(__name__)

ANTAL_AVD = {"V85": 8, "V75": 7, "V86": 8, "V64": 6, "V65": 6}
SAKNAS_ODDS = 9999      # ATG visar exakt 9999 när det inte finns odds än (högre odds anges som de är)
# Vinnaroddsen används först när vinnarpoolen har riktiga pengar. Tidigt i veckan omsätter den några hundra
# kronor och oddsen säger ingenting; vid start brukar en V85-avdelning omsätta runt en miljon.
MIN_VINNARPOOL = 100_000   # kr


# ---------- hjälpfunktioner ----------

def _rekord(r: Optional[dict]) -> Optional[str]:
    """{'code': 'aK', 'time': {'minutes': 1, 'seconds': 10, 'tenths': 7}} -> '1.10,7aK'."""
    t = (r or {}).get("time")
    if not t:
        return None
    return f"{t.get('minutes', 1)}.{t.get('seconds', 0):02d},{t.get('tenths', 0)}{r.get('code', '')}"


def _ar(stat: dict, ar: str) -> dict:
    return ((stat or {}).get("years") or {}).get(ar) or {}


def _segerproc(person: Optional[dict], ar: str) -> Optional[float]:
    y = _ar((person or {}).get("statistics"), ar)
    if not y.get("starts"):
        return None
    wp = y.get("winPercentage")
    return wp / 10000 if wp is not None else (y.get("placement") or {}).get("1", 0) / y["starts"]


def _namn(person: Optional[dict]) -> Optional[str]:
    if not person:
        return None
    namn = f"{person.get('firstName', '')} {person.get('lastName', '')}".strip()
    return namn or None


def _odds(v) -> Optional[float]:
    if not isinstance(v, (int, float)) or v <= 100 or v == SAKNAS_ODDS:
        return None
    return v / 100


def _tolka_start(s: dict, ar: str, likvid: bool) -> Start:
    h = s.get("horse") or {}
    stat = h.get("statistics") or {}
    liv = stat.get("life") or {}
    plac = liv.get("placement") or {}
    i_ar = _ar(stat, ar)
    pools = s.get("pools") or {}
    res = s.get("result") or {}
    streck = (pools.get("V85") or pools.get(next((k for k in pools if k.startswith("V")), ""), {}) or {}).get("betDistribution")
    vinnare = pools.get("vinnare") or {}
    snitt = ((stat.get("lastFiveStarts") or {}).get("averageOdds"))
    km = res.get("kmTime")
    return Start(
        nr=s["number"], hast=h.get("name") or f"Nr {s['number']}", hast_id=h.get("id"),
        alder=h.get("age"), kon=h.get("sex"),
        kusk=_namn(s.get("driver")), tranare=_namn(h.get("trainer")),
        spar=s.get("postPosition"), distans=s.get("distance"),
        struken=bool(s.get("scratched")),
        livs_starter=liv.get("starts"), livs_segrar=plac.get("1"),
        livs_platser=sum(plac.get(k, 0) for k in ("1", "2", "3")) if plac else None,
        ar_starter=i_ar.get("starts"), ar_segrar=(i_ar.get("placement") or {}).get("1"),
        intjant=h.get("money"), rekord=_rekord(h.get("record")),
        snittodds_5=snitt / 100 if snitt else None,
        kusk_segerproc=_segerproc(s.get("driver"), ar),
        tranare_segerproc=_segerproc(h.get("trainer"), ar),
        streck=streck / 10000 if isinstance(streck, (int, float)) else None,
        vinnarodds=_odds(vinnare.get("finalOdds") or vinnare.get("odds")) if likvid else None,
        placering=res.get("place") if res else None,
        slutodds=res.get("finalOdds"),
        km_tid=f"{km.get('minutes', 1)}.{km.get('seconds', 0):02d},{km.get('tenths', 0)}" if km else None,
    )


# ---------- tolkning ----------

def tolka_spel(spel: dict, hamtad: str) -> Omgang:
    """Tolka ett spel från /games/{id}. `hamtad` (UTC) används om poolen saknar tidsstämpel.

    Kastar ValideringsFel om omgången är trasig. Strecken kontrolleras per avdelning: en avdelning
    där strecken inte summerar till ungefär 100 % får inga streck, men omgången sparas ändå.
    """
    try:
        spel_id = spel["id"]
        spelform = spel_id.split("_")[0]
        lopp = spel["races"]
    except (KeyError, TypeError, AttributeError) as e:
        raise ValideringsFel(f"spelet saknar grundfält: {e}") from e
    antal = ANTAL_AVD.get(spelform)
    if antal is None or len(lopp) != antal:
        raise ValideringsFel(f"{spel_id}: {len(lopp)} lopp, väntade {antal}")

    pool = (spel.get("pools") or {}).get(spelform) or {}
    tidpunkt = lokal_till_utc(pool["timestamp"].replace(" ", "T")) if pool.get("timestamp") else hamtad
    datum = lopp[0].get("date") or spel_id.split("_")[1]
    ar = datum[:4]

    avdelningar: List[Avdelning] = []
    for i, r in enumerate(sorted(lopp, key=lambda r: r.get("startTime") or ""), start=1):
        oms = ((r.get("pools") or {}).get("vinnare") or {}).get("turnover")
        likvid = oms is None or oms / 100 >= MIN_VINNARPOOL
        starter = [_tolka_start(s, ar, likvid) for s in r.get("starts") or []]
        if len(starter) < 2:
            raise ValideringsFel(f"{spel_id}: avdelning {i} har {len(starter)} hästar")
        if len({s.nr for s in starter}) != len(starter):
            raise ValideringsFel(f"{spel_id}: avdelning {i} har dubbla startnummer")
        summa = sum(s.streck or 0 for s in starter)
        if summa and not 0.97 <= summa <= 1.03:
            log.warning("%s avd %s: strecken summerar till %.3f – sparar inga streck", spel_id, i, summa)
            for s in starter:
                s.streck = None
        avgjort = r.get("status") == "results" and any(s.placering for s in starter)
        avdelningar.append(Avdelning(
            avd=i, lopp_id=r["id"], loppnr=r.get("number"), namn=r.get("name"),
            distans=r.get("distance"), startmetod=r.get("startMethod"),
            starttid=lokal_till_utc(r["startTime"]) if r.get("startTime") else None,
            starter=starter,
            vinnare=sorted(s.nr for s in starter if s.placering == 1) if avgjort else [],
        ))

    utdelning, vinnande = {}, {}
    res = pool.get("result") or {}
    for ratt, u in (res.get("payouts") or {}).items():
        utdelning[int(ratt)] = (u.get("payout") or 0) / 100
        vinnande[int(ratt)] = u.get("systems")
    avgjord = (spel.get("status") == "results" and bool(utdelning)
               and all(a.vinnare for a in avdelningar)
               and (res.get("boostInfo") or {}).get("resultComplete", True))

    return Omgang(
        id=spel_id, spelform=spelform, datum=datum,
        bana=((lopp[0].get("track") or {}).get("name")) or "",
        spelstopp=avdelningar[0].starttid or tidpunkt,
        status=spel.get("status") or "",
        omsattning=pool["turnover"] / 100 if pool.get("turnover") else None,
        tidpunkt=tidpunkt, avdelningar=avdelningar,
        utdelning=utdelning if avgjord else {}, vinnande_rader=vinnande if avgjord else {},
        avgjord=avgjord,
    )


# ---------- hämtning ----------

def hamta_produkt(spelform: str = config.SPELFORM) -> dict:
    """{'upcoming': [...], 'results': [...]} – kommande och nyss avgjorda omgångar."""
    data, _ = hamta_json(f"{config.ATG_BASE}/products/{spelform}")
    if not isinstance(data, dict) or "upcoming" not in data:
        raise HamtningsFel(f"Oväntat svar från /products/{spelform}")
    return data


def hamta_spel(spel_id: str) -> dict:
    data, _ = hamta_json(f"{config.ATG_BASE}/games/{spel_id}")
    if not isinstance(data, dict) or not data.get("races"):
        raise HamtningsFel(f"Spelet {spel_id} saknar lopp")
    return data


def spel_for_dag(datum: str, spelform: str = config.SPELFORM) -> List[str]:
    """Spel-id:n för en viss dag, t.ex. ['V85_2026-10-17_16_5']."""
    data, _ = hamta_json(f"{config.ATG_BASE}/calendar/day/{datum}")
    return [g["id"] for g in ((data or {}).get("games") or {}).get(spelform, []) if g.get("id")]
