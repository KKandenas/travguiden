"""AI-anrop från pipelinen (aldrig från appen). Allt går genom anropa_json().

Två leverantörer, valda efter vilken nyckel som finns:
- Gemini (förval) via Googles SDK `google-genai`, nyckel GEMINI_API_KEY. Har en gratisnivå.
- Claude via Anthropics SDK `anthropic`, nyckel ANTHROPIC_API_KEY.
Finns båda används Gemini, om inte AI_LEVERANTOR=claude. Båda SDK:erna kräver Python 3.10+.
Saknas nyckel eller SDK hoppar AI-stegen över med en loggrad – resten av pipelinen fungerar ändå.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any, Callable, Dict, List, Optional

log = logging.getLogger(__name__)

GEMINI_MODELL = os.environ.get("GEMINI_MODELL", "").strip() or "gemini-3.8-flash"  # kan sättas som repo-variabel
# Reserver när huvudmodellen är överbelastad eller inte svarar (repo-variabel GEMINI_RESERVMODELLER, kommaseparerad).
GEMINI_RESERVER = [m.strip() for m in (os.environ.get("GEMINI_RESERVMODELLER", "").strip()
                                       or "gemini-3.7-flash,gemini-3.6-flash,gemini-3.5-flash").split(",") if m.strip()]
GEMINI_TANKANDE = "low"            # minimal | low | medium | high

CLAUDE_MODELL = "claude-opus-5-5"
CLAUDE_EFFORT = "medium"

MAX_VARV = 2                       # varv genom hela modellkedjan innan anropet ges upp (30 s paus emellan)
TILLFALLIGA_FEL = {429, 500, 502, 503, 504}
OKANDA_MODELLER = {400, 404}       # modellen finns inte (längre) – hoppas över resten av körningen
ANROP_TIDSGRANS = 90               # sekunder per enskilt anrop; SDK:t kan annars hänga i det oändliga
AI_TIDSBUDGET = 15 * 60            # sekunder AI totalt per körning, så att körningen hinner spara sin data
MAX_FEL_I_RAD = 3                  # så många misslyckade anrop i rad → AI hoppas över resten av körningen

_start: Optional[float] = None
_fel_i_rad = 0
# Hur AI-anropen gick under körningen – sparas för driftstatusen i appen (se __main__.spara_ai_status).
KORNING: Dict[str, Any] = {"lyckade": 0, "misslyckade": 0, "modeller": {}, "stoppad": None}
_ordning: List[str] = []           # modellkedjan; en modell som just svarat dåligt flyttas sist
_ur_spel: set = set()              # modeller som inte finns

# Signaturen som resten av koden använder; tester skickar in en egen funktion med samma form.
Anropare = Callable[[str, str, Dict[str, Any], int], Dict[str, Any]]


class AiFel(Exception):
    pass


def leverantor() -> Optional[str]:
    har_gemini = bool(os.environ.get("GEMINI_API_KEY", "").strip())
    har_claude = bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())
    if os.environ.get("AI_LEVERANTOR", "").lower() == "claude" and har_claude:
        return "claude"
    if har_gemini:
        return "gemini"
    if har_claude:
        return "claude"
    return None


def modellnamn() -> str:
    return GEMINI_MODELL if leverantor() == "gemini" else CLAUDE_MODELL


def tillganglig() -> tuple:
    """(True, '') om en AI-modell kan anropas, annars (False, orsak)."""
    lev = leverantor()
    if lev is None:
        return False, "varken GEMINI_API_KEY eller ANTHROPIC_API_KEY är satt"
    try:
        if lev == "gemini":
            from google import genai  # noqa: F401
        else:
            import anthropic  # noqa: F401
    except ImportError:
        paket = "google-genai" if lev == "gemini" else "anthropic"
        return False, f"paketet {paket} är inte installerat (kräver Python 3.10+)"
    return True, ""


def _tolka_json(text: Optional[str]) -> Dict[str, Any]:
    if not text:
        raise AiFel("svaret saknar text")
    try:
        return json.loads(text)
    except ValueError as e:
        raise AiFel(f"svaret var inte giltig JSON: {e}") from e


# ---------- Gemini ----------

_gemini = None


def _med_tidsgrans(fn: Callable[[], Any], sekunder: float) -> Any:
    """Kör fn i en daemon-tråd och ge upp efter `sekunder`. En hängande tråd stoppar inte processen."""
    ut: Dict[str, Any] = {}

    def kor() -> None:
        try:
            ut["svar"] = fn()
        except BaseException as e:  # skickas vidare till anroparen nedan
            ut["fel"] = e

    t = threading.Thread(target=kor, daemon=True)
    t.start()
    t.join(sekunder)
    if t.is_alive():
        raise AiFel(f"inget svar inom {sekunder:.0f} s")
    if "fel" in ut:
        raise ut["fel"]
    return ut["svar"]


def _modellkedja() -> List[str]:
    global _ordning
    alla = [GEMINI_MODELL] + [m for m in GEMINI_RESERVER if m != GEMINI_MODELL]
    if set(_ordning) != set(alla):
        _ordning = alla
    return [m for m in _ordning if m not in _ur_spel]


def _flytta_sist(modell: str) -> None:
    if modell in _ordning:
        _ordning.remove(modell)
        _ordning.append(modell)


def _anropa_gemini(system: str, anvandare: str, schema: Dict[str, Any], max_tokens: int) -> Dict[str, Any]:
    """Prova modellkedjan: huvudmodellen först, sedan reserverna. En modell som är överbelastad, svarar
    med serverfel eller inte svarar inom tidsgränsen flyttas sist för resten av körningen, så att nästa
    anrop går direkt till en modell som fungerar."""
    global _gemini
    if _gemini is None:
        from google import genai
        from google.genai import types
        # SDK:t gör annars egna omförsök vid 429/5xx och väntar så länge servern säger (Retry-After) – det
        # var därför anrop "hängde". Vi låter 429/5xx komma direkt hit och byter modell i stället.
        _gemini = genai.Client(http_options=types.HttpOptions(  # läser GEMINI_API_KEY
            timeout=ANROP_TIDSGRANS * 1000,
            retry_options=types.HttpRetryOptions(attempts=1, http_status_codes=[408])))
    senaste_fel = "ingen modell att prova"
    for varv in range(MAX_VARV):
        if varv:
            log.info("Gemini: alla modeller svarade dåligt, väntar 30 s")
            time.sleep(30)
        for modell in _modellkedja():
            try:
                svar = _med_tidsgrans(lambda modell=modell: _gemini.interactions.create(
                    model=modell,
                    system_instruction=system,
                    input=anvandare,
                    response_mime_type="application/json",
                    response_format={"type": "text", "mime_type": "application/json", "schema": schema},
                    generation_config={"thinking_level": GEMINI_TANKANDE, "max_output_tokens": max_tokens},
                    store=False,
                ), ANROP_TIDSGRANS)
            except AiFel as e:                       # tidsgränsen
                senaste_fel = f"{modell}: {e}"
                log.info("Gemini: %s – provar nästa modell", senaste_fel)
                _flytta_sist(modell)
                continue
            except Exception as e:  # interactions-API:t har egna feltyper; titta bara på statuskoden
                kod = getattr(e, "code", None) or getattr(e, "status_code", None)
                senaste_fel = f"{modell} svarade {kod or type(e).__name__}: {e}"
                if kod in OKANDA_MODELLER and "model" in str(e).lower():
                    log.warning("Gemini: %s finns inte – används inte mer i den här körningen", modell)
                    _ur_spel.add(modell)
                    continue
                if kod == 429 and "day" in str(e).lower():
                    log.warning("Gemini: %s – dagskvoten är slut, används inte mer i den här körningen", modell)
                    _ur_spel.add(modell)
                    continue
                if kod in TILLFALLIGA_FEL:
                    log.info("Gemini: %s – tillfälligt fel (%s), provar nästa modell", modell, kod)
                    _flytta_sist(modell)
                    continue
                raise AiFel(senaste_fel) from e
            usage = getattr(svar, "usage", None)
            if usage is not None:
                log.info("Gemini: %s in / %s ut tokens (%s)", getattr(usage, "total_input_tokens", "?"),
                         getattr(usage, "total_output_tokens", "?"), modell)
            if svar.status != "completed":
                raise AiFel(f"Gemini ({modell}) avslutade med status {svar.status}")
            KORNING["modeller"][modell] = KORNING["modeller"].get(modell, 0) + 1
            return _tolka_json(svar.output_text)
    raise AiFel(senaste_fel)


# ---------- Claude ----------

_claude = None


def _anropa_claude(system: str, anvandare: str, schema: Dict[str, Any], max_tokens: int) -> Dict[str, Any]:
    global _claude
    import anthropic

    if _claude is None:
        _claude = anthropic.Anthropic()
    try:
        svar = _claude.beta.messages.create(
            model=CLAUDE_MODELL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": anvandare}],
            output_config={"effort": CLAUDE_EFFORT, "format": {"type": "json_schema", "schema": schema}},
            # Om modellen avböjer körs samma anrop automatiskt på en reservmodell.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
    except anthropic.APIStatusError as e:
        raise AiFel(f"Claude API svarade {e.status_code}: {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise AiFel(f"Nätverksfel mot Claude API: {e}") from e

    log.info("Claude: %s in / %s ut tokens (%s)", svar.usage.input_tokens, svar.usage.output_tokens, svar.model)
    if svar.stop_reason == "refusal":
        raise AiFel("Claude avböjde förfrågan")
    if svar.stop_reason == "max_tokens":
        raise AiFel("Claude-svaret blev avklippt (max_tokens)")
    return _tolka_json(next((b.text for b in svar.content if b.type == "text"), None))


def anropa_json(system: str, anvandare: str, schema: Dict[str, Any], max_tokens: int = 16000) -> Dict[str, Any]:
    """Ett anrop med strikt JSON-schema för svaret. Kastar AiFel vid avslag, avbrott eller API-fel."""
    global _start, _fel_i_rad
    lev = leverantor()
    if lev is None:
        raise AiFel("ingen AI-nyckel är satt")
    if _fel_i_rad >= MAX_FEL_I_RAD:
        KORNING["stoppad"] = "flera misslyckade anrop i rad"
        raise AiFel(f"{_fel_i_rad} misslyckade anrop i rad – hoppar över AI resten av körningen")
    if _start is None:
        _start = time.monotonic()
    elif time.monotonic() - _start > AI_TIDSBUDGET:
        KORNING["stoppad"] = f"tidsbudgeten ({AI_TIDSBUDGET // 60} min) tog slut"
        raise AiFel(f"tidsbudgeten för AI ({AI_TIDSBUDGET // 60} min) är slut – resten tas nästa körning")
    try:
        svar = (_anropa_gemini if lev == "gemini" else _anropa_claude)(system, anvandare, schema, max_tokens)
    except AiFel:
        _fel_i_rad += 1
        KORNING["misslyckade"] += 1
        raise
    _fel_i_rad = 0
    KORNING["lyckade"] += 1
    return svar
