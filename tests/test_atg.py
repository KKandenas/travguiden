"""Tolkning av ATG:s svar (sparade i tests/fixtures, bantade på fält vi inte använder)."""
import copy

import pytest

from pipeline.modeller import ValideringsFel
from pipeline.sources import atg
from tests.conftest import las_fixture

HAMTAD = "2026-10-14T08:00:00Z"


def test_kommande_omgang():
    o = atg.tolka_spel(las_fixture("atg_v85_kommande.json"), HAMTAD)
    assert o.id == "V85_2026-10-17_16_5" and o.spelform == "V85" and o.bana == "Gävle"
    assert o.spelstopp == "2026-10-17T13:00:00Z"          # 15:00 svensk sommartid
    assert o.tidpunkt == "2026-10-14T08:15:45Z"           # poolens tidsstämpel
    assert len(o.avdelningar) == 8 and not o.avgjord and o.utdelning == {}
    a1 = o.avdelningar[0]
    assert a1.distans == 1640 and a1.startmetod == "auto" and a1.vinnare == []
    h1 = a1.starter[0]
    assert h1.hast == "Zätamustangen" and h1.kusk == "Mats E Djuse" and h1.spar == 1
    assert h1.streck == pytest.approx(0.0914)
    assert h1.vinnarodds is None                          # vinnarpoolen har bara 377 kr än
    assert h1.rekord == "1.10,7aK" and h1.livs_starter == 82 and h1.livs_segrar == 20
    for a in o.avdelningar:
        assert sum(s.streck for s in a.starter) == pytest.approx(1, abs=0.03)


def test_odds_nar_vinnarpoolen_har_pengar():
    d = las_fixture("atg_v85_kommande.json")
    for r in d["races"]:
        r["pools"]["vinnare"]["turnover"] = 50_000_000      # 500 000 kr
    o = atg.tolka_spel(d, HAMTAD)
    assert o.avdelningar[0].starter[0].vinnarodds == pytest.approx(7.61)
    alla = [s for a in o.avdelningar for s in a.starter]
    assert any(s.vinnarodds is None for s in alla)        # 9999 = inga odds än
    struken = o.avdelningar[5].starter[0]
    assert struken.struken and struken.vinnarodds is None  # odds 0 för struken häst


def test_avgjord_omgang():
    o = atg.tolka_spel(las_fixture("atg_v85_avgjord.json"), HAMTAD)
    assert o.avgjord
    assert o.utdelning == {5: 7.0, 6: 32.0, 7: 846.0, 8: 64035.0}
    assert o.vinnande_rader[8] == 244
    assert [a.vinnare for a in o.avdelningar] == [[1], [5], [7], [15], [7], [5], [3], [9]]
    vinnare = o.avdelningar[0].starter[0]
    assert vinnare.placering == 1 and vinnare.slutodds == pytest.approx(2.53) and vinnare.km_tid == "1.11,9"


def test_fel_antal_avdelningar():
    d = las_fixture("atg_v85_kommande.json")
    d["races"] = d["races"][:7]
    with pytest.raises(ValideringsFel):
        atg.tolka_spel(d, HAMTAD)


def test_trasiga_streck_sparas_inte():
    d = copy.deepcopy(las_fixture("atg_v85_kommande.json"))
    d["races"][0]["starts"][0]["pools"]["V85"]["betDistribution"] = 9000
    o = atg.tolka_spel(d, HAMTAD)
    assert all(s.streck is None for s in o.avdelningar[0].starter)
    assert all(s.streck is not None for s in o.avdelningar[1].starter)


def test_hoga_odds_ar_riktiga():
    assert atg._odds(30188) == pytest.approx(301.88)
    assert atg._odds(9999) is None and atg._odds(0) is None


def test_v75_omgang():
    o = atg.tolka_spel(las_fixture("atg_v75_avgjord.json"), HAMTAD)
    assert o.spelform == "V75" and len(o.avdelningar) == 7 and o.avgjord
    assert sorted(o.utdelning) == [5, 6, 7]
    for a in o.avdelningar:
        assert sum(s.streck for s in a.starter) == pytest.approx(1, abs=0.03)


def test_radpris_och_vinstgrupper():
    from pipeline import config
    assert config.radpris("V85", "2026-10-17") == 0.5
    assert config.radpris("V75", "2025-10-11") == 0.5           # gamla V75
    assert config.radpris("V75", "2026-11-28") == 0.6           # nya V75
    assert config.vinstgrupper(8) == [8, 7, 6, 5] and config.vinstgrupper(7) == [7, 6, 5]
