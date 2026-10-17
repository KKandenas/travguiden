from datetime import datetime, timezone

from pipeline import schema


def utc(s):
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def test_senaste_planerade_i_svensk_tid_sommar_och_vinter():
    # Lördag 17 okt 2026 11:26 svensk sommartid (09:26 UTC) → lördag 11:00 = 09:00 UTC
    assert schema.senaste_planerade(utc("2026-10-17T09:26:00")) == utc("2026-10-17T09:00:00")
    # Lördag 31 okt 2026 (vintertid) 14:55 svensk tid = 13:55 UTC → 14:50 svensk = 13:50 UTC
    assert schema.senaste_planerade(utc("2026-10-31T13:55:00")) == utc("2026-10-31T13:50:00")
    # Tisdag 07:00 svensk tid → måndagens 22:30
    assert schema.senaste_planerade(utc("2026-10-13T05:00:00")) == utc("2026-10-12T20:30:00")


def test_forfallen_kor_bara_en_gang_per_planerad_tid():
    nu = utc("2026-10-17T09:26:00")
    assert schema.forfallen(None, nu) == utc("2026-10-17T09:00:00")
    assert schema.forfallen("2026-10-16T20:30:00Z", nu) == utc("2026-10-17T09:00:00")   # missad tid tas igen
    assert schema.forfallen("2026-10-17T09:00:00Z", nu) is None                          # redan körd
    assert schema.forfallen("2026-10-17T09:00:00Z", utc("2026-10-17T10:26:00")) is None  # ingen ny tid än


def test_lordagens_tider_fram_till_spelstopp():
    tider = [t for d, t in schema.PLANERADE if d == 5]
    assert {"14:30", "14:50"} <= set(tider) and sum(t < "15:00" for t in tider) >= 6
    assert all(any(d == dag for d, _ in schema.PLANERADE) for dag in range(7))   # V-spel även andra dagar


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
