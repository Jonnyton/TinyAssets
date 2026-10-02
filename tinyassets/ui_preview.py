"""Render a person's own custom UI headlessly, so the agent that built it can see it.

The agent that writes a UI has no browser: it cannot tell whether its village
renders, how it looks, or whether it runs at a usable frame rate (founder's live
test, 2026-10-02). This renders ONE UI of the caller's own library in a headless
Chromium and reports what a person would see: a PNG of the screen, frames per
second over a short window, console errors and uncaught exceptions, the bridge
calls the UI made, and any request that tried to leave.

The render is the real thing, not an imitation. The shipped ``/app/ui-frame``
document runs under its shipped headers, receives the stored component, its
assets and its pinned libraries exactly as the app hands them over, and loads
them from ``blob:`` URLs. Only the parent is a stand-in, playing the app's part:

* **No network.** Every request is intercepted. The stand-in parent page and the
  frame document are served from memory; anything else is refused and reported.
  There is nothing to reach -- no session, no cookie, no token exists in the
  browser at all.
* **Read-only bridge.** ``whoami`` answers with the command center's id and the
  reads answer empty, so a UI renders its empty state. Every call that would act
  (``sendMessage``, ``emit``, ``setConversationDesign``) is refused as a preview,
  and each call is reported so the agent sees what its UI tried.

It runs as a short-lived subprocess (``python -m tinyassets.ui_preview``) with a
hard wall clock, one render at a time per process: the box is memory-bound
(about 150 MB unique per render, measured 2026-10-02) and a second concurrent
render is refused as busy rather than queued. A host without Playwright's
Chromium refuses with ``ui_preview_unavailable`` -- never a blank image that
looks like a result.
"""

from __future__ import annotations

import base64
import contextlib
import json
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

#: One render at a time in this process; a second is refused, not queued.
_SLOT = threading.BoundedSemaphore(1)
DEFAULT_WIDTH, DEFAULT_HEIGHT = 1024, 768
MAX_WIDTH, MAX_HEIGHT = 1920, 1920
#: Wait after the bundle is handed over before sampling, and the sample window.
SETTLE_MS, SAMPLE_MS = 1500, 1000
WALL_SECONDS = 60.0
MAX_REPORTED_LINES = 50
_ORIGIN = "https://preview.tinyassets.invalid"


class PreviewUnavailable(RuntimeError):
    """This host cannot render (no Playwright Chromium), or the slot is busy."""


# The app's part, played from memory. The bridge answers as a read-only preview:
# the reads a UI starts with answer empty, every action is refused by name.
_PARENT = """<!doctype html><html><head><meta charset="utf-8">
<style>html,body{margin:0;height:100%}iframe{border:0;width:100%;height:100%;display:block}</style>
</head><body><script>
window.__preview={calls:[],delivered:false,error:""};
const SPEC=__SPEC__;
const frame=document.createElement('iframe');
frame.setAttribute('sandbox','allow-scripts');
frame.setAttribute('referrerpolicy','no-referrer');
frame.src='/app/ui-frame';
document.body.appendChild(frame);
const EMPTY={whoami:{protocol:1,command_center_id:SPEC.universe_id,command_center_name:'Preview'},
  list_agents:{agents:[]},read_conversation:{turns:[],has_more:false,next_before:null},
  list_automations:{automations:[]},list_runs:{runs:[],has_more:false},
  list_files:{path:'',entries:[],truncated:false},
  conversation_design:{state:'default',agent_definition_id:'',component_key:''}};
const bytes=async path=>(await (await fetch(path)).arrayBuffer());
window.addEventListener('message',async e=>{
  if(e.source!==frame.contentWindow) return;
  const m=e.data;
  if(!m||typeof m!=='object'||m.ta_ui!==1) return;
  if(m.type==='ready'&&!window.__preview.delivered){
    window.__preview.delivered=true;
    try{
      const libraries=[];
      for(const [name,format] of SPEC.libraries)
        libraries.push({name,format,bytes:await bytes('/__preview/lib/'+encodeURIComponent(name))});
      const files=[];
      for(const [path,type] of SPEC.files)
        files.push({path,media_type:type,
          bytes:await bytes('/__preview/asset/'+encodeURIComponent(path))});
      const bundle=Object.assign({},SPEC.bundle,{files,libraries});
      frame.contentWindow.postMessage({ta_ui:1,type:'bundle',bundle},'*');
    }catch(err){ window.__preview.error=String(err&&err.message||err); }
    return;
  }
  if(m.type==='call'&&typeof m.id==='string'){
    const action=String(m.action);
    window.__preview.calls.push(action);
    const known=Object.prototype.hasOwnProperty.call(EMPTY,action);
    frame.contentWindow.postMessage(known
      ?{ta_ui:1,type:'result',id:m.id,ok:true,result:EMPTY[action]}
      :{ta_ui:1,type:'result',id:m.id,ok:false,
        error:'preview: '+action+' does not run while previewing'},'*');
  }
});
</script></body></html>"""

