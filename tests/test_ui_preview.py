"""The agent can see the UI it built: a real headless render of its own UI.

Real Chromium (``real_browser``): the shipped frame renders the stored
component, its assets and libraries; the report carries what a person would see
and what went wrong -- a PNG, frames per second, uncaught errors, refused
bridge actions -- and nothing reaches a network.
"""
# ruff: noqa: E501 -- embedded JavaScript bundles are stored verbatim
from __future__ import annotations

import io
import struct
import zlib

import pytest

from tinyassets import custom_agents as ca
from tinyassets import ui_preview

OWNER, HOME = "alice", "u-alice"


def _png(rgb=(32, 160, 64), size=8) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))

    raw = b"".join(b"\x00" + bytes(rgb) * size for _ in range(size))
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def _add(base, ui_id, **fields):
    component = {"kind": "tinyassets.app-ui.v1", "version": 1, "ui_id": ui_id,
                 "name": ui_id, "markup": "", "style": "", "script": "", **fields}
    ca.change_app_ui_entry(base, owner_user_id=OWNER, universe_id=HOME,
                           operation="add_ui", payload={"component": component})


def _pixel(png: bytes, x: int, y: int) -> tuple[int, int, int]:
    image = pytest.importorskip("PIL.Image")
    return image.open(io.BytesIO(png)).convert("RGB").getpixel((x, y))


def _need_browser():
    if not ui_preview.available():
        pytest.skip("Playwright is not installed on this host")


@pytest.mark.real_browser
def test_the_agent_sees_its_ui_as_rendered_with_its_assets(tmp_path):
    _need_browser()
    _add(tmp_path, "village",
         markup='<div id=sky></div><img id=grass src="ta-asset:img/grass.png">',
         style="html,body{margin:0}#sky{position:fixed;inset:0;background:#2050c0}"
               "#grass{position:fixed;left:0;bottom:0;width:100%;height:50%}",
         script="(function spin(){requestAnimationFrame(spin);})();"
                "tinyassets.whoami().then(w=>document.title=w.command_center_id);"
                "tinyassets.sendMessage('hello').catch(()=>{});")
    ca.put_app_ui_asset(tmp_path, owner_user_id=OWNER, universe_id=HOME, ui_id="village",
                        path="img/grass.png", data=_png())

    try:
        report = ui_preview.preview_app_ui(tmp_path, owner_user_id=OWNER, universe_id=HOME,
                                           ui_id="village", width=400, height=300)
    except ui_preview.PreviewUnavailable as exc:
        pytest.skip(str(exc))

    assert report["png"].startswith(b"\x89PNG"), "a real screenshot, not a placeholder"
    assert _pixel(report["png"], 200, 40) == (32, 80, 192), "the sky is the UI's own style"
    assert _pixel(report["png"], 200, 260) == (32, 160, 64), "the grass is the stored asset"
    assert report["fps"] and report["fps"] > 5, report["fps"]
    # The reads answer; the action is refused as a preview, and both are reported.
    assert report["bridge_calls"] == {"whoami": 1, "send_message": 1}
    assert report["uncaught_errors"] == [] and report["missing_assets"] == []
    assert report["blocked_requests"] == []


@pytest.mark.real_browser
def test_a_broken_ui_reports_its_error_and_its_blocked_egress(tmp_path):
    _need_browser()
    _add(tmp_path, "broken", libraries=["three"], script_type="module",
         script='import * as THREE from "three";\n'
                'fetch("https://elsewhere.example/x").catch(()=>{});\n'
                'document.body.style.background="#fff";\n'
                'throw new Error("village exploded at r" + THREE.REVISION);')
    try:
        report = ui_preview.preview_app_ui(tmp_path, owner_user_id=OWNER, universe_id=HOME,
                                           ui_id="broken", width=320, height=240)
    except ui_preview.PreviewUnavailable as exc:
        pytest.skip(str(exc))

    assert any("village exploded at r170" in line
               for line in report["uncaught_errors"] + report["console"]), report
    assert any("Refused to connect" in line or "elsewhere.example" in line
               for line in report["console"] + report["blocked_requests"]), report


def test_an_unknown_ui_is_named_not_rendered(tmp_path):
    _add(tmp_path, "village")
    with pytest.raises(ca.AgentNotFoundError, match="installed: \\['village'\\]"):
        ui_preview.preview_app_ui(tmp_path, owner_user_id=OWNER, universe_id=HOME,
                                  ui_id="nope")


def test_another_persons_ui_is_not_reachable(tmp_path):
    _add(tmp_path, "village")
    with pytest.raises(ca.AgentNotFoundError):
        ui_preview.preview_app_ui(tmp_path, owner_user_id="bob", universe_id=HOME,
                                  ui_id="village")


def test_no_browser_is_a_loud_refusal_not_a_blank_image(tmp_path, monkeypatch):
    _add(tmp_path, "village")
    monkeypatch.setattr(ui_preview, "available", lambda: False)
    with pytest.raises(ui_preview.PreviewUnavailable, match="ui_preview_unavailable"):
        ui_preview.preview_app_ui(tmp_path, owner_user_id=OWNER, universe_id=HOME,
                                  ui_id="village")


