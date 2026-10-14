import copy

from pipeline import lagring
from pipeline.sources import atg
from tests.conftest import las_fixture


def _omgang(fil="atg_v85_kommande.json", **andra):
    d = copy.deepcopy(las_fixture(fil))
    if "timestamp" in andra:
        d["pools"]["V85"]["timestamp"] = andra["timestamp"]
    return d


def test_idempotent(conn):
    o = atg.tolka_spel(_omgang(), "2026-10-14T08:00:00Z")
    forsta = lagring.spara_omgang(conn, o)
    andra = lagring.spara_omgang(conn, o)
    assert forsta["starter"] == 98 and forsta["streck"] > 0
    assert andra == {"starter": 0, "streck": 0, "odds": 0}
    assert conn.execute("SELECT COUNT(*) FROM avdelningar").fetchone()[0] == 8


def test_ny_bild_bara_nar_strecken_andrats(conn):
    lagring.spara_omgang(conn, atg.tolka_spel(_omgang(), "x"))
    d = _omgang(timestamp="2026-10-15 10:00:00")
    d["races"][0]["starts"][0]["pools"]["V85"]["betDistribution"] = 1014
    d["races"][0]["starts"][1]["pools"]["V85"]["betDistribution"] = 5071
    nya = lagring.spara_omgang(conn, atg.tolka_spel(d, "x"))
    assert nya["streck"] == 2


def test_resultat_och_utdelning(conn):
    o = atg.tolka_spel(_omgang("atg_v85_avgjord.json"), "x")
    lagring.spara_omgang(conn, o)
    rad = conn.execute("SELECT avgjord FROM omgangar").fetchone()
    assert rad[0] == 1
    assert conn.execute("SELECT kr FROM utdelning WHERE ratt = 8").fetchone()[0] == 64035.0
    assert conn.execute("SELECT vinnare FROM avdelningar WHERE avd = 4").fetchone()[0] == "15"
    assert lagring.ej_avgjorda(conn, "2030-01-01T00:00:00Z") == []
