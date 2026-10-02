"""S0 of the app.html split: the ES-module route, its allowlist and CSP grant.

docs/design-notes/2026-10-01-split-app-html-into-es-modules.md. Nothing loads a
module yet; these pin the serving contract S1 relies on.
"""

from __future__ import annotations

import anyio
import pytest

from tinyassets.auth.middleware import _auth_challenge_path
from tinyassets.onboarding import _csp, app_modules, onboarding_routes

SHA = "0123456789abcdef0123456789abcdef01234567"


class _Request:
    def __init__(self, build: str, name: str, method: str = "GET") -> None:
        self.path_params = {"build": build, "name": name}
        self.method = method


def _get(build: str, name: str, method: str = "GET"):
    return anyio.run(app_modules.handle_app_module, _Request(build, name, method))


@pytest.fixture
def live(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("TINYASSETS_ONBOARDING_APP", "1")
    monkeypatch.setattr("tinyassets.onboarding.build_sha", lambda: SHA)
    return SHA


def test_the_entry_module_is_served_as_cacheable_javascript(live):
    response = _get(live, "main.js")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/javascript")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "immutable" in response.headers["cache-control"]
    assert bytes(response.body) == (app_modules.MODULE_DIR / "main.js").read_bytes()
    assert _get(live, "main.js", "HEAD").status_code == 200


@pytest.mark.parametrize(
    "name",
    ["nope.js", "Main.js", "main.mjs", "main.js.map", "../app.html", "..%2Fapp.html",
     "app.html", "", "main"],
)
def test_only_allowlisted_basenames_are_served(live, name):
    assert _get(live, name).status_code == 404


def test_another_builds_modules_are_refused(live):
    """A stale page reloads on the build check; it never imports newer code."""
    assert _get("f" * 40, "main.js").status_code == 404
    assert _get(app_modules.DEV_BUILD, "main.js").status_code == 404


def test_dev_build_is_served_uncached(monkeypatch):
    monkeypatch.setenv("TINYASSETS_ONBOARDING_APP", "1")
    monkeypatch.setattr("tinyassets.onboarding.build_sha", lambda: "")
    response = _get(app_modules.DEV_BUILD, "main.js")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"


def test_the_dark_flag_hides_modules(monkeypatch):
    monkeypatch.delenv("TINYASSETS_ONBOARDING_APP", raising=False)
    monkeypatch.setattr("tinyassets.onboarding.build_sha", lambda: SHA)
    assert _get(SHA, "main.js").status_code == 404


def test_the_route_is_registered_for_reads_only():
    routes = [r for r in onboarding_routes() if getattr(r, "path", "") == "/app/m/{build}/{name}"]
    assert len(routes) == 1
    assert set(routes[0].methods) == {"GET", "HEAD"}


def test_the_auth_carve_out_is_exactly_the_module_shape():
    assert not _auth_challenge_path(f"/app/m/{SHA}/main.js")
    for near in (
        f"/app/m/{SHA}/main.js/x", f"/app/m/{SHA}/../me", f"/app/m/{SHA}/main.json",
        f"/app/m/{SHA}/sub/main.js", "/app/m/main.js", f"/app/m/{SHA}/", "/app/m",
        f"/app/m/{SHA}/Main.js", "/app/me",
    ):
        assert _auth_challenge_path(near), near


def test_the_csp_grants_the_module_path_and_never_strict_dynamic():
    policy = _csp("n0nce", "https://auth.example", "https://tinyassets.io/mcp")
    script = next(d for d in policy.split(";") if d.strip().startswith("script-src"))
    assert script.split() == ["script-src", "'nonce-n0nce'", "https://tinyassets.io/app/m/"]
    assert "strict-dynamic" not in policy and "'self'" not in script
    # No resource origin: no module grant at all, still nonce-only.
    bare = _csp("n0nce", "", "")
    assert "script-src 'nonce-n0nce';" in bare


def test_module_files_ship_with_the_package():
    """Data a feature reads must be packaged: the Docker image copies tinyassets/."""
    assert "main.js" in app_modules.module_names()
