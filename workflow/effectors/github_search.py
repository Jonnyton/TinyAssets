"""search_repo_files: a platform-trusted opaque node that finds repo file paths.

The localization counterpart to ``read_repo_files``. A free-text patch request
("fix the wiki file_bug dedup", "compute_payout_shares returns floats") names a
*concept*, not a path. This node lets a user-buildable loop turn that concept
into concrete repo-relative paths: a node named ``search_repo_files`` (in the
``workflow`` domain) lists the repository's file paths (via the GitHub Git Trees
API) and returns those whose path matches the caller's query terms/globs. A
downstream ``read_repo_files`` node then reads the matched files, so the loop can
edit existing files it was only able to *describe*.

Design note: docs/design-notes/2026-05-29-repo-search-primitive.md
(Option A — opaque domain callable; sibling of read_repo_files PR #1152).

Why path-search (not content grep): the GitHub *code-search* API requires
authentication, only indexes the default branch, and lags behind HEAD. The Git
Trees API is unauthenticated for public repos, reflects the exact ref, and has
no indexing lag — so path-name search is the minimal, robust building block that
matches our subscription-only / no-API-key posture. Content grep, if ever
needed, is a separate primitive.

Contract (opaque callable — ``fn(state) -> dict`` of state updates):

  reads from state:
    - ``search_destination`` (str): ``owner/repo`` to search. Falls back to
      ``read_destination`` / ``destination`` so it composes with read_repo_files
      without re-declaring the repo.
    - ``search_query`` (str): whitespace/comma/semicolon-separated terms. A term
      containing glob chars (``* ? [ ]``) is matched as an fnmatch glob against
      the repo-relative path; otherwise it is a case-insensitive substring match.
      Dotted module names (``workflow.api.wiki``) also match their slash form
      (``workflow/api/wiki``).
    - ``search_ref`` (str, optional): branch/tag/sha to search. Empty => the
      repo's default branch.
  writes to state:
    - ``matched_paths_json`` (str): JSON array of matching repo-relative paths,
      best-match first, capped at the result limit.
    - ``search_status_json`` (str): JSON object with query, ref, total_blobs,
      matched, returned, ``truncated`` (bool), and ``error`` (kind or null).

Build decisions (mirror read_repo_files):
  1. Read scope — resolves a token from ``WORKFLOW_GITHUB_READ_CAPABILITIES``
     (search IS a read; it shares the read scope, NOT the write map). Empty =>
     unauthenticated, which works for public repos (rate-limited).
  2. The platform callable enforces caps (result count, query length) — never
     node config.
  3. Distinct ``error`` kinds; never raises.
  4. Platform-trusted opaque callable — referenced by id, body not user-supplied.
"""

from __future__ import annotations

import fnmatch
import json
import logging
import os
import re
import urllib.error
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

_GITHUB_API = "https://api.github.com"
_READ_CAPABILITIES_ENV = "WORKFLOW_GITHUB_READ_CAPABILITIES"
_SEARCH_TIMEOUT_S = 30.0

_DEFAULT_MAX_RESULTS = 50
_MAX_QUERY_CHARS = 2000
_MAX_TERMS = 40

DOMAIN_ID = "workflow"
NODE_ID = "search_repo_files"

_REPO_RE = re.compile(r"[\w.-]+/[\w.-]+")
_GLOB_CHARS = re.compile(r"[*?\[\]]")


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        val = int(raw)
    except ValueError:
        return default
    return val if val > 0 else default


def _read_token(destination: str) -> str:
    """Resolve a READ-scoped token for ``destination`` (empty if none).

    Shares the read capability map with read_repo_files — search is a read.
    Empty string => unauthenticated read (public repos).
    """
    raw = os.environ.get(_READ_CAPABILITIES_ENV, "").strip()
    if not raw:
        return ""
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        logger.warning(
            "%s is set but not valid JSON; treating search as unauthenticated",
            _READ_CAPABILITIES_ENV,
        )
        return ""
    if not isinstance(parsed, dict):
        return ""
    token = parsed.get(destination, "")
    return token.strip() if isinstance(token, str) else ""


def _parse_terms(raw: object) -> list[str]:
    """Parse search_query into match terms (whitespace/comma/semicolon split)."""
    text = str(raw or "").strip()
    if not text:
        return []
    text = text[:_MAX_QUERY_CHARS]
    out: list[str] = []
    seen: set[str] = set()
    for piece in re.split(r"[\s,;]+", text):
        term = piece.strip()
        if term and term not in seen:
            seen.add(term)
            out.append(term)
        if len(out) >= _MAX_TERMS:
            break
    return out


def _http_get_json(url: str, token: str) -> tuple[object | None, dict | None]:
    """GET a GitHub JSON endpoint. Returns ``(parsed, error)``."""
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "workflow-github-search/1.0",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, method="GET", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=_SEARCH_TIMEOUT_S) as resp:
            raw = resp.read().decode("utf-8")
            return (json.loads(raw) if raw.strip() else {}), None
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:200]
        return None, {"http_status": exc.code, "detail": detail}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return None, {"http_status": None, "detail": str(exc)}
    except (TypeError, ValueError) as exc:
        return None, {"http_status": None, "detail": f"parse error: {exc}"}


