"""Hästkoll steg 2 (AI med fejkat svar) och kandidatutvärderingen."""
import json
import random

from pipeline import export, lagring
from pipeline.ai import hastkoll
from pipeline.model import data, sannolikhet as S, statistik
from pipeline.sources import atg
from tests.conftest import las_fixture

SPEL = "V85_2026-10-17_16_5"


class FejkAI:
    def __init__(self):
        self.anrop = 0

    def __call__(self, system, fraga, schema, max_tokens):
        self.anrop += 1
        hastar = json.loads(fraga.split("\n", 1)[1])
        return {"hastar": [{"avd": h["avd"], "nr": h["nr"], "bedomning": 1 if h["nr"] == 1 else 0,
                            "motivering": "Instängd senast."} for h in hastar]}


def _omgang_med_kommentarer(conn):
    lagring.spara_omgang(conn, atg.tolka_spel(las_fixture("atg_v85_kommande.json"), "x"))
    avd_id = conn.execute("SELECT id FROM avdelningar WHERE avd = 1").fetchone()[0]
    lagring.spara_hastinfo(conn, avd_id, atg.tolka_hastinfo(las_fixture("atg_lopp_extended.json")), "x")
    conn.execute("UPDATE tidigare_starter SET kommentar = 'Rygg, ingen lucka, mkt kvar.' WHERE nr = 1")


def test_bedomer_en_gang_och_exporteras(conn):
    _omgang_med_kommentarer(conn)
    ai = FejkAI()
    assert hastkoll.uppdatera(conn, ai, SPEL) == 3 and ai.anrop == 1
    assert hastkoll.uppdatera(conn, ai, SPEL) == 0 and ai.anrop == 1          # redan bedömda
    h = export.omgang_data(conn, SPEL)["avdelningar"][0]["hastar"][0]
    assert h["hastkoll"] == {"bedomning": 1, "motivering": "Instängd senast."}
    l1 = next(l for l in data.lopp(conn) if l["avd"] == 1)
    assert {h["nr"]: h.get("hastkoll") for h in l1["hastar"]}[1] == 1


def test_kandidat_som_hittar_vinnaren_uppfyller_kravet(monkeypatch):
    monkeypatch.setattr(statistik, "MIN_KANDIDATLOPP", 100)
    monkeypatch.setattr(statistik, "MIN_TESTLOPP", 50)
    rng = random.Random(3)
    lopp = []
    for i in range(1200):
        n = 10
        streck = S.normalisera([rng.random() + .05 for _ in range(n)])
        markerad = rng.randrange(n)
        sann = S.normalisera([s * (3 if j == markerad else 1) for j, s in enumerate(streck)])
        vinnare = rng.choices(range(1, n + 1), weights=sann)[0]
        lopp.append({"datum": f"2025-{1 + i // 100:02d}-01", "spelform": "V85" if i % 2 else "V75", "avd": 2,
                     "startmetod": "auto", "distans": 2140, "vinnare": [vinnare],
                     "hastar": [{"nr": j + 1, "streck": s, "hastkoll": 1 if j == markerad else 0} for j, s in enumerate(streck)]})
    u = statistik.utvardera_kandidat(lopp, "hastkoll")
    assert u["uppfyllt"] and u["vikt"] > 0.5
