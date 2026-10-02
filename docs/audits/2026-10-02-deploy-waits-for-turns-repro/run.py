"""A merge lands mid-turn: does the deploy wait, and does the turn finish?

    REPRO_IMAGE=<image with fastmcp+uvicorn+repo deps> python run.py wait [TURN_S]
    REPRO_IMAGE=... python run.py cap [TURN_S]

Starts the daemon (GEN=1), opens an MCP session and calls `converse`, a turn
that holds a real interactive seat for TURN_S seconds (default 600). Five
seconds in, a "merge" arrives: this runs the REAL `Wait for in-flight turns`
step, extracted verbatim from .github/workflows/deploy-prod.yml, with `ssh` and
`scp` replaced by local stand-ins that run the same command against the local
container. When the step returns, it converges GEN=2 the way deploy_fail_safe.sh
does (`up -d --timeout 20`).

wait  cap 2700s, as production. Expect: outcome=idle, the turn's reply arrives
      from GEN=1, the swap starts only after it, and GEN=2 serves.
cap   cap 20s, standing in for 45 min with a turn that will not end. Expect:
      outcome=cap_reached, the swap proceeds, and the turn is cut off.

Prints one line of results per variant.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import httpx
import yaml

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
URL = "http://127.0.0.1:18001/mcp"
HEADERS = {"Accept": "application/json, text/event-stream"}

FAKE_SSH = r"""#!/usr/bin/env bash
# The droplet is this machine: run the command the step would send, with sudo
# stripped (Docker Desktop needs none).
cmd="${@: -1}"
exec bash -c "sudo() { \"\$@\"; }; ${cmd}"
"""
FAKE_SCP = r"""#!/usr/bin/env bash
# Copy the one file the step ships to the path the step then reads.
args=("$@"); src="${args[-2]}"; dst="${args[-1]#*:}"
cp "$src" "$dst"
"""


def compose(*args: str, env: dict[str, str], check: bool = True) -> float:
    started = time.monotonic()
    subprocess.run(["docker", "compose", "-f", str(HERE / "compose.yml"), *args],
                   check=check, env={**os.environ, **env})
    return time.monotonic() - started


def up(timeout: float = 90) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            httpx.get(URL, timeout=1)
            return
        except httpx.HTTPError:
            time.sleep(0.25)
    raise SystemExit("server never came up")


def session() -> httpx.Client:
    client = httpx.Client(headers=HEADERS, timeout=None)
    init = client.post(URL, json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2025-03-26", "capabilities": {},
        "clientInfo": {"name": "repro", "version": "1"}}})
    client.headers["mcp-session-id"] = init.headers["mcp-session-id"]
    client.post(URL, json={"jsonrpc": "2.0", "method": "notifications/initialized"})
    return client


def call(client: httpx.Client, name: str) -> str:
    response = client.post(URL, json={"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                                      "params": {"name": name, "arguments": {}}})
    return response.text


def wait_step_script() -> str:
    wf = yaml.safe_load((REPO / ".github" / "workflows" / "deploy-prod.yml").read_text(
        encoding="utf-8"))
    step = next(s for s in wf["jobs"]["deploy"]["steps"]
                if s.get("name") == "Wait for in-flight turns")
    return step["run"]


def run_wait_step(cap_s: int, work: Path) -> dict[str, str]:
    bin_dir = work / "bin"
    bin_dir.mkdir()
    for name, body in (("ssh", FAKE_SSH), ("scp", FAKE_SCP)):
        (bin_dir / name).write_text(body, encoding="utf-8", newline="\n")
    script = work / "wait.sh"
    script.write_text(wait_step_script(), encoding="utf-8", newline="\n")
    out = work / "gh_output"
    out.write_text("", encoding="utf-8")
    env = {**os.environ, "GITHUB_OUTPUT": out.as_posix(), "DO_SSH_USER": "local",
           "DO_DROPLET_HOST": "localhost", "TARGET_REVISION": "f" * 40,
           "TURN_WAIT_CAP_S": str(cap_s), "TURN_POLL_S": "5",
           "RUN_URL": "https://example.invalid/repro"}
    bash = shutil.which("bash") or "bash"
    if os.name == "nt":
        inner = (f'export PATH="$(cygpath -u "{bin_dir}"):$PATH"; '
                 f'bash "$(cygpath -u "{script}")"')
    else:
        inner = f'export PATH="{bin_dir}:$PATH"; bash "{script}"'
    subprocess.run([bash, "-c", inner], env=env, check=True, cwd=REPO)  # the checkout root
    return dict(line.split("=", 1)
                for line in out.read_text(encoding="utf-8").splitlines() if "=" in line)


def main(variant: str, turn_s: float) -> None:
    cap_s = {"wait": 2700, "cap": 20}[variant]
    env1 = {"GEN": "1", "TURN_S": str(turn_s)}
    compose("down", "-v", "--timeout", "0", env=env1, check=False)
    compose("run", "--rm", "--no-deps", "--user", "0:0", "--entrypoint", "chown", "daemon",
            "1001:1001", "/data", env=env1)
    compose("up", "-d", env=env1)
    up()

    reply: dict[str, object] = {}
    client = session()

    def turn() -> None:
        try:
            reply["text"] = call(client, "converse")
        except httpx.HTTPError as exc:
            reply["text"] = f"CUT OFF: {type(exc).__name__}"
        reply["at"] = time.monotonic()

    started = time.monotonic()
    worker = threading.Thread(target=turn, daemon=True)
    worker.start()
    time.sleep(5)  # the merge lands mid-turn

    marker: dict[str, object] = {}

    def watch_marker() -> None:
        time.sleep(12)
        got = subprocess.run(["docker", "exec", "tinyassets-daemon", "cat",
                              "/data/.deploy-pending.json"], capture_output=True, text=True)
        marker["seen"] = got.stdout.strip() or got.stderr.strip()

    threading.Thread(target=watch_marker, daemon=True).start()
    with tempfile.TemporaryDirectory() as tmp:
        outcome = run_wait_step(cap_s, Path(tmp))
    swap_at = time.monotonic()

    dead: list[float] = []
    stop = threading.Event()

    def probe() -> None:
        while not stop.is_set():
            try:
                httpx.get(URL, timeout=1)
            except httpx.HTTPError:
                dead.append(time.monotonic())
            time.sleep(0.25)

    prober = threading.Thread(target=probe, daemon=True)
    prober.start()
    compose("up", "-d", "--timeout", "20", env={"GEN": "2", "TURN_S": str(turn_s)})
    up()
    stop.set()
    prober.join()
    worker.join(timeout=60)
    new_gen = call(session(), "gen")

    finished = reply.get("at")
    text = str(reply.get("text", "<no reply>"))
    print(json.dumps({
        "variant": variant,
        "turn_s": turn_s,
        "wait_outcome": outcome.get("outcome"),
        "waited_s": outcome.get("waited_s"),
        "polls": outcome.get("polls"),
        "turn_reply": "TURN_FINISHED gen=1" if "TURN_FINISHED gen=1" in text else text[:120],
        "turn_finished_before_swap": finished is not None and finished <= swap_at,
        "turn_s_observed": round(finished - started, 1) if finished else None,
        "port_dead_window_s": round(dead[-1] - dead[0], 1) if dead else 0.0,
        "new_gen_serving": "2" if '"2"' in new_gen or "text\":\"2" in new_gen else new_gen[:120],
        "marker_during_wait": marker.get("seen", "<not read>")[:300],
    }))
    compose("down", "-v", "--timeout", "0", env={"GEN": "0", "TURN_S": "1"}, check=False)


if __name__ == "__main__":
    main(sys.argv[1], float(sys.argv[2]) if len(sys.argv) > 2 else 600.0)
