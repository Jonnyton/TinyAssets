"""The MCP server must not import spaCy when it starts.

tinyassets.evaluation.structural used to `import spacy` (and try to load a
model) at module import. The server reaches that module at import time
(universe_server -> api.extensions -> handoffs -> outcomes -> evaluation), so
every server start and every process that imported the server paid for
spaCy's numpy/thinc stack for a model it never calls. Measured on 2026-10-01
(Windows, cold): importing the server took 8.2 s at 328 MB RSS with spaCy
loaded, and 2.6 s at 121 MB without it.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from tinyassets.evaluation import structural

_REPO = Path(__file__).resolve().parent.parent


def _loaded_after(module: str) -> set[str]:
    probe = (
        f"import sys, {module}\n"
        "print(' '.join(sorted(m.split('.')[0] for m in sys.modules)))\n"
    )
    out = subprocess.run(
        [sys.executable, "-c", probe], cwd=_REPO, capture_output=True, text=True,
        timeout=300, check=True,
    ).stdout
    return set(out.split())


def test_importing_the_server_does_not_load_spacy():
    loaded = _loaded_after("tinyassets.universe_server")
    assert "spacy" not in loaded
    assert "thinc" not in loaded


def test_the_pipeline_loads_once_on_first_use(monkeypatch):
    calls = []

    def fake_loader():
        calls.append(1)
        return None

    monkeypatch.setattr(structural, "_NLP_CACHE", structural._UNLOADED)
    monkeypatch.setitem(sys.modules, "spacy", type(sys)("spacy"))
    sys.modules["spacy"].load = lambda name: (calls.append(name), "pipeline")[1]
    assert structural._nlp() == "pipeline"
    assert structural._nlp() == "pipeline"
    assert calls == ["en_core_web_sm"], "loaded once, then cached"


def test_a_missing_model_degrades_to_the_regex_fallback(monkeypatch):
    def missing(name):
        raise OSError("no model")

    monkeypatch.setattr(structural, "_NLP_CACHE", structural._UNLOADED)
    monkeypatch.setitem(sys.modules, "spacy", type(sys)("spacy"))
    sys.modules["spacy"].load = missing
    assert structural._nlp() is None
    assert structural._extract_sentences("One. Two!") == ["One.", "Two!"]
