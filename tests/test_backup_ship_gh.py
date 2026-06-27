"""Tests for scripts/backup_ship_gh.py — offsite GH release asset upload."""

from __future__ import annotations

import importlib.util
import json
import types
from pathlib import Path

import pytest

# Load the script as a module without executing __main__.
_SCRIPT = Path(__file__).parent.parent / "scripts" / "backup_ship_gh.py"


def _load() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("backup_ship_gh", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bsg = _load()


# ── Helpers ───────────────────────────────────────────────────────────

def _fake_post_fn(responses: list[dict]) -> object:
    """Returns a post_fn that pops responses in order."""
    resp_iter = iter(responses)

    def _fn(req):
        return next(resp_iter)

    return _fn


def _make_tarball(tmp_path: Path, name: str = "tinyassets-data-2026-04-20T02-00-00Z.tar.gz") -> Path:
    p = tmp_path / name
    p.write_bytes(b"\x1f\x8b" + b"\x00" * 100)  # minimal gzip magic bytes
    return p


# ── Token validation ──────────────────────────────────────────────────


def test_ship_exits_1_without_gh_token(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("GH_TOKEN", raising=False)
    tarball = _make_tarball(tmp_path)
    with pytest.raises(SystemExit) as exc:
        bsg.ship(tarball, post_fn=lambda req: {})
    assert exc.value.code == 1


def test_ship_exits_2_when_tarball_missing(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GH_TOKEN", "ghp_test")
    missing = tmp_path / "no-such-file.tar.gz"
    with pytest.raises(SystemExit) as exc:
        bsg.ship(missing, post_fn=lambda req: {})
    assert exc.value.code == 2


# ── ensure_repo ───────────────────────────────────────────────────────


def test_ensure_repo_noop_when_exists() -> None:
    calls = []

    def _post(req):
        calls.append(req.full_url)
        return {"id": 1}

    bsg.ensure_repo("tok", "owner/repo", post_fn=_post)
    assert len(calls) == 1
    assert "/repos/owner/repo" in calls[0]
    assert "user/repos" not in calls[0]


def test_ensure_repo_creates_when_missing() -> None:
    calls = []
    seq = [RuntimeError("404: not found"), {"id": 2}]
    idx = [0]

    def _post(req):
        calls.append(req.full_url)
        resp = seq[idx[0]]
        idx[0] += 1
        if isinstance(resp, Exception):
            raise resp
        return resp

    bsg.ensure_repo("tok", "owner/newrepo", post_fn=_post)
    assert idx[0] == 2
    assert calls == [
        "https://api.github.com/repos/owner/newrepo",
        "https://api.github.com/user/repos",
    ]


def test_ensure_repo_re_raises_non_404() -> None:
    def _post(req):
        raise RuntimeError("500: server error")

    with pytest.raises(RuntimeError, match="500"):
        bsg.ensure_repo("tok", "owner/repo", post_fn=_post)


# ── create_release ────────────────────────────────────────────────────


def test_create_release_posts_correct_tag() -> None:
    captured = []

    def _post(req):
        captured.append(json.loads(req.data.decode()))
        return {"id": 42, "upload_url": "https://uploads.github.com/upload{?name,label}"}

    result = bsg.create_release("tok", "owner/repo", "my-tag", post_fn=_post)
    assert captured[0]["tag_name"] == "my-tag"
    assert result["id"] == 42


# ── _upload_asset ─────────────────────────────────────────────────────


def test_upload_asset_strips_template_suffix(tmp_path) -> None:
    tarball = _make_tarball(tmp_path)
    captured_urls = []

    def _post(req):
        captured_urls.append(req.full_url)
        return {"name": tarball.name, "browser_download_url": "https://example.com"}

    bsg._upload_asset(
        "tok",
        "https://uploads.github.com/repos/owner/repo/releases/1/assets{?name,label}",
        tarball.name,
        tarball,
        post_fn=_post,
    )
    url = captured_urls[0]
    assert "{" not in url
    assert f"name={tarball.name}" in url


def test_upload_asset_uses_gzip_content_type(tmp_path) -> None:
    tarball = _make_tarball(tmp_path)
    captured_headers = []

    def _post(req):
        captured_headers.append(dict(req.headers))
        return {"name": tarball.name}

    bsg._upload_asset("tok", "https://uploads.example.com/upload{?name,label}",
                      tarball.name, tarball, post_fn=_post)
    ct = captured_headers[0].get("Content-type", "")
    assert "gzip" in ct


# ── prune_releases ────────────────────────────────────────────────────


def _make_releases(n: int) -> list[dict]:
    return [
        {"id": i, "tag_name": f"tag-{i:03d}",
         "created_at": f"2026-04-{i + 1:02d}T00:00:00Z"}
        for i in range(1, n + 1)
    ]


def test_prune_releases_keeps_newest(monkeypatch) -> None:
    releases = _make_releases(35)
    deleted_ids = []

    def _post(req):
        if "DELETE" in str(req.get_method()):
            deleted_ids.append(req.full_url)
            return {}
        return releases  # GET releases

    # Monkey-patch list_releases + delete_release to avoid URL parsing noise.
    monkeypatch.setattr(bsg, "list_releases",
                        lambda token, repo, **kw: releases)

    def _del(token, repo, rid, tag, **kw):
        deleted_ids.append(rid)

    monkeypatch.setattr(bsg, "delete_release", _del)

    pruned = bsg.prune_releases("tok", "owner/repo", keep=30)
    assert pruned == 5
    # Oldest 5 (ids 1..5) should be deleted.
    assert set(deleted_ids) == {1, 2, 3, 4, 5}


def test_prune_releases_noop_when_within_limit(monkeypatch) -> None:
    releases = _make_releases(10)
    monkeypatch.setattr(bsg, "list_releases",
                        lambda token, repo, **kw: releases)
    monkeypatch.setattr(bsg, "delete_release", lambda *a, **kw: None)
    pruned = bsg.prune_releases("tok", "owner/repo", keep=30)
    assert pruned == 0


# ── ship() end-to-end ─────────────────────────────────────────────────


def test_ship_dry_run_makes_no_api_calls(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GH_TOKEN", "ghp_test")
    tarball = _make_tarball(tmp_path)
    calls = []
    bsg.ship(tarball, dry_run=True, post_fn=lambda req: calls.append(req) or {})
    assert calls == []


def test_ship_calls_ensure_create_upload_prune(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GH_TOKEN", "ghp_test")
    tarball = _make_tarball(tmp_path)

    steps = []

    def _ensure(token, repo, **kw):
        steps.append("ensure")

    def _create(token, repo, tag, **kw):
        steps.append("create")
        return {"id": 1, "upload_url": "https://uploads.github.com/u{?name,label}"}

    def _upload(token, url, name, path, **kw):
        steps.append("upload")
        return {"name": name, "browser_download_url": "https://example.com"}

    def _prune(token, repo, keep, **kw):
        steps.append("prune")
        return 0

    monkeypatch.setattr(bsg, "ensure_repo", _ensure)
    monkeypatch.setattr(bsg, "create_release", _create)
    monkeypatch.setattr(bsg, "_upload_asset", _upload)
    monkeypatch.setattr(bsg, "prune_releases", _prune)

    bsg.ship(tarball)
    assert steps == ["ensure", "create", "upload", "prune"]


def test_ship_exits_3_on_api_error(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GH_TOKEN", "ghp_test")
    tarball = _make_tarball(tmp_path)

    def _ensure(token, repo, **kw):
        raise RuntimeError("500: server error")

    monkeypatch.setattr(bsg, "ensure_repo", _ensure)

    with pytest.raises(SystemExit) as exc:
        bsg.ship(tarball)
    assert exc.value.code == 3


# ── Tag derivation from filename ──────────────────────────────────────


def test_tag_derived_from_tarball_stem(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GH_TOKEN", "ghp_test")
    tarball = _make_tarball(tmp_path, "tinyassets-data-2026-04-20T02-00-00Z.tar.gz")
    tags_seen = []

    def _ensure(token, repo, **kw):
        pass

    def _create(token, repo, tag, **kw):
        tags_seen.append(tag)
        return {"id": 1, "upload_url": "https://uploads.github.com/u{?name,label}"}

    monkeypatch.setattr(bsg, "ensure_repo", _ensure)
    monkeypatch.setattr(bsg, "create_release", _create)
    monkeypatch.setattr(bsg, "_upload_asset",
                        lambda *a, **kw: {"name": "x"})
    monkeypatch.setattr(bsg, "prune_releases", lambda *a, **kw: 0)

    bsg.ship(tarball)
    assert tags_seen == ["tinyassets-data-2026-04-20T02-00-00Z"]


# ── backup.sh integration ─────────────────────────────────────────────


def test_backup_sh_references_backup_ship_gh() -> None:
    sh = Path(__file__).parent.parent / "deploy" / "backup.sh"
    text = sh.read_text(encoding="utf-8")
    assert "backup_ship_gh.py" in text


def test_backup_sh_gh_token_guard() -> None:
    sh = Path(__file__).parent.parent / "deploy" / "backup.sh"
    text = sh.read_text(encoding="utf-8")
    assert "GH_TOKEN" in text


def test_backup_sh_offsite_is_best_effort() -> None:
    sh = Path(__file__).parent.parent / "deploy" / "backup.sh"
    text = sh.read_text(encoding="utf-8")
    # Non-fatal: script should not exit on GH ship failure.
    assert "WARN" in text or "non-fatal" in text.lower() or "best-effort" in text.lower()


# ── Runbook ───────────────────────────────────────────────────────────


def test_runbook_mentions_gh_restore() -> None:
    runbook = (
        Path(__file__).parent.parent
        / "docs" / "ops" / "backup-restore-runbook.md"
    )
    if not runbook.exists():
        pytest.skip("backup-restore-runbook.md not yet created")
    text = runbook.read_text(encoding="utf-8")
    assert "github" in text.lower() or "gh release" in text.lower()
