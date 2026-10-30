"""Hästkoll steg 1: utrustning och de senaste starterna (ATG /races/{id}/extended)."""
from pipeline import export, lagring
from pipeline.sources import atg
from tests.conftest import las_fixture


def test_tolka_hastinfo():
    info = atg.tolka_hastinfo(las_fixture("atg_lopp_extended.json"))
    h = info[1]
    assert (h["skor_fram"], h["skor_bak"], h["skor_andrad"]) == (True, True, False)
    assert h["vagn"] == "Vanlig" and h["vagn_andrad"] is True
    assert len(h["tidigare"]) == 5 and all(t["datum"] < "2025-11-01" for t in h["tidigare"])   # ingen senare start
    senast = h["tidigare"][0]
    assert senast["datum"] == "2025-10-25" and senast["galopp"] and senast["diskad"] and senast["placering"] is None
    assert senast["odds"] == 12.48 and senast["kusk"] == "Claes Sjöström" and senast["vagn"] == "Amerikansk"


def test_spara_och_exportera(conn):
    lagring.spara_omgang(conn, atg.tolka_spel(las_fixture("atg_v85_kommande.json"), "x"))
    avd_id = conn.execute("SELECT id FROM avdelningar WHERE avd = 1").fetchone()[0]
    info = atg.tolka_hastinfo(las_fixture("atg_lopp_extended.json"))
    assert lagring.spara_hastinfo(conn, avd_id, info, "2026-10-17T10:00:00Z") == 3
    assert lagring.spara_hastinfo(conn, avd_id, info, "2026-10-17T11:00:00Z") == 3          # ersätts, inga dubbletter
    assert conn.execute("SELECT COUNT(*) FROM tidigare_starter").fetchone()[0] == sum(len(i["tidigare"]) for i in info.values())
    h = export.omgang_data(conn, "V85_2026-10-17_16_5")["avdelningar"][0]["hastar"][0]
    assert h["utrustning"] == {"skor_fram": True, "skor_bak": True, "skor_andrad": False, "vagn": "Vanlig", "vagn_andrad": True}
    assert h["tidigare"][0]["datum"] == "2025-10-25" and h["tidigare"][0]["diskad"] is True



def test_forstapris_underlag_och_sparad_kommentar_behalls(conn):
    assert atg.tolka_forstapris("Pris: 125.000-62.500-34.000 kr (8 prisplacerade)") == 125000.0
    info = atg.tolka_hastinfo(las_fixture("atg_lopp_extended.json"))
    t = info[1]["tidigare"][0]
    assert t["underlag"] and t["land"] and t["forstapris"] > 0
    lagring.spara_omgang(conn, atg.tolka_spel(las_fixture("atg_v85_kommande.json"), "x"))
    avd_id = conn.execute("SELECT id FROM avdelningar WHERE avd = 1").fetchone()[0]
    lagring.spara_hastinfo(conn, avd_id, info, "x", 125000.0)
    conn.execute("UPDATE tidigare_starter SET kommentar = 'Sparad kommentar.' WHERE nr = 1")
    lagring.spara_hastinfo(conn, avd_id, info, "y", 125000.0)          # ATG visar inte kommentaren längre
    assert conn.execute("SELECT COUNT(*) FROM tidigare_starter WHERE kommentar = 'Sparad kommentar.'").fetchone()[0] == 3
    assert conn.execute("SELECT forstapris FROM avdelningar WHERE id = ?", (avd_id,)).fetchone()[0] == 125000.0
