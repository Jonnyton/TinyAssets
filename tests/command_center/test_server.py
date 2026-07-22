"""Smoke tests for command_center.server — real HTTP on an ephemeral port."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from command_center import collector
from command_center.server import make_handler


@pytest.fixture()
def village(tmp_path: Path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "workflow").mkdir()
    table = "| Task | Files | Depends | Status |\n|------|-------|---------|--------|\n"
    (root / "STATUS.md").write_text(table, encoding="utf-8")
    cfg = collector.Config(
        root=root,
        directory_url=None,
        inbox_dir=root / ".agents" / "village-inbox",
        claude_home=tmp_path / "c",
        codex_home=tmp_path / "x",
        kimi_home=tmp_path / "k",
        data_dirs=[],
    )
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cfg, _NullCache(cfg)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield cfg, httpd.server_address[1]
    httpd.shutdown()
    httpd.server_close()


class _NullCache:
    """StateCache stub: no poller thread, single fresh snapshot."""

    def __init__(self, cfg: collector.Config) -> None:
        self._snap = collector.snapshot(cfg)

    def get(self) -> dict:
        return self._snap


def _get(port: int, path: str) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def test_index_served(village):
    _, port = village
    status, body = _get(port, "/")
    assert status == 200
    assert b"Agent Village" in body


def test_static_assets_served(village):
    _, port = village
    for path, marker in (("/app.css", b"--grass-1"), ("/app.js", b"POLL_MS"),
                         ("/favicon.svg", b"<svg"), ("/manifest.webmanifest", b"Agent Village")):
        status, body = _get(port, path)
        assert status == 200, path
        assert marker in body, path


def test_state_endpoint(village):
    _, port = village
    status, body = _get(port, "/api/state")
    assert status == 200
    data = json.loads(body)
    for key in ("zones", "agents", "universes", "events", "stats", "world"):
        assert key in data


def test_talk_and_chat_roundtrip(village):
    _, port = village
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/talk",
        data=json.dumps({"target": "agent:kimi-abc", "message": "hello sprite"}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        result = json.loads(resp.read())
    assert result["ok"] is True
    status, body = _get(port, "/api/chat?target=agent:kimi-abc")
    assert status == 200
    messages = json.loads(body)["messages"]
    assert any("hello sprite" in m["text"] for m in messages)


def test_talk_validation(village):
    _, port = village
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/talk",
        data=json.dumps({"target": "", "message": ""}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        urllib.request.urlopen(req, timeout=5)
    assert excinfo.value.code == 400


def test_token_gate(tmp_path: Path):
    root = tmp_path / "repo"
    root.mkdir()
    cfg = collector.Config(
        root=root, token="s3cret", directory_url=None,
        claude_home=tmp_path / "c", codex_home=tmp_path / "x", kimi_home=tmp_path / "k",
        data_dirs=[],
    )
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cfg, _NullCache(cfg)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    port = httpd.server_address[1]
    try:
        status, _ = _get(port, "/api/state")
        assert status == 401
        status, body = _get(port, "/api/state?token=s3cret")
        assert status == 200
    finally:
        httpd.shutdown()
        httpd.server_close()
