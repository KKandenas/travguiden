"""Appens filer laddas med versionsnummer (?v=…) så att mobilens cache aldrig blandar gammalt och nytt.
Alla hänvisningar måste ha samma version – byt den överallt när appen ändras."""
import re
from pathlib import Path

DOCS = Path(__file__).parent.parent / "docs"


def test_samma_version_overallt():
    versioner = {}
    for f in ["index.html", "app.js", "backtest.js", "backtest_worker.js"]:
        for namn, v in re.findall(r'(app\.css|app\.js|optimizer\.js|backtest\.js|backtest_worker\.js)\?v=([\w.-]+)',
                                  (DOCS / f).read_text()):
            versioner.setdefault(v, []).append(f"{f}: {namn}")
    assert len(versioner) == 1, f"Olika versioner: {versioner}"
    hanvisningar = next(iter(versioner.values()))
    for namn in ("app.css", "app.js", "optimizer.js", "backtest.js"):
        assert any(namn in h for h in hanvisningar), f"{namn} laddas utan versionsnummer"
