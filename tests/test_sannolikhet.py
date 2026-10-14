import math
import random

import pytest

from pipeline.model import sannolikhet as S


def _lopp(streck, vinnare=1, **extra):
    return {"startmetod": "auto", "distans": 2140, "vinnare": [vinnare],
            "hastar": [{"nr": i + 1, "streck": s, **extra} for i, s in enumerate(streck)]}


def test_vikt_ett_ger_strecken():
    l = _lopp([0.5, 0.3, 0.2])
    assert S.chanser(l, {"log_streck": 1.0}) == pytest.approx([0.5, 0.3, 0.2])


def test_vikt_under_ett_plattar_ut():
    p = S.chanser(_lopp([0.6, 0.3, 0.1]), {"log_streck": 0.8})
    assert p[0] < 0.6 and p[2] > 0.1 and sum(p) == pytest.approx(1)


def test_odds_vags_in_bara_nar_de_finns():
    l = _lopp([0.5, 0.5])
    l["hastar"][0]["vinnarodds"] = 1.5
    l["hastar"][1]["vinnarodds"] = 3.0
    p = S.chanser(l, {"log_streck": 1.0, "odds_mot_streck": 1.0})
    assert p == pytest.approx([2 / 3, 1 / 3])
    utan = _lopp([0.5, 0.5])
    assert S.chanser(utan, {"log_streck": 1.0, "odds_mot_streck": 1.0}) == pytest.approx([0.5, 0.5])


def test_skattning_hittar_kand_vikt():
    """Simulera lopp där den sanna chansen är streck^0,7 och kontrollera att skattningen hittar 0,7."""
    rng = random.Random(1)
    lopp = []
    for _ in range(3000):
        n = rng.randint(8, 12)
        streck = S.normalisera([rng.random() ** 3 + 0.01 for _ in range(n)])
        sann = S.normalisera([s ** 0.7 for s in streck])
        vinnare = rng.choices(range(1, n + 1), weights=sann)[0]
        lopp.append(_lopp(streck, vinnare))
    w = S.skatta(lopp, ["log_streck"], l2=0.1)
    assert w["log_streck"] == pytest.approx(0.7, abs=0.05)
    assert sum(S.logloss(lopp, w)) < sum(S.logloss(lopp, {"log_streck": 1.0}))


def test_dott_lopp_delar_vinsten():
    l = _lopp([0.5, 0.5])
    l["vinnare"] = [1, 2]
    assert S.logloss([l], {"log_streck": 1.0}) == [pytest.approx(-math.log(0.5))]


def test_experter_hojer_chansen_bara_dar_system_finns():
    l = _lopp([0.5, 0.5])
    l["hastar"][0]["expertandel"] = 1.0
    l["hastar"][1]["expertandel"] = 0.0
    p = S.chanser(l, {"log_streck": 1.0, "experter": 0.15})
    assert p[0] > 0.5 > p[1]
    assert S.chanser(_lopp([0.5, 0.5]), {"log_streck": 1.0, "experter": 0.15}) == pytest.approx([0.5, 0.5])
