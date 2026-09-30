#!/usr/bin/env python3
"""Fail when the live sign-in page offers Google without Sign in with Apple.

App Store Review Guideline 4.8: an app that lets people set up or sign in to
their primary account with a third-party or social login (Google Sign-In
among them) must also offer an equivalent login that limits data to name and
email, lets the user hide their email, and does no ad tracking. Sign in with
Apple is that login. TinyAssets' own email/password does not count, because
the exemption covers only apps that use their own sign-in *exclusively*.

The iOS shell signs in through the hosted WorkOS AuthKit page, so the
providers it offers are dashboard configuration, not app code. No test in
the repository can see that setting. This probe reads it off the live page:

    python scripts/authkit_login_parity_probe.py
    python scripts/authkit_login_parity_probe.py --authkit https://<env>.authkit.app

The AuthKit domain is discovered from the issuer the live ``/mcp/app`` page
injects, so a WorkOS environment change is followed automatically.

Each run loads the AuthKit page once, which opens (and abandons) one
unauthenticated authorization session. It sends no credentials.

Exit codes: 0 pass (Apple offered, or no Google), 1 Google offered without
Apple, 2 could not determine (network error, or the page no longer carries a
provider list this probe recognises). 2 must never read as a pass.
"""

from __future__ import annotations

import argparse
import re
import sys
import urllib.error
import urllib.request

DEFAULT_APP_URL = "https://tinyassets.io/mcp/app"
_USER_AGENT = "tinyassets-authkit-login-parity-probe/1"

_ISSUER = re.compile(r'"issuer"\s*:\s*"(https://[^"]+)"')
# Matches both the login hrefs (``/api/login?provider=GoogleOAuth``) and the
# escaped RSC payload (``\"provider\":\"GoogleOAuth\"``).
_PROVIDER = re.compile(r'provider(?:=|\\*"\s*:\s*\\*")([A-Za-z]+)OAuth')
# Present whenever AuthKit rendered its method list, even an empty one.
_METHOD_LIST_MARKER = "oauth_providers"


def fetch(url: str, timeout: float = 30.0) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", "replace")


def authkit_issuer(app_html: str) -> str | None:
    match = _ISSUER.search(app_html)
    return match.group(1).rstrip("/") if match else None


def offered_providers(authkit_html: str) -> set[str] | None:
    """Lower-cased OAuth provider names the page offers; None if unrecognised."""
    providers = {name.lower() for name in _PROVIDER.findall(authkit_html)}
    if not providers and _METHOD_LIST_MARKER not in authkit_html:
        return None
    return providers


def verdict(providers: set[str] | None) -> tuple[int, str]:
    if providers is None:
        return 2, "UNKNOWN: AuthKit page carries no provider list this probe recognises"
    listed = ", ".join(sorted(providers)) or "none"
    if "google" in providers and "apple" not in providers:
        return 1, (
            f"FAIL: offers Google without Sign in with Apple (providers: {listed}); "
            "App Store Guideline 4.8 - see docs/host-actions.md, "
            "'Apple: turn on Sign in with Apple'"
        )
    return 0, f"PASS: providers: {listed}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--app-url", default=DEFAULT_APP_URL)
    parser.add_argument("--authkit", help="AuthKit domain; skips discovery")
    args = parser.parse_args(argv)

    try:
        authkit = args.authkit
        if not authkit:
            authkit = authkit_issuer(fetch(args.app_url))
            if not authkit:
                print(f"UNKNOWN: no AuthKit issuer in {args.app_url}")
                return 2
        providers = offered_providers(fetch(authkit.rstrip("/") + "/"))
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"UNKNOWN: {type(exc).__name__}: {exc}")
        return 2

    code, message = verdict(providers)
    print(f"{authkit}: {message}")
    return code


if __name__ == "__main__":
    sys.exit(main())
