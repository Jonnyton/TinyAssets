"""The web app's ES modules, served as static files from ``tinyassets/onboarding/app/``.

app.html carries the whole web app in one inline script. The split
(docs/design-notes/2026-10-01-split-app-html-into-es-modules.md) moves that
script into native ES modules the page imports from ``/app/m/<build>/<name>.js``.
This module is S0: the route, its allowlist and the CSP grant, with nothing
loaded yet.

* **Allowlist, not a path.** Only basenames of ``.js`` files present in the
  module directory are served (``[a-z0-9_]+.js``); there is no path join of
  request input, so ``..``, ``/`` or an encoded variant can only ever 404.
* **Build-keyed.** ``<build>`` must equal the deployed build. The page embeds
  its build and reloads itself when the server moves on (the existing
  ``X-TinyAssets-Build`` check), so a stale page never imports another build's
  modules: a mismatch is a 404, not newer code under an older page. With a real
  build the response is cacheable forever (``immutable``); in dev it is not.
* **Public.** Like ``/app`` and ``/app/sw.js`` the modules load before any
  bearer exists. They are static, carry no secret and no identity; the auth
  middleware exempts exactly this path shape (``is_module_path``).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

MODULE_DIR = Path(__file__).resolve().parent / "app"
_NAME_RE = re.compile(r"^[a-z0-9_]{1,64}\.js$")
_BUILD_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
#: Exactly one build segment and one module basename; nothing deeper.
_PATH_RE = re.compile(r"^/app/m/[A-Za-z0-9._-]{1,64}/[a-z0-9_]{1,64}\.js$")
DEV_BUILD = "dev"


def module_names() -> frozenset[str]:
    """The servable basenames: ``.js`` files present in the module directory."""
    if not MODULE_DIR.is_dir():
        return frozenset()
    return frozenset(
        p.name for p in MODULE_DIR.iterdir() if p.is_file() and _NAME_RE.fullmatch(p.name)
    )


def build_segment() -> str:
    """The URL segment for the deployed build, or ``dev`` when it is unknown."""
    from tinyassets.onboarding import build_sha

    sha = build_sha()
    return sha if sha and _BUILD_RE.fullmatch(sha) else DEV_BUILD


def module_url(name: str) -> str:
    return f"/app/m/{build_segment()}/{name}"


def is_module_path(path: str) -> bool:
    """The exact public path shape, for the auth middleware's carve-out."""
    return _PATH_RE.fullmatch(path) is not None


def script_source(resource: str) -> str:
    """The CSP ``script-src`` entry that admits the modules and nothing else.

    A path-restricted host source (``https://tinyassets.io/app/m/``), derived
    from the connector's public resource URL so it names the public origin even
    behind the tunnel. Deliberately NOT ``'strict-dynamic'``: that would let any
    script the page's trusted code inserted execute, and this page's CSP is
    nonce-only so that a bug inserting bundle script still runs nothing. An
    injected ``<script src>`` under this path can only load one of our own
    allowlisted module files. Empty when the origin is unknown (no modules load).
    """
    from urllib.parse import urlsplit

    parts = urlsplit(resource or "")
    if parts.scheme not in ("https", "http") or not parts.netloc:
        return ""
    return f"{parts.scheme}://{parts.netloc}/app/m/"


async def handle_app_module(request: Any) -> Any:
    """``GET``/``HEAD /app/m/{build}/{name}``: one allowlisted module, or 404."""
    from starlette.responses import PlainTextResponse, Response

    from tinyassets.onboarding import onboarding_enabled

    build = request.path_params.get("build", "")
    name = request.path_params.get("name", "")
    current = build_segment()
    if not onboarding_enabled() or build != current or name not in module_names():
        return PlainTextResponse("Not Found", status_code=404)
    headers = {
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": (
            "no-cache" if current == DEV_BUILD else "public, max-age=31536000, immutable"
        ),
    }
    media = "text/javascript; charset=utf-8"
    if request.method == "HEAD":
        return Response(status_code=200, media_type=media, headers=headers)
    return Response((MODULE_DIR / name).read_bytes(), media_type=media, headers=headers)
