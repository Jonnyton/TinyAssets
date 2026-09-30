"""The app's one public URL is `https://tinyassets.io/app`.

Founder directive 2026-09-30: move off `/mcp/app` cleanly — no redirect, no
alias, no back-compat. That makes this a *drift* problem, not a routing one: the
daemon can serve `/app` perfectly while an installed shell, a probe, or a
published link still asks for `/mcp/app` and gets a 404.

So this file scans the shipped surfaces themselves rather than restating what
other tests already assert about routes:

* the clients that are compiled/installed and cannot be hot-fixed (the Android
  shell's `server.url`, the desktop shell's `PROD_APP_URL`),
* the edge config that decides whether the URL resolves at all,
* the probes and published links a reader is told to trust.

History files (`docs/audits/`, `docs/reviews/`, `docs/concerns/`, archived
openspec changes, captured session output) are deliberately NOT scanned: they
record what was true at the time, and rewriting them would falsify the record.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

APP_URL = "https://tinyassets.io/app"
RETIRED = "/mcp/app"

#: Surfaces a user or an installed binary actually reaches. Every one of these
#: is a place the old path would still be live if the move were half-done.
LIVE_SURFACES = (
    "tinyassets",
    "scripts",
    "deploy/compose.yml",
    "deploy/cloudflare-worker/wrangler.toml",
    "desktop-app",
    "mobile",
    "WebSite",
    "openspec/specs",
)

#: Files whose remaining mentions are prose ABOUT the move — a comment or a spec
#: clause naming the path it moved off, which is worth keeping so the next reader
#: knows why `/mcp/app` 404s. They are not exempted from the scan wholesale: they
#: are held to the stricter `_USED_AS_A_PATH` test below, so an actual string
#: literal or URL sneaking back in still fails.
PROSE_EXEMPT = {
    "deploy/cloudflare-worker/worker.js",
    "deploy/cloudflare-worker/wrangler.toml",
    "tinyassets/auth/middleware.py",
    "tinyassets/onboarding/__init__.py",
    "scripts/cloud_only_preflight.py",
    # The spec states the retirement itself ("/mcp/app* SHALL NOT be mounted").
    "openspec/specs/live-mcp-connector-surface/spec.md",
}

#: The old path *used*, rather than talked about: a quoted string, a full URL, or
#: the regex-escaped form the SPA held its callback prefix in.
_USED_AS_A_PATH = re.compile(
    r"""["'(]/mcp/app|https?://[^\s"']*/mcp/app|\\/mcp\\/app""",
)

#: Files whose whole job is to PROVE the old path is dead, so they must name it
#: as a live string. Fully exempt from the scan — and held to
#: `test_the_retirement_provers_actually_assert_the_retirement` instead, so the
#: exemption cannot quietly become somewhere drift hides.
RETIREMENT_PROVERS = {"scripts/probe_app_surface.py"}

_TEXT_SUFFIXES = {
    ".py", ".js", ".ts", ".tsx", ".json", ".html", ".md", ".txt", ".toml",
    ".yml", ".yaml", ".css",
}


def _iter_files(target: str):
    path = REPO_ROOT / target
    if path.is_file():
        yield path
        return
    for child in path.rglob("*"):
        if not child.is_file() or child.suffix.lower() not in _TEXT_SUFFIXES:
            continue
        parts = set(child.relative_to(REPO_ROOT).parts)
        if parts & {"node_modules", "dist", "build", ".next", "__pycache__"}:
            continue
        yield child


