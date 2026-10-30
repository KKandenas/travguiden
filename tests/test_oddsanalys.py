"""Oddsanalysen (vinnaroddsens vikt och sena pengar) på en avgjord omgång med påhittade förhandsodds."""
from pipeline import lagring
from pipeline.model import modeller, oddsanalys
from pipeline.sources import atg
from tests.conftest import las_fixture


def test_oddsanalys_med_forhandsodds(conn):
    o = atg.tolka_spel(las_fixture("atg_v85_avgjord.json"), "x")
    lagring.spara_omgang(conn, o)
    # Två bilder före spelstopp för varje häst: oddsen faller för startnummer 1, stiger för övriga
    for r in conn.execute("SELECT s.id, s.nr FROM starter s WHERE s.struken = 0").fetchall():
        conn.execute("INSERT INTO vinnarodds VALUES (?, '2026-10-10T11:00:00Z', ?)", (r["id"], 8.0))
        conn.execute("INSERT INTO vinnarodds VALUES (?, '2026-10-10T12:50:00Z', ?)", (r["id"], 4.0 if r["nr"] == 1 else 9.0))
    modeller.berakna_prognoser(conn, alla=True)
    lopp = oddsanalys.lopp_med_odds(conn, "2026-10-01")
    assert len(lopp) == 8 and all(h["vinnarodds"] for h in lopp[0]["hastar"])
    g = oddsanalys.sena_pengar(lopp)
    assert g["kraftigt oddsfall (chansen +30 %)"][3] == 8          # en häst per avdelning
    text = oddsanalys.rapport(conn, "2026-10-01")
    assert "1 omgångar" in text and "Sena pengar" in text
