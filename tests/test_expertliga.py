"""Expertligan: experternas system rättade mot utdelningen (avgjord fixtur med påhittade system)."""
from pipeline import expertliga, export, lagring
from pipeline.modeller import Expertsystem
from pipeline.sources import atg
from tests.conftest import las_fixture

SPEL = "V85_2026-10-10_5_6"
VINNARE = [1, 5, 7, 15, 7, 5, 3, 9]              # avd 1–8 i fixturen; utdelning 5–8 rätt: 7, 32, 846, 64 035 kr


def _system(namn, kalla, val, id_):
    lopp = [f"2026-10-10_5_{6 + i}" for i in range(8)]
    return Expertsystem(id=id_, omgang_id=SPEL, kalla=kalla, namn=namn, artikel=None,
                        rader=None, val={lopp[i]: nr for i, nr in enumerate(val) if nr})


def _fyll(conn):
    lagring.spara_omgang(conn, atg.tolka_spel(las_fixture("atg_v85_avgjord.json"), "x"))
    alla_ratt = [[v, v + 1] if i < 2 else [v] for i, v in enumerate(VINNARE)]          # 4 rader: 8, 7, 7 och 6 rätt
    sju = [[v + 1] if i == 0 else [v] for i, v in enumerate(VINNARE)]                    # 1 rad, 7 rätt
    harry = [[v] if i < 5 else None for i, v in enumerate(VINNARE)]                      # 3 avdelningar åt Harry
    lagring.spara_expertsystem(conn, [
        _system("ÅKE OLSSONS LILLA SYSTEMFÖRSLAG - V85 lördag", "ATG:s experter", alla_ratt, "a" * 36),
        _system("Mats E Djuse", "Fem tippar", sju, "b" * 36),
        _system("TR Media (lilla systemet)", "ATG:s experter", harry, "c" * 36)], "x")


def test_radfordelning():
    # avd 1: 2 hästar varav vinnaren, avd 2: 1 häst som förlorade, avd 3: 3 hästar med vinnaren
    assert expertliga.radfordelning({1: [1, 2], 2: [4], 3: [5, 6, 7]}, {1: [1], 2: [3], 3: [7]}) == {0: 2, 1: 3, 2: 1}


def test_ligans_namn():
    assert expertliga.ligans_namn("FERNLUNDS STORA SYSTEMFÖRSLAG - V85 söndag") == "Patrik Fernlund · stora"
    assert expertliga.ligans_namn("Patrik Fernlund stora systemförslag") == "Patrik Fernlund · stora"
    assert expertliga.ligans_namn("Åke Olssons lilla systemförslag V85 - lördag") == "Åke Olsson · lilla"
    assert expertliga.ligans_namn("TR Media (lilla systemet)") == "TR Media · lilla"
    assert expertliga.ligans_namn("Mats E Djuse") == "Mats E Djuse"


def test_ratta_omgang(conn):
    _fyll(conn)
    r = {x["liga"]: x for x in expertliga.ratta_omgang(conn, SPEL)}
    a = r["Åke Olsson · lilla"]
    assert (a["rader"], a["insats"], a["ratt"], a["spikar"], a["holl"]) == (4, 2.0, 8, 6, 6)
    assert a["tillbaka"] == 64035 + 2 * 846 + 32
    assert r["Mats E Djuse"]["ratt"] == 7 and r["Mats E Djuse"]["tillbaka"] == 846.0
    assert r["Mats E Djuse"]["spikar"] == 8 and r["Mats E Djuse"]["holl"] == 7
    assert "ratt" not in r["TR Media · lilla"] and r["TR Media · lilla"]["holl"] == 5     # Harry: bara spikarna


def test_liga_och_export(conn):
    _fyll(conn)
    l = expertliga.liga(conn, SPEL)
    assert l["omgangar"] == 1 and [d["namn"] for d in l["deltagare"]][0] == "Åke Olsson · lilla"
    assert {d["namn"] for d in l["deltagare"]} == {"Åke Olsson · lilla", "TR Media · lilla", "Fem tippar – alla gäster"}
    assert [d["namn"] for d in l["gaster"]] == ["Mats E Djuse"] and len(l["senaste"]) == 3
    tr = next(d for d in l["deltagare"] if d["namn"] == "TR Media · lilla")
    assert tr["insats"] == 0 and tr["ratt_snitt"] is None and tr["holl"] == 5
    assert expertliga.liga(conn, None)["senaste"] == []