# Counted inside the frame: animation frames the page actually produced.
_FPS_PROBE = """ms => new Promise(resolve => {
  let frames = 0; const start = performance.now();
  function tick(now) { frames++; if (now - start < ms) requestAnimationFrame(tick);
    else resolve(frames * 1000 / (now - start)); }
  requestAnimationFrame(tick);
})"""


def available() -> bool:
    """Whether this host has Playwright with an installed Chromium."""
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except ImportError:
        return False
    return True


def _spec_for(
    base_path: str | Path, owner_user_id: str, universe_id: str, ui_id: str,
    width: int, height: int,
) -> dict[str, Any]:
    from tinyassets.custom_agents import AgentNotFoundError, get_app_ui
    from tinyassets.onboarding import ui_library_set

    row = get_app_ui(base_path, owner_user_id=owner_user_id, universe_id=universe_id)
    entry = next((e for e in row["ui_library"]
                  if isinstance(e, dict) and e.get("ui_id") == ui_id), None)
    if entry is None:
        installed = [e.get("ui_id") for e in row["ui_library"] if isinstance(e, dict)]
        raise AgentNotFoundError(f"no UI with ui_id {ui_id!r}; installed: {installed}")
    names = ui_library_set.load_order(list(entry.get("libraries") or []))
    manifest = ui_library_set.manifest()
    assets = entry.get("assets") or {}
    return {
        "base_path": str(base_path), "owner_user_id": owner_user_id,
        "universe_id": universe_id, "ui_id": ui_id,
        "width": width, "height": height,
        "libraries": [[name, manifest[name]["format"]] for name in names],
        "files": [[path, ref["media_type"]] for path, ref in assets.items()],
        "hashes": {path: ref["sha256"] for path, ref in assets.items()},
        "bundle": {"markup": entry.get("markup", ""), "style": entry.get("style", ""),
                   "script": entry.get("script", ""),
                   **({"script_type": "module"} if entry.get("script_type") == "module" else {})},
    }


def preview_app_ui(
    base_path: str | Path, *, owner_user_id: str, universe_id: str, ui_id: str,
    width: int = DEFAULT_WIDTH, height: int = DEFAULT_HEIGHT,
    wall_seconds: float = WALL_SECONDS,
) -> dict[str, Any]:
    """Render the caller's own UI ``ui_id``; the report plus ``png`` bytes.

    Raises ``AgentNotFoundError`` for a UI the caller does not have and
    :class:`PreviewUnavailable` when this host cannot render or is rendering.
    """
    if not (isinstance(width, int) and isinstance(height, int)
            and 200 <= width <= MAX_WIDTH and 200 <= height <= MAX_HEIGHT):
        raise ValueError(f"width and height must be 200..{MAX_WIDTH} pixels")
    if not available():
        raise PreviewUnavailable(
            "ui_preview_unavailable: this host has no headless browser to render with")
    spec = _spec_for(base_path, owner_user_id, universe_id, ui_id, width, height)
    if not _SLOT.acquire(blocking=False):
        raise PreviewUnavailable("ui_preview_busy: another preview is rendering; try again")
    try:
        return _run_child(spec, wall_seconds)
    finally:
        _SLOT.release()


def _run_child(spec: dict[str, Any], wall_seconds: float) -> dict[str, Any]:
    try:
        done = subprocess.run(
            [sys.executable, "-m", "tinyassets.ui_preview"],
            input=json.dumps(spec).encode("utf-8"), capture_output=True,
            timeout=wall_seconds, cwd=str(Path(__file__).resolve().parents[1]),
        )
    except subprocess.TimeoutExpired:
        raise PreviewUnavailable(
            f"ui_preview_timeout: the render did not finish in {wall_seconds:.0f} s") from None
    lines = [line for line in done.stdout.decode("utf-8", "replace").splitlines()
             if line.startswith("{")]
    if done.returncode != 0 or not lines:
        tail = done.stderr.decode("utf-8", "replace").strip().splitlines()[-1:] or ["no output"]
        raise PreviewUnavailable(f"ui_preview_failed: {tail[0][:300]}")
    report = json.loads(lines[-1])
    if report.get("unavailable"):
        raise PreviewUnavailable(f"ui_preview_unavailable: {report['unavailable']}")
    report["png"] = base64.b64decode(report.pop("png_base64"))
    return report


