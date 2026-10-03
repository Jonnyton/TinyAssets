"""Tests for the Guideline 4.8 probe: Google sign-in needs Sign in with Apple.

No network. The fixtures are trimmed from the live AuthKit page captured on
2026-09-29, which offered Google, password and SSO, and no Apple.
"""

from __future__ import annotations

import importlib.util
import sys
import urllib.error
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def load():
    path = REPO_ROOT / "scripts" / "authkit_login_parity_probe.py"
    spec = importlib.util.spec_from_file_location("authkit_parity_under_test", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


probe = load()


def _button(method: str, provider: str) -> str:
    return (
        f'<div class="ak-AuthMethodButton" data-method="{method}">'
        f'<a href="/api/login?provider={provider}&amp;redirect_uri=https%3A%2F%2F'
        f'tinyassets.io%2Fmcp%2Fapp">Continue with {method.title()}</a></div>'
    )


def _payload(*providers: str) -> str:
    entries = ",".join(
        f'{{\\"name\\":\\"{p.lower()}\\",\\"authorize_params\\":'
        f'{{\\"provider\\":\\"{p}OAuth\\"}}}}'
        for p in providers
    )
    return f'{{\\"authMethods\\":{{\\"password\\":true,\\"oauth_providers\\":[{entries}]}}}}'


GOOGLE_ONLY = _button("google", "GoogleOAuth") + _payload("Google")
GOOGLE_AND_APPLE = (
    _button("google", "GoogleOAuth") + _button("apple", "AppleOAuth")
    + _payload("Google", "Apple")
)
NO_OAUTH = _payload()
UNRECOGNISED = "<html><body>Something went wrong</body></html>"


def test_google_without_apple_fails():
    providers = probe.offered_providers(GOOGLE_ONLY)
    assert providers == {"google"}
    code, message = probe.verdict(providers)
    assert code == 1
    assert "4.8" in message


def test_google_with_apple_passes():
    assert probe.offered_providers(GOOGLE_AND_APPLE) == {"google", "apple"}
    assert probe.verdict({"google", "apple"})[0] == 0


def test_payload_alone_is_enough_to_see_google():
    # If AuthKit ever stops rendering buttons server-side, the RSC payload
    # still names the provider; losing both must not read as "no Google".
    assert probe.offered_providers(_payload("Google")) == {"google"}


def test_rendered_list_without_oauth_passes():
    providers = probe.offered_providers(NO_OAUTH)
    assert providers == set()
    assert probe.verdict(providers) == (0, "PASS: providers: none")


def test_unrecognised_page_is_unknown_not_pass():
    assert probe.offered_providers(UNRECOGNISED) is None
    assert probe.verdict(None)[0] == 2


def test_issuer_is_read_from_the_app_config():
    app = 'const CFG = {"build": "x", "issuer": "https://env-1.authkit.app", "a": 1};'
    assert probe.authkit_issuer(app) == "https://env-1.authkit.app"
    assert probe.authkit_issuer("<html></html>") is None


def test_main_discovers_authkit_and_fails(monkeypatch, capsys):
    pages = {
        "https://tinyassets.io/app": '{"issuer": "https://env-1.authkit.app"}',
        "https://env-1.authkit.app/": GOOGLE_ONLY,
    }
    fetched = []

    def fake_fetch(url, timeout=30.0):
        fetched.append(url)
        return pages[url]

    monkeypatch.setattr(probe, "fetch", fake_fetch)
    assert probe.main([]) == 1
    assert fetched == ["https://tinyassets.io/app", "https://env-1.authkit.app/"]
    assert "FAIL" in capsys.readouterr().out


def test_main_missing_issuer_is_unknown(monkeypatch):
    monkeypatch.setattr(probe, "fetch", lambda url, timeout=30.0: "<html></html>")
    assert probe.main([]) == 2


def test_main_network_error_is_unknown(monkeypatch):
    def boom(url, timeout=30.0):
        raise urllib.error.URLError("unreachable")

    monkeypatch.setattr(probe, "fetch", boom)
    assert probe.main(["--authkit", "https://env-1.authkit.app"]) == 2
