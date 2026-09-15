"""Measure system Chromium inside the unchanged workspace jail and limits.

Diagnostic, not a fake browser or a production deployment. No external URL,
tenant state, credentials, host port or host IPC is used. Nonzero exit is an
actual compatibility failure, not permission to disable isolation or raise caps.
"""

import argparse
import json
import os
import struct
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tinyassets.node_sandbox import (  # noqa: E402
    BwrapLauncher,
    NodeSandbox,
    WorkspaceLimits,
    WorkspaceMount,
)


def diagnostic_limits(control: bool, memory_max: str) -> WorkspaceLimits:
    """A comparison cannot remove AS without a verified container RAM bound."""
    if not control:
        return WorkspaceLimits()
    try:
        physical_bound = int(memory_max.strip())
    except ValueError:
        raise ValueError("comparison requires a finite cgroup v2 memory.max") from None
    if not 0 < physical_bound <= WorkspaceLimits().rss_cap_bytes:
        raise ValueError("comparison requires a container memory cap of at most 2 GiB")
    return WorkspaceLimits(rlimit_as=-1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native", action="store_true",
                        help="diagnose the native binary separately from Debian's /etc wrapper")
    parser.add_argument("--address-space-control", action="store_true",
                        help="diagnostic only: compare without RLIMIT_AS; retain RSS/CPU/deadline")
    options = parser.parse_args()
    if sys.platform != "linux" or os.getuid() == 0:
        raise SystemExit("This diagnostic requires Linux and a non-root user")
    binary = "/usr/lib/chromium/chromium" if options.native else "/usr/bin/chromium"
    memory_max = Path("/sys/fs/cgroup/memory.max").read_text().strip()
    limits = diagnostic_limits(options.address_space_control, memory_max)
    with tempfile.TemporaryDirectory(prefix="ta-browser-compat-", dir="/tmp") as temporary:
        root = Path(temporary)
        (root / "preview.html").write_text(
            "<!doctype html><html><meta charset='utf-8'><title>Workspace proof</title>"
            "<style>body{background:#eff6ff;color:#172554;font:24px sans-serif}"
            "main{padding:32px}p{color:#166534}</style><main><h1>Workspace browser</h1>"
            "<p>Rendered inside the offline jail.</p></main></html>", encoding="utf-8")
        handle = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            mount = WorkspaceMount(f"/proc/self/fd/{handle}", pass_fds=(handle,), limits=limits)
            source = '''
def run(state):
    version = ws.run([state['binary'], '--version'])
    capture = ws.run([state['binary'], '--headless', '--disable-gpu',
        '--no-first-run', '--no-default-browser-check',
        '--user-data-dir=/workspace/profile', '--window-size=960,640',
        '--screenshot=/workspace/capture.png', 'file:///workspace/preview.html'])
    return {'result': {'version': version, 'capture': capture}}
'''
            result = NodeSandbox(launcher=BwrapLauncher(), timeout=30).run_sync(
                node_id="browser-compatibility", source_code=source, input_state={"binary": binary},
                input_keys=["binary"], output_keys=["result"], timeout=30, workspace=mount)
            report = dict(binary=binary, limits=limits.rlimit_profile(),
                          address_space_control=options.address_space_control,
                          container_memory_max=memory_max,
                          container_memory_peak=Path("/sys/fs/cgroup/memory.peak").read_text().strip(),
                          rss_cap_bytes=limits.rss_cap_bytes,
                          success=result.success,
                          error=result.error, output=result.output_state)
            png = root / "capture.png"
            captured = False
            if png.is_file():
                header = png.read_bytes()[:24]
                if header[:8] == b"\x89PNG\r\n\x1a\n":
                    report["png_dimensions"] = struct.unpack(">II", header[16:24])
                    captured = report["png_dimensions"] == (960, 640)
            report["captured"] = captured
            print(json.dumps(report))
            return 0 if result.success and captured else 1
        finally:
            os.close(handle)


if __name__ == "__main__":
    raise SystemExit(main())
