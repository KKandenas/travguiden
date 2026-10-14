"""AI-kommentarer med en fejkad AI: vad den får se och när en kommentar skrivs om."""
import copy

from pipeline import export, lagring
from pipeline.ai import kommentarer
from pipeline.model import modeller
from pipeline.sources import atg, atgtips
from tests.conftest import las_fixture

SPEL = "V85_2026-10-17_16_5"


class FejkAI:
    def __init__(self):
        self.fragor = []

    def __call__(self, system, fraga, schema, max_tokens):
        import json
        avd = json.loads(fraga.split("\n", 1)[1])
        self.fragor.append([a["avd"] for a in avd])
        return {"kommentarer": [{"avd": a["avd"], "kommentar": f"Kommentar till avdelning {a['avd']}."} for a in avd]}


def _omgang(conn, med_expert=True):
    lagring.spara_omgang(conn, atg.tolka_spel(las_fixture("atg_v85_kommande.json"), "x"))
    if med_expert:
        post = {"post_id": "x", "kupong_id": "1956601d-126e-4258-be6e-fdef45f1cfe0", "spel_id": SPEL,
                "titel": "Kupong 5", "artikel": "Fem tippar V85®", "kalla": atgtips.KALLA_FEM}
        lagring.spara_expertsystem(conn, [atgtips.tolka_kupong(las_fixture("atgtips_kupong.json"), post, "Nicklas Bäckström")], "x")
    modeller.berakna_prognoser(conn)
    return export.omgang_data(conn, SPEL)


def test_underlag():
    d = {"avd": 1, "distans": 2140, "startmetod": "volte", "hastar": [
        {"nr": 1, "namn": "A", "kusk": "K", "streck": 0.6, "chans": 0.55, "distans": 2160, "ar": [5, 2], "livs": [20, 6, 10],
         "experter": [0]},
        {"nr": 2, "namn": "B", "streck": 0.4, "chans": 0.45, "distans": 2140, "experter": [0, 1]},
        {"nr": 3, "namn": "C", "struken": True, "experter": []},
    ]}
    u = kommentarer.underlag(d, [{"namn": "Ett"}, {"namn": "Två"}])
    assert u["lopp"] == "2140 m voltstart" and u["struken"] == ["3 C"]
    a, b = u["hastar"]
    assert (a["nr"], a["chans_procent"], a["streck_procent"], a["tillagg_meter"]) == (1, 55, 60, 20)
    assert a["experter"] == "1 av 2" and "spik_hos" not in a
    assert b["experter"] == "2 av 2" and b["spik_hos"] == ["Två"]


def test_skriver_alla_forst_och_sedan_bara_vid_andring(conn):
    ai = FejkAI()
    d = _omgang(conn)
    assert kommentarer.uppdatera(conn, ai, d, nu="2026-10-14T10:00:00Z") == 8
    assert kommentarer.uppdatera(conn, ai, d, nu="2026-10-14T12:00:00Z") == 0
    assert export.omgang_data(conn, SPEL)["avdelningar"][0]["kommentar"] == "Kommentar till avdelning 1."

    # En struken häst ger alltid en ny kommentar för den avdelningen
    struken = copy.deepcopy(d)
    struken["avdelningar"][2]["hastar"][0]["struken"] = True
    assert kommentarer.uppdatera(conn, ai, struken, nu="2026-10-14T13:00:00Z") == 1
    assert ai.fragor[-1] == [3]


def test_andrat_underlag_vantar_tills_kommentaren_ar_gammal(conn):
    ai = FejkAI()
    d = _omgang(conn)
    kommentarer.uppdatera(conn, ai, d, nu="2026-10-14T10:00:00Z")
    nytt = copy.deepcopy(d)
    for a in nytt["avdelningar"]:
        h = next(h for h in a["hastar"] if not h.get("struken"))
        h["streck"] = (h["streck"] or 0) + 0.05
    assert kommentarer.uppdatera(conn, ai, nytt, nu="2026-10-14T20:00:00Z") == 0      # bara 10 h
    assert kommentarer.uppdatera(conn, ai, nytt, nu="2026-10-15T07:00:00Z") == 8      # 21 h


def test_nya_expertsystem_ger_nya_kommentarer(conn):
    ai = FejkAI()
    kommentarer.uppdatera(conn, ai, _omgang(conn, med_expert=False), nu="2026-10-14T10:00:00Z")
    assert kommentarer.uppdatera(conn, ai, _omgang(conn, med_expert=True), nu="2026-10-14T11:00:00Z") == 8
