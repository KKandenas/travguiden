"""Driftvakten: sena planerade körningar och omgångar utan resultat."""
from datetime import datetime, timezone

from pipeline import vakt


def utc(s):
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def test_sen_korning_ger_larm_tills_en_korning_gar_i_tid(conn):
    assert vakt.kontrollera(conn, utc("2026-11-07T14:00:00")) == []                  # inget kört än
    vakt.spara_korning(conn, utc("2026-11-07T12:30:00"), utc("2026-11-07T13:23:00"))   # 53 min sent
    larm = vakt.kontrollera(conn, utc("2026-11-07T13:30:00"))
    assert len(larm) == 1 and "53 minuter sent" in larm[0] and "cron-job.org" in larm[0]
    vakt.spara_korning(conn, utc("2026-11-07T13:00:00"), utc("2026-11-07T13:02:00"))
    assert vakt.kontrollera(conn, utc("2026-11-07T13:05:00")) == []
    vakt.spara_korning(conn, utc("2026-11-07T12:30:00"), utc("2026-11-07T13:23:00"))
    assert vakt.kontrollera(conn, utc("2026-11-09T13:30:00")) == []                  # för länge sedan


def test_omgang_utan_resultat_efter_tolv_timmar(conn):
    conn.execute("""INSERT INTO omgangar (id, spelform, datum, bana, spelstopp, status, avgjord)
                    VALUES ('V85_2026-11-07_5_5', 'V85', '2026-11-07', 'Solvalla', '2026-11-07T14:00:00Z', 'x', 0)""")
    assert vakt.kontrollera(conn, utc("2026-11-07T22:00:00")) == []
    assert "saknar resultat" in vakt.kontrollera(conn, utc("2026-11-08T03:00:00"))[0]
    assert vakt.kontrollera(conn, utc("2026-11-20T03:00:00")) == []                  # äldre än en vecka


def test_ai_som_misslyckas_flera_korningar_i_rad_ger_larm(conn, monkeypatch):
    from pipeline import __main__ as cli
    from pipeline.ai import klient

    def korning(lyckade, misslyckade):
        monkeypatch.setattr(cli, "_ai_fore", None)                       # ny körning
        monkeypatch.setattr(klient, "KORNING", {"lyckade": lyckade, "misslyckade": misslyckade, "modeller": {},
                                                "stoppad": None})
        cli.spara_ai_status(conn)
        cli.spara_ai_status(conn)                                        # anropas flera gånger per körning
        return vakt.kontrollera(conn, utc("2026-11-18T08:00:00"))

    monkeypatch.setattr(klient, "tillganglig", lambda: (True, ""))
    assert korning(0, 3) == [] and korning(0, 3) == []
    larm = korning(0, 3)
    assert len(larm) == 1 and "3 körningar i rad" in larm[0]
    assert korning(0, 0) == larm                                         # ingen AI i körningen: oförändrat
    assert korning(2, 1) == []                                           # något lyckades: räkningen börjar om
    monkeypatch.setattr(klient, "tillganglig", lambda: (False, "GEMINI_API_KEY saknas"))
    assert "inte igång" in korning(0, 0)[0]
