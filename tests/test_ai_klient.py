import time

import pytest

from pipeline.ai import klient
from pipeline.ai.klient import AiFel


@pytest.fixture(autouse=True)
def nollstall(monkeypatch):
    monkeypatch.setattr(klient, "_start", None)
    monkeypatch.setattr(klient, "_fel_i_rad", 0)
    monkeypatch.setattr(klient, "_anrop", {})
    monkeypatch.setattr(klient, "_paus", {})
    monkeypatch.setattr(klient, "leverantor", lambda: "gemini")


def test_hangande_anrop_ger_upp_efter_tidsgransen():
    start = time.monotonic()
    with pytest.raises(AiFel, match="inget svar"):
        klient._med_tidsgrans(lambda: time.sleep(5), 0.2)
    assert time.monotonic() - start < 2


def test_fel_i_anropet_skickas_vidare():
    def boom():
        raise ValueError("x")
    with pytest.raises(ValueError):
        klient._med_tidsgrans(boom, 1)


def test_ai_hoppas_over_efter_flera_fel_i_rad(monkeypatch):
    anrop = []

    def trasig(*a):
        anrop.append(1)
        raise AiFel("503")
    monkeypatch.setattr(klient, "_anropa_gemini", trasig)
    for _ in range(klient.MAX_FEL_I_RAD):
        with pytest.raises(AiFel, match="503"):
            klient.anropa_json("s", "u", {})
    with pytest.raises(AiFel, match="i rad"):
        klient.anropa_json("s", "u", {})
    assert len(anrop) == klient.MAX_FEL_I_RAD


def test_lyckat_anrop_nollstaller_felraknaren(monkeypatch):
    svar = iter([AiFel("503"), AiFel("503"), {"ok": 1}, AiFel("503"), AiFel("503"), {"ok": 2}])

    def ibland(*a):
        x = next(svar)
        if isinstance(x, Exception):
            raise x
        return x
    monkeypatch.setattr(klient, "_anropa_gemini", ibland)
    resultat = []
    for _ in range(6):
        try:
            resultat.append(klient.anropa_json("s", "u", {}))
        except AiFel:
            pass
    assert resultat == [{"ok": 1}, {"ok": 2}]


def test_tidsbudgeten_stoppar_fler_anrop(monkeypatch):
    monkeypatch.setattr(klient, "_anropa_gemini", lambda *a: {"ok": 1})
    assert klient.anropa_json("s", "u", {}) == {"ok": 1}
    monkeypatch.setattr(klient, "_start", time.monotonic() - klient.AI_TIDSBUDGET - 1)
    with pytest.raises(AiFel, match="tidsbudgeten"):
        klient.anropa_json("s", "u", {})


class _Svar:
    status = "completed"
    output_text = '{"ok": 1}'
    usage = None


class _Fel(Exception):
    def __init__(self, kod, text="overloaded"):
        super().__init__(text)
        self.code = kod


class _FalskGemini:
    """Svarar enligt en tabell modell -> lista av utfall (Exception eller "ok")."""
    def __init__(self, utfall):
        self.utfall, self.anrop = utfall, []
        self.interactions = self

    def create(self, model, **k):
        self.anrop.append(model)
        u = self.utfall[model].pop(0) if self.utfall[model] else "ok"
        if isinstance(u, Exception):
            raise u
        return _Svar()


def test_reservmodell_tar_over_vid_overbelastning(monkeypatch):
    falsk = _FalskGemini({"huvud": [_Fel(503), _Fel(503)], "reserv1": [], "reserv2": []})
    monkeypatch.setattr(klient, "_gemini", falsk)
    monkeypatch.setattr(klient, "GEMINI_MODELL", "huvud")
    monkeypatch.setattr(klient, "GEMINI_RESERVER", ["reserv1", "reserv2"])
    monkeypatch.setattr(klient, "_ordning", [])
    monkeypatch.setattr(klient, "_ur_spel", set())
    assert klient.anropa_json("s", "u", {}) == {"ok": 1}
    assert falsk.anrop == ["huvud", "reserv1"]
    # Huvudmodellen ligger nu sist – nästa anrop går direkt till reserven
    assert klient.anropa_json("s", "u", {}) == {"ok": 1}
    assert falsk.anrop[-1] == "reserv1"


def test_okand_modell_hoppas_over_och_andra_fel_kastas(monkeypatch):
    falsk = _FalskGemini({"huvud": [_Fel(404, "model not found")], "reserv1": [_Fel(400, "bad schema")]})
    monkeypatch.setattr(klient, "_gemini", falsk)
    monkeypatch.setattr(klient, "GEMINI_MODELL", "huvud")
    monkeypatch.setattr(klient, "GEMINI_RESERVER", ["reserv1"])
    monkeypatch.setattr(klient, "_ordning", [])
    monkeypatch.setattr(klient, "_ur_spel", set())
    with pytest.raises(AiFel, match="bad schema"):
        klient.anropa_json("s", "u", {})
    assert klient._ur_spel == {"huvud"}


def test_alla_modeller_nere_ger_aifel_efter_tva_varv(monkeypatch):
    falsk = _FalskGemini({"huvud": [_Fel(503)] * 5, "reserv1": [_Fel(429)] * 5})
    monkeypatch.setattr(klient, "_gemini", falsk)
    monkeypatch.setattr(klient, "GEMINI_MODELL", "huvud")
    monkeypatch.setattr(klient, "GEMINI_RESERVER", ["reserv1"])
    monkeypatch.setattr(klient, "_ordning", [])
    monkeypatch.setattr(klient, "_ur_spel", set())
    monkeypatch.setattr(klient.time, "sleep", lambda s: None)
    with pytest.raises(AiFel):
        klient.anropa_json("s", "u", {})
    assert len(falsk.anrop) == 2 * klient.MAX_VARV