def _resolve_ref(destination: str, ref: str, token: str) -> tuple[str | None, dict | None]:
    """Return a usable tree-ish ref. Empty ref => repo default branch."""
    if ref:
        return ref, None
    parsed, err = _http_get_json(f"{_GITHUB_API}/repos/{destination}", token)
    if err is not None:
        return None, err
    default_branch = (parsed or {}).get("default_branch") if isinstance(parsed, dict) else None
    return (default_branch or "main"), None


def _list_tree_paths(
    destination: str, ref: str, token: str
) -> tuple[list[str] | None, bool, dict | None]:
    """List repo-relative blob paths at ``ref``. Returns (paths, truncated, error)."""
    encoded_ref = urllib.parse.quote(ref, safe="")
    url = f"{_GITHUB_API}/repos/{destination}/git/trees/{encoded_ref}?recursive=1"
    parsed, err = _http_get_json(url, token)
    if err is not None:
        return None, False, err
    if not isinstance(parsed, dict):
        return None, False, {"http_status": None, "detail": "unexpected tree shape"}
    tree = parsed.get("tree")
    if not isinstance(tree, list):
        return None, False, {"http_status": None, "detail": "tree missing"}
    paths = [
        entry["path"]
        for entry in tree
        if isinstance(entry, dict) and entry.get("type") == "blob" and entry.get("path")
    ]
    return paths, bool(parsed.get("truncated")), None


def _term_variants(term: str) -> list[str]:
    """Match variants for a term: dotted module names also match slash form."""
    variants = [term]
    if "." in term and not _GLOB_CHARS.search(term):
        slashed = term.replace(".", "/")
        if slashed != term:
            variants.append(slashed)
    return variants


def _match_rank(path: str, terms: list[str]) -> int:
    """Rank a path against terms. 0 = no match; higher = better.

    3 = a term matches the basename exactly or as a prefix;
    2 = a term matches inside the basename (or glob matches the path);
    1 = a term matches inside the full path only.
    """
    lower = path.lower()
    basename = path.rsplit("/", 1)[-1].lower()
    best = 0
    for term in terms:
        for variant in _term_variants(term):
            v = variant.lower()
            if _GLOB_CHARS.search(variant):
                if fnmatch.fnmatch(lower, v) or fnmatch.fnmatch(basename, v):
                    best = max(best, 2)
                continue
            if basename == v or basename.startswith(v):
                best = max(best, 3)
            elif v in basename:
                best = max(best, 2)
            elif v in lower:
                best = max(best, 1)
    return best


def search_repo_files(state: dict) -> dict:
    """Opaque-node body: find repo file paths matching the query. Never raises."""
    destination = str(
        state.get("search_destination")
        or state.get("read_destination")
        or state.get("destination")
        or ""
    ).strip().strip("/")
    matched: list[str] = []
    status: dict[str, object] = {
        "query": str(state.get("search_query") or "").strip(),
        "ref": "",
        "total_blobs": 0,
        "matched": 0,
        "returned": 0,
        "truncated": False,
        "error": None,
    }

    def _emit() -> dict:
        return {
            "matched_paths_json": json.dumps(matched, ensure_ascii=False),
            "search_status_json": json.dumps(status, ensure_ascii=False),
        }

    if not destination or not _REPO_RE.fullmatch(destination):
        status["error"] = "search_destination_invalid"
        return _emit()

    terms = _parse_terms(state.get("search_query"))
    if not terms:
        status["error"] = "no_search_query"
        return _emit()

    max_results = _int_env("WORKFLOW_GITHUB_SEARCH_MAX_RESULTS", _DEFAULT_MAX_RESULTS)
    token = _read_token(destination)

    ref, err = _resolve_ref(destination, str(state.get("search_ref") or "").strip(), token)
    if err is not None:
        code = err.get("http_status")
        status["error"] = (
            "search_tree_denied" if code in (401, 403, 404) else "search_ref_unresolved"
        )
        return _emit()
    status["ref"] = ref

    paths, truncated, err = _list_tree_paths(destination, ref, token)
    if err is not None:
        code = err.get("http_status")
        status["error"] = (
            "search_tree_denied" if code in (401, 403, 404) else "search_request_failed"
        )
        return _emit()

    status["total_blobs"] = len(paths or [])
    status["truncated"] = truncated  # GitHub truncates the tree itself at ~100k entries

    ranked: list[tuple[int, str]] = []
    for path in paths or []:
        rank = _match_rank(path, terms)
        if rank > 0:
            ranked.append((rank, path))
    # Best match first; stable secondary sort by path for determinism.
    ranked.sort(key=lambda item: (-item[0], item[1]))

    status["matched"] = len(ranked)
    matched = [p for _, p in ranked[:max_results]]
    status["returned"] = len(matched)
    if len(ranked) > max_results:
        status["truncated"] = True
    return _emit()


def register_search_repo_files() -> None:
    """Register the search_repo_files opaque callable for the workflow domain.

    Idempotent. Called from workflow/effectors/__init__.py at import so a branch
    that uses it resolves a body at compile time.
    """
    from workflow.domain_registry import register_domain_callable

    register_domain_callable(DOMAIN_ID, NODE_ID, search_repo_files)


__all__ = [
    "search_repo_files",
    "register_search_repo_files",
    "DOMAIN_ID",
    "NODE_ID",
]
