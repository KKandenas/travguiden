"""Det planerade uppdateringsschemat, i svensk tid (sommar- och vintertid sköts automatiskt).

GitHubs schemalagda körningar kan bli flera timmar sena eller utebli. Därför startas pipelinen ofta
(var 15:e minut av cron-job.org, och varje timme av GitHub) med kommandot `planerad`, som bara gör en riktig
uppdatering när en planerad tid nedan har passerats och inte körts än. Övriga starter avslutas direkt utan att
anropa några API:er. Samma upplägg som i Stryktipsguiden.

Tävlingsdagens tider räknas från omgångens spelstopp, inte från veckodagen: söndagens V85 den 1 november 2026
fick annars bara körningen 08:00 och spelades med sju timmar gamla streck och utan vinnarodds.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Iterable, List, Optional
from zoneinfo import ZoneInfo

SVENSK_TID = ZoneInfo("Europe/Stockholm")

ALLA_DAGAR = ["08:00", "18:30", "22:30"]       # ny omgång, kvällsomgångar och streck, resultat och utdelning
# Tävlingsdagen, i minuter från spelstopp: vinnarpoolen får pengar först på tävlingsdagen, och strecken rör sig mest
# sista timmarna. Efter spelstopp: resultat och utdelning. Spelstopp 15:00 ger 11:00, 13:00, 14:00, 14:30, 14:45,
# 15:45 och 16:15.
FORE_SPELSTOPP = [240, 120, 60, 30, 15]
EFTER_SPELSTOPP = [45, 75]
FONSTER = timedelta(days=8)                    # så långt bakåt en missad tid kan tas igen


def _till_kvart(t: datetime) -> datetime:
    """Avrunda nedåt till kvart. cron-job.org startar på kvartar, och en tid mellan två starter tas först vid nästa
    – 14:47 skulle bli 15:00, efter spelstopp (som 14:50 blev 24 oktober 2026)."""
    return t.replace(minute=t.minute - t.minute % 15, second=0, microsecond=0)


def tavlingsdagens_tider(spelstopp: datetime) -> List[datetime]:
    """Planerade tider (UTC) kring en omgångs spelstopp."""
    return [_till_kvart(spelstopp + timedelta(minutes=m)) for m in [-m for m in FORE_SPELSTOPP] + EFTER_SPELSTOPP]


def senaste_planerade(nu: datetime, spelstopp: Iterable[datetime] = ()) -> datetime:
    """Den senaste planerade tiden som har passerat (UTC): de fasta tiderna varje dag och tävlingsdagens tider för
    omgångarna i `spelstopp`."""
    lokal = nu.astimezone(SVENSK_TID)
    kandidater = []
    for dagar_bakat in range(8):
        dag = (lokal - timedelta(days=dagar_bakat)).date()
        for klocka in ALLA_DAGAR:
            h, m = map(int, klocka.split(":"))
            kandidater.append(datetime.combine(dag, time(h, m), tzinfo=SVENSK_TID))
    for s in spelstopp:
        kandidater += tavlingsdagens_tider(s)
    return max(t for t in kandidater if nu - FONSTER <= t <= nu).astimezone(timezone.utc)


def forfallen(senast_kord: Optional[str], nu: datetime, spelstopp: Iterable[datetime] = ()) -> Optional[datetime]:
    """Den planerade tid som ska köras nu, eller None om den senaste redan är körd."""
    tid = senaste_planerade(nu, spelstopp)
    if senast_kord:
        kord = datetime.fromisoformat(senast_kord.replace("Z", "+00:00"))
        if kord >= tid:
            return None
    return tid
