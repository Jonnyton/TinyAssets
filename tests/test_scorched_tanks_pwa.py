from __future__ import annotations

import json
from pathlib import Path

ROOT = (
    Path(__file__).resolve().parents[1]
    / "WebSite"
    / "site"
    / "static"
    / "play"
    / "scorched-tanks"
)


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_scorched_tanks_install_button_has_desktop_fallback() -> None:
    html = _read("index.html")
    original = _read("original.js")

    assert 'id="install-button" class="button" type="button">' in html
    assert "Use the browser menu to install this app" in original
    assert "installButton.disabled = false;" in original


def test_scorched_tanks_pwa_manifest_and_cache_match_runtime_assets() -> None:
    manifest = json.loads(_read("manifest.webmanifest"))
    service_worker = _read("service-worker.js")

    assert manifest["display"] == "standalone"
    assert manifest["start_url"] == "/play/scorched-tanks/"
    assert manifest["scope"] == "/play/scorched-tanks/"
    assert '"./original.js?v=bug043-install"' in service_worker
