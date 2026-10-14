from pipeline import export, lagring
from pipeline.model import modeller
from pipeline.sources import atg
from tests.conftest import las_fixture


def _fyll(conn):
    for f in ("atg_v85_kommande.json", "atg_v85_avgjord.json"):
        lagring.spara_omgang(conn, atg.tolka_spel(las_fixture(f), "2026-10-14T08:00:00Z"))
    modeller.berakna_prognoser(conn, alla=True)


def test_omgang_data(conn):
    _fyll(conn)
    d = export.omgang_data(conn, "V85_2026-10-17_16_5")
    assert len(d["avdelningar"]) == 8 and d["omgang"]["bana"] == "Gävle"
    for a in d["avdelningar"]:
        chanser = [h["chans"] for h in a["hastar"] if not h.get("struken")]
        assert abs(sum(chanser) - 1) < 0.01
        assert all(h["chans"] is None for h in a["hastar"] if h.get("struken"))


def test_dolj_resultat(conn):
    _fyll(conn)
    d = export.omgang_data(conn, "V85_2026-10-10_5_6", dolj_resultat=True)
    assert d["utdelning"] == {} and not d["omgang"]["avgjord"]
    assert all("vinnare" not in a and all("placering" not in h for h in a["hastar"]) for a in d["avdelningar"])


def test_historik(conn):
    _fyll(conn)
    h = export.historik(conn)
    assert [o["id"] for o in h["omgangar"]] == ["V85_2026-10-10_5_6"]
    o = h["omgangar"][0]
    assert len(o["avd"]) == 8 and o["utdelning"][8] == 64035.0
    assert o["avd"][0]["v"] == [1] and all(len(r) == 3 for r in o["avd"][0]["h"])


def test_experter_i_exporten(conn):
    from pipeline.sources import atgtips
    _fyll(conn)
    post = {"post_id": "x", "kupong_id": "1956601d-126e-4258-be6e-fdef45f1cfe0", "spel_id": "V85_2026-10-17_16_5",
            "titel": "Kupong 5", "artikel": "Fem tippar V85®", "kalla": atgtips.KALLA_FEM}
    e = atgtips.tolka_kupong(las_fixture("atgtips_kupong.json"), post, "Nicklas Bäckström")
    lagring.spara_expertsystem(conn, [e], "2026-10-14T09:00:00Z")
    modeller.berakna_prognoser(conn)
    d = export.omgang_data(conn, "V85_2026-10-17_16_5")
    assert d["experter"] == [{"namn": "Nicklas Bäckström", "kalla": "Fem tippar", "artikel": "Fem tippar V85®", "rader": 240}]
    h = {x["nr"]: x for x in d["avdelningar"][1]["hastar"]}
    assert h[3]["experter"] == [0] and h[1]["experter"] == []
    assert h[3]["chans_exp"] > h[3]["chans"]
