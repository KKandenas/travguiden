"""Hästkoll steg 2 (AI med fejkat svar) och kandidatutvärderingen."""
import json
import math
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
                            "motivering": "Instängd senast.",
                            "starter": [{"datum": t["datum"], "lage": "rygg", "storning": "instangd", "avslutning": "stark",
                                         "tempo": "neutral", "bedomning": 1}
                                        for t in h["senaste_starter"] if t["kommentar"]]
                                       + [{"datum": "1999-01-01", "lage": "rygg", "storning": "ingen",
                                           "avslutning": "normal", "tempo": "neutral", "bedomning": 0}]} for h in hastar]}


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
    u = statistik.utvardera_kandidat(lopp, "hastkoll", _bas(lopp))
    assert u["uppfyllt"] and u["vikt"] > 0.5



def test_ny_kommentar_ger_ny_bedomning_men_inte_en_som_forsvinner(conn):
    _omgang_med_kommentarer(conn)
    ai = FejkAI()
    assert hastkoll.uppdatera(conn, ai, SPEL) == 3 and ai.anrop == 1
    # En kommentar till en äldre start tillkommer för häst 1
    sid = conn.execute("SELECT s.id FROM starter s JOIN avdelningar a ON a.id = s.avdelning_id "
                       "WHERE a.avd = 1 AND s.nr = 1").fetchone()[0]
    conn.execute("UPDATE tidigare_starter SET kommentar = 'Gal i första sväng, mkt bra avsl.' WHERE start_id = ? AND nr = 2", (sid,))
    assert hastkoll.uppdatera(conn, ai, SPEL) == 1 and ai.anrop == 2
    # Kommentaren försvinner igen: ingen ny bedömning
    conn.execute("UPDATE tidigare_starter SET kommentar = NULL WHERE start_id = ? AND nr = 2", (sid,))
    assert hastkoll.uppdatera(conn, ai, SPEL) == 0 and ai.anrop == 2


def test_bedomningar_fran_fore_migreringen_far_avtryck_utan_ny_bedomning(conn):
    _omgang_med_kommentarer(conn)
    ai = FejkAI()
    hastkoll.uppdatera(conn, ai, SPEL)
    conn.execute("UPDATE hastkoll SET kommentarer = NULL")
    assert hastkoll.uppdatera(conn, ai, SPEL) == 0 and ai.anrop == 1
    assert conn.execute("SELECT COUNT(*) FROM hastkoll WHERE kommentarer IS NULL").fetchone()[0] == 0



def test_historik_och_faktorer_sparas(conn):
    _omgang_med_kommentarer(conn)
    ai = FejkAI()
    hastkoll.uppdatera(conn, ai, SPEL)
    assert conn.execute("SELECT COUNT(*) FROM hastkoll_historik WHERE version = ?", (hastkoll.VERSION,)).fetchone()[0] == 3
    f = conn.execute("SELECT * FROM hastkoll_faktorer").fetchall()
    assert len(f) == 3                                     # en per start med kommentar; påhittat datum hoppas över
    assert (f[0]["lage"], f[0]["storning"], f[0]["avslutning"], f[0]["bedomning"]) == ("rygg", "instangd", "stark", 1)
    # Om-bedömning av hela omgången: ny historikrad, den gamla finns kvar
    assert hastkoll.uppdatera(conn, ai, SPEL, alla=True) == 3
    assert conn.execute("SELECT COUNT(*) FROM hastkoll_historik").fetchone()[0] == 6
    assert conn.execute("SELECT COUNT(*) FROM hastkoll").fetchone()[0] == 3


def test_aldre_version_bedoms_om_bara_nar_det_begars(conn):
    _omgang_med_kommentarer(conn)
    ai = FejkAI()
    hastkoll.uppdatera(conn, ai, SPEL)
    conn.execute("UPDATE hastkoll SET version = 'hastkoll-1'")
    assert hastkoll.uppdatera(conn, ai, SPEL, ny_version=False) == 0
    assert hastkoll.uppdatera(conn, ai, SPEL, ny_version=True) == 3



def test_kandidat_som_stjalper_en_spelform_godkanns_inte(monkeypatch):
    monkeypatch.setattr(statistik, "MIN_KANDIDATLOPP", 100)
    monkeypatch.setattr(statistik, "MIN_TESTLOPP", 50)
    rng = random.Random(5)
    lopp = []
    for i in range(1600):
        streck = S.normalisera([rng.random() + .05 for _ in range(10)])
        markerad = rng.randrange(10)
        v85 = i % 2 == 1
        faktor = 3 if not v85 else 0.2          # hjälper i V75, stjälper i V85
        sann = S.normalisera([s * (faktor if j == markerad else 1) for j, s in enumerate(streck)])
        lopp.append({"datum": f"2025-{1 + i // 134:02d}-01", "spelform": "V85" if v85 else "V75", "avd": 2,
                     "startmetod": "auto", "distans": 2140,
                     "vinnare": [rng.choices(range(1, 11), weights=sann)[0]],
                     "hastar": [{"nr": j + 1, "streck": s, "hastkoll": 1 if j == markerad else 0} for j, s in enumerate(streck)]})
    u = statistik.utvardera_kandidat(lopp, "hastkoll", _bas(lopp))
    assert u["per_spelform"]["V85"]["forbattring"] < 0 and not u["uppfyllt"]



def _bas(lopp):
    """Oddsens vikter per månad: här strecken som de är."""
    return {l["datum"][:7]: {"log_streck": 1.0, "log_streck_v85": 0.0, "odds_mot_streck": 0.0} for l in lopp}


def test_skatta_med_fasta_vikter():
    rng = random.Random(9)
    lopp = []
    for _ in range(1500):
        streck = S.normalisera([rng.random() + .05 for _ in range(10)])
        m = rng.randrange(10)
        sann = S.normalisera([s * (2 if j == m else 1) for j, s in enumerate(streck)])
        lopp.append({"startmetod": "auto", "distans": 2140, "vinnare": [rng.choices(range(1, 11), weights=sann)[0]],
                     "hastar": [{"nr": j + 1, "streck": s, "hastkoll": 1 if j == m else 0} for j, s in enumerate(streck)]})
    w = S.skatta(lopp, ["hastkoll"], l2=0.1, fast={"log_streck": 1.0})
    assert w["log_streck"] == 1.0 and abs(w["hastkoll"] - math.log(2)) < 0.15
