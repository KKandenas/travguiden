"""Det planerade uppdateringsschemat, i svensk tid (sommar- och vintertid sköts automatiskt).

GitHubs schemalagda körningar kan bli flera timmar sena eller utebli. Därför startas pipelinen ofta
(varje timme, och var 20:e minut på lördagar) med kommandot `planerad`, som bara gör en riktig uppdatering
när en planerad tid nedan har passerats och inte körts än. Övriga starter avslutas direkt utan att anropa
några API:er. Samma upplägg som i Stryktipsguiden.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import List, Optional, Tuple
from zoneinfo import ZoneInfo

SVENSK_TID = ZoneInfo("Europe/Stockholm")

ALLA_DAGAR = ["08:00", "18:30", "22:30"]       # ny omgång, kvällsomgångar och streck, resultat och utdelning
# Lördag fram till spelstopp (oftast 15:00, ibland senare): vinnarpoolen får pengar först på tävlingsdagen.
# Tiderna ligger på kvartar, eftersom cron-job.org startar var 15:e minut (:00, :15, :30, :45). En tid mellan två
# starter tas först vid nästa start – 14:50 blev därför 15:00, efter spelstopp (24 oktober 2026).
LORDAG = ["11:00", "13:00", "14:00", "14:30", "14:45", "15:45", "16:15"]

# (veckodag, klockslag) i svensk tid; måndag = 0
PLANERADE: List[Tuple[int, str]] = sorted(
    [(d, t) for d in range(7) for t in ALLA_DAGAR] + [(5, t) for t in LORDAG])


def senaste_planerade(nu: datetime) -> datetime:
    """Den senaste planerade tiden som har passerat (UTC)."""
    lokal = nu.astimezone(SVENSK_TID)
    kandidater = []
    for dagar_bakat in range(8):
        dag = (lokal - timedelta(days=dagar_bakat)).date()
        for veckodag, klocka in PLANERADE:
            if dag.weekday() == veckodag:
                h, m = map(int, klocka.split(":"))
                t = datetime.combine(dag, time(h, m), tzinfo=SVENSK_TID)
                if t <= lokal:
                    kandidater.append(t)
    return max(kandidater).astimezone(timezone.utc)


def forfallen(senast_kord: Optional[str], nu: datetime) -> Optional[datetime]:
    """Den planerade tid som ska köras nu, eller None om den senaste redan är körd."""
    tid = senaste_planerade(nu)
    if senast_kord:
        kord = datetime.fromisoformat(senast_kord.replace("Z", "+00:00"))
        if kord >= tid:
            return None
    return tid
