"""Driftvakten: körs sist i varje pipelinekörning och säger till om driften inte går som planerat.

Fel i en körning mejlar GitHub redan om, men AI-stegen får misslyckas utan att körningen gör det – därför
larmar vakten också när alla AI-anrop misslyckats flera körningar i rad (som i november 2026, när Google slutade
ta emot ett fält och AI låg nere i två veckor utan att det märktes). Det som annars inte syns är när körningarna går för sent – slutar
cron-job.org starta pipelinen tar GitHubs timvisa start över, med upp till en timmes försening, och tiderna före
spelstopp missas. Workflowet öppnar ett GitHub-ärende (etiketten driftlarm, mejl till ägaren) när det finns
problem och stänger det när allt går som det ska igen.

    python -m pipeline vakt      # skriver ett problem per rad, inget om allt är i ordning
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from . import schema

MAX_FORSENING = timedelta(minutes=45)      # cron-job.org startar var 15:e minut; GitHubs cron ensam ger upp till 60+
MAX_ALDER = timedelta(hours=24)            # en sen körning längre bak räknas inte (en senare har gått i tid)
RESULTAT_EFTER = timedelta(hours=12)       # efter spelstopp: då ska resultat och utdelning finnas
AI_MAX_MISSLYCKADE = 3                     # körningar i rad där alla AI-anrop misslyckades (ungefär ett dygn)


def _tid(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def spara_korning(conn: sqlite3.Connection, planerad: datetime, kord: datetime) -> None:
    """Anropas av `planerad` när en planerad tid körs."""
    varde = json.dumps({"planerad": planerad.strftime("%Y-%m-%dT%H:%M:%SZ"), "kord": kord.strftime("%Y-%m-%dT%H:%M:%SZ")})
    with conn:
        conn.execute("""INSERT INTO installningar (nyckel, varde, uppdaterad) VALUES ('planerad_korning', ?, ?)
                        ON CONFLICT(nyckel) DO UPDATE SET varde = excluded.varde, uppdaterad = excluded.uppdaterad""",
                     (varde, kord.strftime("%Y-%m-%dT%H:%M:%SZ")))


def _svensk(t: datetime) -> str:
    return t.astimezone(schema.SVENSK_TID).strftime("%a %d %b %H:%M")


def kontrollera(conn: sqlite3.Connection, nu: Optional[datetime] = None) -> List[str]:
    nu = nu or datetime.now(timezone.utc)
    problem = []
    r = conn.execute("SELECT varde FROM installningar WHERE nyckel = 'planerad_korning'").fetchone()
    if r:
        k = json.loads(r[0])
        planerad, kord = _tid(k["planerad"]), _tid(k["kord"])
        if kord - planerad > MAX_FORSENING and nu - kord < MAX_ALDER:
            problem.append(
                f"Körningen planerad {_svensk(planerad)} gick först {_svensk(kord)} (svensk tid), "
                f"{int((kord - planerad).total_seconds() // 60)} minuter sent. Kontrollera att jobbet i cron-job.org är "
                "aktivt och att nyckeln inte har gått ut (README, \"Extern start\").")
    gransen = (nu - RESULTAT_EFTER).strftime("%Y-%m-%dT%H:%M:%SZ")
    for (omgang,) in conn.execute("SELECT id FROM omgangar WHERE avgjord = 0 AND spelstopp < ? AND spelstopp > ?",
                                  (gransen, (nu - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ"))):
        problem.append(f"{omgang} saknar resultat mer än 12 timmar efter spelstopp – se loggen för steget resultat.")
    r = conn.execute("SELECT varde FROM installningar WHERE nyckel = 'status:ai'").fetchone()
    ai = json.loads(r[0]) if r else {}
    if ai.get("konfigurerad") is False:
        problem.append(f"AI är inte igång: {ai.get('orsak')}. Kontrollera GEMINI_API_KEY bland GitHub Secrets.")
    elif ai.get("misslyckade_korningar", 0) >= AI_MAX_MISSLYCKADE:
        problem.append(f"Alla AI-anrop har misslyckats {ai['misslyckade_korningar']} körningar i rad – inga "
                       "kommentarer eller Hästkoll. Se loggen för steget Kör pipelinen (Gemini svarade …).")
    return problem