@pytest.mark.parametrize("target", LIVE_SURFACES)
def test_no_live_surface_still_points_at_the_retired_path(target):
    offenders = []
    for path in _iter_files(target):
        rel = path.relative_to(REPO_ROOT).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if rel in RETIREMENT_PROVERS:
            continue
        if rel in PROSE_EXEMPT:
            # Prose is allowed; the path being USED is not.
            if _USED_AS_A_PATH.search(text):
                offenders.append(rel)
            continue
        # Match the escaped form too: the SPA held the callback prefix as a
        # regex literal (`/^\/mcp\/app\/model-callback\/...`), which a plain
        # search for the path missed and a test caught only by its behaviour.
        if RETIRED in text or r"\/mcp\/app" in text:
            offenders.append(rel)
    assert not offenders, (
        f"these shipped surfaces still reference {RETIRED}: {offenders}. "
        f"The app lives only at {APP_URL}; the old path is not served."
    )


def test_android_shell_loads_the_apex_app_url():
    """The installed Play shell is the surface that cannot be hot-fixed.

    A wrong URL here means every install is dark until a new bundle ships and a
    user updates, which is exactly why the move bumps the release.
    """
    config = json.loads((REPO_ROOT / "mobile/capacitor.config.json").read_text(encoding="utf-8"))
    assert config["server"]["url"] == APP_URL
    # Same host as before, so the navigation allow-list is unaffected — asserted
    # so a future URL change cannot quietly strand it.
    assert config["server"]["allowNavigation"] == ["tinyassets.io"]


def test_android_release_is_bumped_past_the_shipped_play_build():
    """1.0.3 / code 4 is on Play pointed at the dead path.

    Play refuses a versionCode it has seen, so the fix for installed users IS
    the bump; a green repo with code 4 would ship nothing.
    """
    release = json.loads((REPO_ROOT / "mobile/android-release.json").read_text(encoding="utf-8"))
    assert release["versionCode"] >= 5
    assert release["versionName"] != "1.0.3"


def test_desktop_shell_loads_the_apex_app_url():
    source = (REPO_ROOT / "desktop-app/config.js").read_text(encoding="utf-8")
    match = re.search(r"PROD_APP_URL\s*=\s*'([^']+)'", source)
    assert match, "PROD_APP_URL is the desktop shell's only load target"
    assert match.group(1) == APP_URL


def test_the_edge_binds_the_app_url_and_leaves_the_connector_alone():
    """Hard Rule 11 plus the move: the connector route is untouched, and the app
    gets its own binding.

    Bound as `/app` + `/app/*` rather than one `/app*` suffix: Cloudflare's `*`
    matches any character, so `/app*` would also capture apex website assets
    that merely start with "app" — `/apple-touch-icon.png` is one the site ships.
    """
    toml = (REPO_ROOT / "deploy/cloudflare-worker/wrangler.toml").read_text(encoding="utf-8")
    patterns = set(re.findall(r'pattern\s*=\s*"([^"]+)"', toml))
    assert "tinyassets.io/mcp*" in patterns
    assert "tinyassets.io/app" in patterns
    assert "tinyassets.io/app/*" in patterns
    assert "tinyassets.io/app*" not in patterns
    assert (REPO_ROOT / "WebSite/site-react/public/apple-touch-icon.png").is_file(), (
        "the /app* hazard this route shape avoids is only real while the site "
        "actually serves an app-prefixed apex asset"
    )


def test_the_retirement_provers_actually_assert_the_retirement():
    """An exemption has to earn itself.

    `probe_app_surface.py` is allowed to name `/mcp/app` only because it probes
    that the path is gone. If it stopped doing that, the exemption would be a
    blind spot rather than a carve-out.
    """
    from scripts import probe_app_surface

    assert probe_app_surface.RETIRED_APP_PATH == RETIRED
    for rel in RETIREMENT_PROVERS:
        assert (REPO_ROOT / rel).is_file(), rel
    # The probe must treat both "still serving" and "redirects" as failures.
    source = (REPO_ROOT / "scripts/probe_app_surface.py").read_text(encoding="utf-8")
    assert "the move is not complete" in source
    assert "back-compat" in source


def test_published_app_link_is_the_apex_url():
    site = (REPO_ROOT / "WebSite/site-react/lib/site.ts").read_text(encoding="utf-8")
    assert f'app: "{APP_URL}"' in site
