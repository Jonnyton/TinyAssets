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

    Code 5 is also shared: the push-notification native change rides the same
    bundle so testers get one update, not two. A lane that bumps again would
    split that into two releases — hence the upper bound, not just a floor.
    """
    release = json.loads((REPO_ROOT / "mobile/android-release.json").read_text(encoding="utf-8"))
    assert release["versionCode"] == 5, (
        "code 5 is the shared slot for the URL move + push notifications; "
        "re-bumping splits one user-visible update in two "
        "(docs/ops/mobile-launch-handoff.md)"
    )
    assert release["versionName"] == "1.0.4"


def test_desktop_shell_loads_the_apex_app_url():
    source = (REPO_ROOT / "desktop-app/config.js").read_text(encoding="utf-8")
    match = re.search(r"PROD_APP_URL\s*=\s*'([^']+)'", source)
    assert match, "PROD_APP_URL is the desktop shell's only load target"
    assert match.group(1) == APP_URL


def test_the_edge_binds_the_app_url_and_leaves_the_connector_alone():
    """Hard Rule 11 plus the move: the connector route is untouched, and the app
    gets its own binding.

    The app route MUST be the `/app*` suffix wildcard, not an exact
    `tinyassets.io/app`. A Cloudflare route is matched against the whole URL
    INCLUDING THE QUERY, so an exact route matches only a bare `/app` and the
    two URLs that carry sign-in and billing — `/app?code=…&state=…` and
    `/app?subscribed=1` — would match nothing and land on the website origin.
    (gpt-6-astra review, 2026-09-29; the earlier exact+subtree pair had this bug.)
    """
    toml = (REPO_ROOT / "deploy/cloudflare-worker/wrangler.toml").read_text(encoding="utf-8")
    patterns = set(re.findall(r'pattern\s*=\s*"([^"]+)"', toml))
    assert "tinyassets.io/mcp*" in patterns
    assert "tinyassets.io/app*" in patterns
    # An exact or subtree-only app binding cannot carry the callback queries.
    assert "tinyassets.io/app" not in patterns
    assert "tinyassets.io/app/*" not in patterns


def test_the_worker_hands_app_prefixed_website_assets_back():
    """The cost of the wildcard, and the code that pays it.

    `/app*` also captures apex assets whose path merely starts with "app", so
    the Worker must pass exactly those to the website origin rather than answer
    404 on the site's behalf. Asserted together with the asset actually existing,
    so the guard cannot outlive its reason.
    """
    worker = (REPO_ROOT / "deploy/cloudflare-worker/worker.js").read_text(encoding="utf-8")
    assert "function belongsToWebsite" in worker
    assert "passToWebsiteOrigin" in worker
    assert (REPO_ROOT / "WebSite/site-react/public/apple-touch-icon.png").is_file(), (
        "the pass-through exists for a real apex asset whose path starts with "
        "'app'; if the site stops serving one, re-derive the route shape"
    )


def test_the_retirement_provers_actually_assert_the_retirement():
    """An exemption has to earn itself.

    `probe_app_surface.py` is allowed to name `/mcp/app` only because it probes
    that the path is gone. If it stopped doing that, the exemption would be a
    blind spot rather than a carve-out.

    Checked by BEHAVIOUR, not by a substring of the source: an earlier version
    of this test asserted error-message text, which proved only that a string
    existed and went stale the moment the wording changed.
    """
    from scripts import probe_app_surface

    assert probe_app_surface.RETIRED_APP_PATH == RETIRED
    for rel in RETIREMENT_PROVERS:
        assert (REPO_ROOT / rel).is_file(), rel

    # Statuses that mean "this still works" must not be accepted as retirement.
    accepted = probe_app_surface.RETIRED_OK_STATUSES
    assert 200 not in accepted
    assert not any(300 <= status < 400 for status in accepted)
    assert not any(status >= 500 for status in accepted)
    assert accepted, "an empty set would make the check unsatisfiable, not strict"


def test_published_app_link_is_the_apex_url():
    site = (REPO_ROOT / "WebSite/site-react/lib/site.ts").read_text(encoding="utf-8")
    assert f'app: "{APP_URL}"' in site
