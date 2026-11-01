from datetime import datetime, timezone

from pipeline import schema


def utc(s):
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


LORDAG = [utc("2026-10-31T14:02:07")]      # V85 Bjerke, spelstopp 15:02 svensk vintertid
SONDAG = [utc("2026-11-01T14:00:19")]      # V85 Solvalla, söndag


def test_senaste_planerade_i_svensk_tid_sommar_och_vinter():
    # Lördag 17 okt 2026, spelstopp 15:00 sommartid (13:00 UTC); 11:26 svensk tid → 11:00 = 09:00 UTC
    assert schema.senaste_planerade(utc("2026-10-17T09:26:00"), [utc("2026-10-17T13:00:00")]) == utc("2026-10-17T09:00:00")
    # Lördag 31 okt 2026 (vintertid) 14:55 svensk tid = 13:55 UTC → 14:45 svensk = 13:45 UTC
    assert schema.senaste_planerade(utc("2026-10-31T13:55:00"), LORDAG) == utc("2026-10-31T13:45:00")
    # Tisdag 07:00 svensk tid → måndagens 22:30
    assert schema.senaste_planerade(utc("2026-10-13T05:00:00")) == utc("2026-10-12T20:30:00")


def test_tavlingsdagens_tider_fran_spelstopp_pa_kvartar():
    svensk = [t.astimezone(schema.SVENSK_TID).strftime("%H:%M") for t in schema.tavlingsdagens_tider(LORDAG[0])]
    assert svensk == ["11:00", "13:00", "14:00", "14:30", "14:45", "15:45", "16:15"]
    assert all(t < LORDAG[0] for t in schema.tavlingsdagens_tider(LORDAG[0])[:5])   # före spelstopp trots 15:02


def test_omgang_pa_sondag_far_tavlingsdagens_tider():
    nu = utc("2026-11-01T13:50:00")                                    # söndag 14:50 svensk tid
    assert schema.senaste_planerade(nu) == utc("2026-11-01T07:00:00")  # utan omgången: bara 08:00
    assert schema.senaste_planerade(nu, SONDAG) == utc("2026-11-01T13:45:00")
    assert schema.forfallen("2026-11-01T13:30:00Z", nu, SONDAG) == utc("2026-11-01T13:45:00")
    # Omgångar mer än en vecka bakåt påverkar inget
    assert schema.senaste_planerade(utc("2026-11-10T05:00:00"), SONDAG) == utc("2026-11-09T21:30:00")


def test_forfallen_kor_bara_en_gang_per_planerad_tid():
    nu, ss = utc("2026-10-17T09:26:00"), [utc("2026-10-17T13:00:00")]
    assert schema.forfallen(None, nu, ss) == utc("2026-10-17T09:00:00")
    assert schema.forfallen("2026-10-16T20:30:00Z", nu, ss) == utc("2026-10-17T09:00:00")   # missad tid tas igen
    assert schema.forfallen("2026-10-17T09:00:00Z", nu, ss) is None                          # redan körd
    assert schema.forfallen("2026-10-17T09:00:00Z", utc("2026-10-17T10:26:00"), ss) is None  # ingen ny tid än


def test_planerad_kor_en_gang(tmp_path, monkeypatch):
    from pipeline import __main__ as cli
    monkeypatch.setenv("TRAV_DB", str(tmp_path / "t.db"))
    monkeypatch.setattr(cli.db.config, "DB_PATH", tmp_path / "t.db")
    korda = []
    monkeypatch.setattr(cli, "steg_atg", lambda conn: korda.append("atg") or True)
    monkeypatch.setattr(cli, "steg_experter", lambda conn: None)
    monkeypatch.setattr(cli, "steg_resultat", lambda conn: True)
    monkeypatch.setattr(cli, "steg_kommentarer", lambda conn: None)
    monkeypatch.setattr(cli.export, "exportera_allt", lambda conn: None)
    assert cli.main(["planerad"]) == 0 and korda == ["atg"]
    assert cli.main(["planerad"]) == 0 and korda == ["atg"]           # samma planerade tid körs inte igen