def test_one_render_at_a_time(tmp_path, monkeypatch):
    _add(tmp_path, "village")
    monkeypatch.setattr(ui_preview, "available", lambda: True)
    assert ui_preview._SLOT.acquire(blocking=False)
    try:
        with pytest.raises(ui_preview.PreviewUnavailable, match="ui_preview_busy"):
            ui_preview.preview_app_ui(tmp_path, owner_user_id=OWNER, universe_id=HOME,
                                      ui_id="village")
    finally:
        ui_preview._SLOT.release()


@pytest.mark.parametrize("width, height", [(10, 300), (300, 5000), ("400", 300)])
def test_the_viewport_is_bounded(tmp_path, width, height):
    _add(tmp_path, "village")
    with pytest.raises(ValueError, match="width and height"):
        ui_preview.preview_app_ui(tmp_path, owner_user_id=OWNER, universe_id=HOME,
                                  ui_id="village", width=width, height=height)


# --------------------------------------------------------------------------- #
# writing the screenshot into the agent's own folder
# --------------------------------------------------------------------------- #


def test_the_screenshot_lands_in_previews_and_replaces_a_planted_hard_link(tmp_path):
    import os

    universe = tmp_path / "u-alice"
    universe.mkdir()
    (universe / "soul.md").write_text("the persona", encoding="utf-8")
    (universe / "previews").mkdir()
    os.link(universe / "soul.md", universe / "previews" / "village.png")

    shown = ui_preview.write_preview(universe, "village", b"\x89PNG-bytes")

    assert shown == "/u/previews/village.png"
    assert (universe / "previews" / "village.png").read_bytes() == b"\x89PNG-bytes"
    assert (universe / "soul.md").read_text(encoding="utf-8") == "the persona", (
        "the write replaced the link instead of writing through it")
    assert sorted(p.name for p in (universe / "previews").iterdir()) == ["village.png"]


@pytest.mark.parametrize("ui_id", ["../soul", "a/b", "", "UPPER", "x" * 65])
def test_only_the_apps_id_shape_names_a_file(tmp_path, ui_id):
    with pytest.raises(ui_preview.PreviewUnavailable, match="ui_id"):
        ui_preview.write_preview(tmp_path, ui_id, b"png")
    assert list(tmp_path.iterdir()) == []


def test_a_previews_entry_that_is_not_a_folder_is_refused(tmp_path):
    (tmp_path / "previews").write_text("a file", encoding="utf-8")
    with pytest.raises(ui_preview.PreviewUnavailable, match="not a plain folder"):
        ui_preview.write_preview(tmp_path, "village", b"png")


@pytest.mark.skipif(__import__("os").name != "posix", reason="needs symlink creation")
def test_a_previews_symlink_is_refused(tmp_path):
    import os

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    universe = tmp_path / "u"
    universe.mkdir()
    os.symlink(elsewhere, universe / "previews")
    with pytest.raises(ui_preview.PreviewUnavailable, match="not a plain folder"):
        ui_preview.write_preview(universe, "village", b"png")
    assert list(elsewhere.iterdir()) == []


# --------------------------------------------------------------------------- #
# the served handle: read_graph target="app_ui_preview"
# --------------------------------------------------------------------------- #


def test_the_engine_handle_renders_writes_and_reports(tmp_path, monkeypatch):
    import json

    import tinyassets.api.helpers as helpers
    from tests.engine_authority_helpers import mock_engine_admission, seed_engine_authority
    from tinyassets import engine_mcp_server as s

    root = tmp_path / "data"
    (root / "u-a").mkdir(parents=True)
    monkeypatch.setattr(helpers, "_base_path", lambda: root)
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(root))
    monkeypatch.setattr(s, "_ACTOR_ID", "actor-a")
    monkeypatch.setattr(s, "_GRAPH_ID", "u-a")
    seed_engine_authority(root, actor="actor-a", graph="u-a")
    mock_engine_admission(monkeypatch, {"u-a"})
    seen = {}

    def fake_render(base, *, owner_user_id, universe_id, ui_id, **_):
        seen.update(owner=owner_user_id, universe=universe_id, ui=ui_id)
        return {"ui_id": ui_id, "fps": 60.0, "uncaught_errors": [], "png": b"\x89PNG-shot"}

    monkeypatch.setattr(ui_preview, "preview_app_ui", fake_render)
    report = json.loads(s.read_graph(target="app_ui_preview", query="village"))

    assert seen == {"owner": "actor-a", "universe": "u-a", "ui": "village"}, (report,
        "the owner and universe come from the binding, never the arguments")
    assert report["screenshot"] == "/u/previews/village.png"
    assert report["see_it"] == 'read path="/u/previews/village.png"'
    assert "png" not in report, "bytes go to the folder, never into the result"
    assert (root / "u-a" / "previews" / "village.png").read_bytes() == b"\x89PNG-shot"

    monkeypatch.setattr(ui_preview, "preview_app_ui", lambda *a, **k: (_ for _ in ()).throw(
        ui_preview.PreviewUnavailable("ui_preview_busy: another preview is rendering")))
    busy = json.loads(s.read_graph(target="app_ui_preview", query="village"))
    assert busy["error"] == "ui_preview_busy"
    missing = json.loads(s.read_graph(target="app_ui_preview", query=""))
    assert missing["error"] == "app_ui_validation_error"


def test_the_browser_sandbox_is_never_turned_off():
    """Playwright launches Chromium with its sandbox OFF unless asked. The UI is
    somebody's code, so the render keeps the browser's own confinement."""
    import inspect

    source = inspect.getsource(ui_preview._child)
    assert "chromium_sandbox=True" in source
    assert "--no-sandbox" not in source
