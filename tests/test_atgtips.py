"""Experternas system: CMS-poster, namn ur artikeln och kupongerna (sparade svar i tests/fixtures)."""
import pytest

from pipeline import lagring
from pipeline.model import data, modeller
from pipeline.modeller import ValideringsFel
from pipeline.sources import atg, atgtips
from tests.conftest import FIXTURES, las_fixture

SPEL = "V85_2026-10-17_16_5"


def test_nyckel_ur_html():
    url, nyckel = atgtips.tolka_nyckel((FIXTURES / "atgtips_sida.html").read_text())
    assert url.endswith("/spaces/test/environments/master") and nyckel == "fejkad-nyckel-for-test"


def test_kupongposter_bara_v85_for_vara_omgangar_och_ingen_harry():
    poster = las_fixture("atgtips_kupongposter.json")
    k = atgtips.tolka_kupongposter(poster, {SPEL})
    assert len(k) == 5 and {x["kalla"] for x in k} == {atgtips.KALLA_FEM}
    assert all(x["spel_id"] == SPEL and len(x["kupong_id"]) == 36 for x in k)
    assert atgtips.tolka_kupongposter(poster, {"V85_2030-01-01_1_1"}) == []
    harry = [{"title": "harry", "url": f"https://www.atg.se/spel/{SPEL}?couponId=01bc169e-68f1-4cf8-9c43-660937a83933"}]
    assert atgtips.tolka_kupongposter(harry, {SPEL}) == []


def test_namn_ur_artikeln():
    namn = atgtips.namn_ur_artikel(las_fixture("atgtips_fem_tippar_body.json"))
    assert sorted(namn.values()) == ["Jimmy Dahlman", "Mats E Djuse", "Mattias Djuse", "Nicklas Bäckström", "Oskar Florhed"]
    assert namn["3bzCnObG9yP4ueJBFxTDOZ"] == "Nicklas Bäckström"     # kupongpostens id


def _post(**andra):
    return {"post_id": "x", "kupong_id": "1956601d-126e-4258-be6e-fdef45f1cfe0", "spel_id": SPEL,
            "titel": "Kupong 5 Fem tippar", "artikel": "Fem tippar V85®", "kalla": atgtips.KALLA_FEM, **andra}


def test_kupong():
    e = atgtips.tolka_kupong(las_fixture("atgtips_kupong.json"), _post(), "Nicklas Bäckström")
    assert e.namn == "Nicklas Bäckström" and e.rader == 240 and len(e.val) == 8
    assert e.val["2026-10-17_16_5"] == [2, 3, 10] and e.val["2026-10-17_16_6"] == [3]


def test_kupong_utan_namn_far_titel_eller_artikel():
    assert atgtips.tolka_kupong(las_fixture("atgtips_kupong.json"), _post(), None).namn == "Fem tippar V85®"
    e = atgtips.tolka_kupong(las_fixture("atgtips_kupong.json"), _post(titel="Fernlunds systemförslag"), None)
    assert e.namn == "Fernlunds systemförslag"


def test_kupong_for_fel_omgang():
    with pytest.raises(ValideringsFel):
        atgtips.tolka_kupong(las_fixture("atgtips_kupong.json"), _post(spel_id="V85_2026-10-10_5_6"), None)


def test_lagring_och_expertandel(conn):
    lagring.spara_omgang(conn, atg.tolka_spel(las_fixture("atg_v85_kommande.json"), "x"))
    e = atgtips.tolka_kupong(las_fixture("atgtips_kupong.json"), _post(), "Nicklas Bäckström")
    assert lagring.spara_expertsystem(conn, [e], "2026-10-14T09:00:00Z") == 1
    assert lagring.spara_expertsystem(conn, [e], "2026-10-14T10:00:00Z") == 1      # ersätts, inga dubbletter
    assert conn.execute("SELECT COUNT(*) FROM expertval").fetchone()[0] == sum(len(v) for v in e.val.values())
    lopp = {l["avd"]: l for l in data.lopp(conn)}
    avd1 = {h["nr"]: h for h in lopp[1]["hastar"]}
    assert avd1[2]["expertandel"] == pytest.approx(1 / 3) and avd1[2]["experter"] == 1
    assert avd1[1]["expertandel"] == 0
    assert {h["nr"]: h for h in lopp[2]["hastar"]}[3]["expertandel"] == 1     # spik
    modeller.berakna_prognoser(conn)
    n = conn.execute("SELECT COUNT(*) FROM prognoser WHERE modellversion = ?", (modeller.EXPERTMODELL,)).fetchone()[0]
    assert n > 0


def test_ateranvand_post_far_veckans_artikel_och_avsandare():
    post = {"sys": {"id": "p1"}, "title": "Stora systemet",
            "url": f"https://www.atg.se/spel/{SPEL}?couponId=1956601d-126e-4258-be6e-fdef45f1cfe0",
            "linkedFrom": {"entryCollection": {"items": [
                {"__typename": "Article", "sys": {"id": "gammal"}, "title": "Lördag 18/10: Tips till V75® på Bjerke",
                 "slug": "x", "gameTagId": ["V75_2025-10-18_78_5"], "lead": "TR Medias tips till lördagens V75®"},
                {"__typename": "Article", "sys": {"id": "ny"}, "title": "Lördag 17/10: Tips till V85® på Gävle",
                 "slug": "y", "gameTagId": [SPEL], "lead": "TR Medias tips till lördagens V85® och Dagens Dubbel"}]}}}
    [k] = atgtips.tolka_kupongposter([post], {SPEL})
    assert k["artikel_id"] == "ny" and k["avsandare"] == "TR Media" and k["kalla"] == atgtips.KALLA_OVRIGA
    e = atgtips.tolka_kupong(las_fixture("atgtips_kupong.json"), k, None)
    assert e.namn == "TR Media (stora systemet)" and e.artikel == "Lördag 17/10: Tips till V85® på Gävle"