def test_dagskvot_slut_tar_modellen_ur_spel(monkeypatch):
    falsk = _FalskGemini({"huvud": [_Fel(429, "Quota exceeded for metric: requests per day")], "reserv1": []})
    monkeypatch.setattr(klient, "_gemini", falsk)
    monkeypatch.setattr(klient, "GEMINI_MODELL", "huvud")
    monkeypatch.setattr(klient, "GEMINI_RESERVER", ["reserv1"])
    monkeypatch.setattr(klient, "_ordning", [])
    monkeypatch.setattr(klient, "_ur_spel", set())
    assert klient.anropa_json("s", "u", {}) == {"ok": 1}
    assert klient._ur_spel == {"huvud"}


def test_gemini_klienten_byggs_utan_egna_omforsok(monkeypatch):
    """Körs bara där google-genai är installerat (Python 3.10+, t.ex. i CI)."""
    pytest.importorskip("google.genai")
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    monkeypatch.setattr(klient, "_gemini", None)
    monkeypatch.setattr(klient, "_ordning", [])
    monkeypatch.setattr(klient, "_ur_spel", set())
    fangad = {}

    def fake_skapa(fn, sekunder):
        fangad["klient"] = klient._gemini
        raise RuntimeError("inget nätverk i tester")
    monkeypatch.setattr(klient, "_med_tidsgrans", fake_skapa)
    with pytest.raises(AiFel):
        klient._anropa_gemini("s", "u", {}, 10)
    opt = fangad["klient"]._api_client._http_options
    assert opt.retry_options.attempts == 1 and opt.retry_options.http_status_codes == [408]


def test_ai_status_sparas_och_exporteras(conn, monkeypatch):
    import json
    from pipeline import __main__ as cli, export
    monkeypatch.setattr(klient, "KORNING", {"lyckade": 3, "misslyckade": 1, "modeller": {"gemini-3.7-flash": 3},
                                            "stoppad": None})
    monkeypatch.setattr(klient, "tillganglig", lambda: (True, ""))
    cli.spara_ai_status(conn)
    d = export.bygg_drift(conn)
    assert d["ai"]["lyckade"] == 3 and d["ai"]["modeller"] == {"gemini-3.7-flash": 3} and d["ai"]["tid"]
    # Ingen AI använd i körningen → förra statusen ligger kvar
    monkeypatch.setattr(klient, "KORNING", {"lyckade": 0, "misslyckade": 0, "modeller": {}, "stoppad": None})
    cli.spara_ai_status(conn)
    assert export.bygg_drift(conn)["ai"]["lyckade"] == 3
    monkeypatch.setattr(klient, "tillganglig", lambda: (False, "ingen AI-nyckel"))
    cli.spara_ai_status(conn)
    assert export.bygg_drift(conn)["ai"] == {"konfigurerad": False, "orsak": "ingen AI-nyckel",
                                             "tid": export.bygg_drift(conn)["ai"]["tid"]}
    assert json.dumps(export.bygg_drift(conn))



def test_hogst_rpm_grans_anrop_per_modell_och_minut(monkeypatch):
    """Gratisnivån tillåter 5 anrop/min per modell: vi sprider över kedjan och väntar när alla är fulla."""
    klocka = {"t": 1000.0}
    monkeypatch.setattr(klient.time, "monotonic", lambda: klocka["t"])
    vantat = []
    monkeypatch.setattr(klient.time, "sleep", lambda s: (vantat.append(s), klocka.__setitem__("t", klocka["t"] + s)))
    monkeypatch.setattr(klient, "RPM_GRANS", 2)
    falsk = _FalskGemini({"huvud": [], "reserv1": []})
    monkeypatch.setattr(klient, "_gemini", falsk)
    monkeypatch.setattr(klient, "GEMINI_MODELL", "huvud")
    monkeypatch.setattr(klient, "GEMINI_RESERVER", ["reserv1"])
    monkeypatch.setattr(klient, "_ordning", [])
    monkeypatch.setattr(klient, "_ur_spel", set())
    for _ in range(5):
        assert klient.anropa_json("s", "u", {}) == {"ok": 1}
    assert falsk.anrop == ["huvud", "huvud", "reserv1", "reserv1", "huvud"]
    assert len(vantat) == 1 and 59 <= vantat[0] <= 61       # det femte anropet väntade en minut


def test_429_per_minut_pausar_modellen(monkeypatch):
    klocka = {"t": 1000.0}
    monkeypatch.setattr(klient.time, "monotonic", lambda: klocka["t"])
    falsk = _FalskGemini({"huvud": [_Fel(429, "Your project has exceeded a quota")], "reserv1": []})
    monkeypatch.setattr(klient, "_gemini", falsk)
    monkeypatch.setattr(klient, "GEMINI_MODELL", "huvud")
    monkeypatch.setattr(klient, "GEMINI_RESERVER", ["reserv1"])
    monkeypatch.setattr(klient, "_ordning", [])
    monkeypatch.setattr(klient, "_ur_spel", set())
    assert klient.anropa_json("s", "u", {}) == {"ok": 1}
    assert klient.anropa_json("s", "u", {}) == {"ok": 1}
    assert falsk.anrop == ["huvud", "reserv1", "reserv1"]      # huvud vilar en minut efter 429