def _child(spec: dict[str, Any]) -> dict[str, Any]:
    from urllib.parse import unquote, urlsplit

    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright

    from tinyassets.custom_agents import read_app_ui_asset
    from tinyassets.onboarding import ui_library_set
    from tinyassets.onboarding.ui_frame import BOOTSTRAP_HTML, FRAME_HEADERS

    served: dict[str, bytes] = {}
    for name, _ in spec["libraries"]:
        served["/__preview/lib/" + name] = ui_library_set.library_bytes(name)
    missing = []
    for path, sha in spec["hashes"].items():
        found = read_app_ui_asset(spec["base_path"], owner_user_id=spec["owner_user_id"],
                                  sha256=sha)
        if found is None:
            missing.append(path)
        else:
            served["/__preview/asset/" + path] = found
    blocked: list[str] = []
    console: list[str] = []
    errors: list[str] = []
    parent = _PARENT.replace("__SPEC__", json.dumps({
        k: spec[k] for k in ("universe_id", "libraries", "files", "bundle")}))

    def route(r):
        url = urlsplit(r.request.url)
        path = unquote(url.path)
        if f"{url.scheme}://{url.netloc}" == _ORIGIN:
            if path == "/":
                return r.fulfill(status=200, content_type="text/html", body=parent)
            if path == "/app/ui-frame":
                return r.fulfill(status=200, content_type="text/html", body=BOOTSTRAP_HTML,
                                 headers=dict(FRAME_HEADERS))
            if path in served:
                return r.fulfill(status=200, content_type="application/octet-stream",
                                 body=served[path])
        if len(blocked) < MAX_REPORTED_LINES:
            blocked.append(r.request.url[:300])
        return r.abort()

    with sync_playwright() as p:
        try:
            # The UI is somebody's arbitrary code: Chromium's own sandbox stays
            # ON (Playwright turns it off by default), so a renderer exploit is
            # confined the way any browser tab is, not handed the daemon's user.
            browser = p.chromium.launch(
                chromium_sandbox=True,
                args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader",
                      "--disable-dev-shm-usage", "--no-first-run"])
        except PlaywrightError as exc:
            return {"unavailable": str(exc).splitlines()[0][:300]}
        try:
            # No service_workers="block": its injected shim throws inside a
            # sandboxed frame and would be reported as the UI's own error.
            context = browser.new_context(
                viewport={"width": spec["width"], "height": spec["height"]})
            page = context.new_page()
            page.on("console", lambda m: (m.type in ("error", "warning")
                                          and len(console) < MAX_REPORTED_LINES
                                          and console.append(f"{m.type}: {m.text[:500]}")))
            page.on("pageerror", lambda e: len(errors) < MAX_REPORTED_LINES
                    and errors.append(str(e)[:500]))
            context.route("**/*", route)
            started = time.monotonic()
            page.goto(_ORIGIN + "/")
            page.wait_for_function("window.__preview.delivered", timeout=15_000)
            page.wait_for_timeout(SETTLE_MS)
            frame = next((f for f in page.frames if f.url.endswith("/app/ui-frame")), None)
            fps = None
            if frame is not None:
                try:
                    fps = round(frame.evaluate(_FPS_PROBE, SAMPLE_MS), 1)
                except PlaywrightError as exc:
                    errors.append(f"frame rate could not be measured: {str(exc)[:200]}")
            png = page.screenshot(type="png")
            state = page.evaluate("window.__preview")
            loaded_ms = int((time.monotonic() - started) * 1000)
        finally:
            browser.close()
    calls: dict[str, int] = {}
    for action in state.get("calls") or []:
        calls[action] = calls.get(action, 0) + 1
    return {
        "ui_id": spec["ui_id"], "width": spec["width"], "height": spec["height"],
        "fps": fps, "rendered_ms": loaded_ms,
        "uncaught_errors": errors, "console": console,
        "bridge_calls": calls, "blocked_requests": blocked,
        "missing_assets": missing, "delivery_error": state.get("error") or "",
        "png_base64": base64.b64encode(png).decode("ascii"),
    }


def main() -> int:
    spec = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    sys.stdout.write(json.dumps(_child(spec)) + "\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


PREVIEW_DIR = "previews"


def write_preview(universe_dir: str | Path, ui_id: str, png: bytes) -> str:
    """Put ``png`` at ``/u/previews/<ui_id>.png``; the path as the agent sees it.

    The folder is the agent's own and the agent can change it, so the write
    trusts nothing in it: ``previews`` must be a real directory (not a link or
    junction), the bytes go to a fresh exclusive temp file, and ``os.replace``
    swaps it in -- which breaks a hard link the agent may have planted at the
    target instead of writing through it.
    """
    import os
    import re
    import stat

    # The server stores any non-empty ui_id; only the app's own id shape names
    # a file, so nothing like "../x" ever becomes a path.
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", str(ui_id)):
        raise PreviewUnavailable(
            f"ui_preview_failed: ui_id {ui_id!r} is not lowercase letters, digits and dashes")
    root = Path(universe_dir)
    folder = root / PREVIEW_DIR
    try:
        info = os.lstat(folder)
    except FileNotFoundError:
        folder.mkdir()
        info = os.lstat(folder)
    if not stat.S_ISDIR(info.st_mode) or getattr(info, "st_reparse_tag", 0):
        raise PreviewUnavailable(f"ui_preview_failed: /u/{PREVIEW_DIR} is not a plain folder")
    name = f"{ui_id}.png"
    temp = folder / f".{name}.{os.getpid()}.{threading.get_ident()}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) \
        | getattr(os, "O_BINARY", 0)
    fd = os.open(temp, flags, 0o644)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(png)
        os.replace(temp, folder / name)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temp)
        raise
    return f"/u/{PREVIEW_DIR}/{name}"
