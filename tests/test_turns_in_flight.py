"""A deploy never swaps the daemon while it is running someone's work.

``scripts/turns_in_flight.py`` is the question; the ``Wait for in-flight turns``
step of ``deploy-prod.yml`` is the loop that asks it before the swap. Both are
exercised for real here: seats taken through ``universe_seats`` itself, the
script run the way production runs it (piped to ``python -`` with no
``tinyassets`` importable), and the workflow's own bash loop run against a
stand-in ``ssh``.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest

from scripts import turns_in_flight as tif
from tinyassets import universe_seats as seats
from tinyassets.storage import DB_FILENAME
from tinyassets.storage.agent_turn_journal import WORKING_STATES, ensure_schema

try:
    import yaml
except ImportError:  # pragma: no cover - CI installs it
    yaml = None

_REPO = Path(__file__).resolve().parent.parent
_SCRIPT = _REPO / "scripts" / "turns_in_flight.py"
_WORKFLOW = _REPO / ".github" / "workflows" / "deploy-prod.yml"


# --- the names the script cannot import --------------------------------------


def test_duplicated_names_match_the_daemon():
    assert tif.SEATS_DB == seats.LEDGER_NAME
    assert tif.JOURNAL_DB == DB_FILENAME
    assert set(tif.WORKING_STATES) == set(WORKING_STATES)


def test_script_imports_nothing_from_the_repo():
    """It runs inside whatever image is live, which may predate any helper."""
    source = _SCRIPT.read_text(encoding="utf-8")
    assert "import tinyassets" not in source
    assert "from tinyassets" not in source
    assert "from scripts" not in source


# --- the question ------------------------------------------------------------


def test_missing_data_dir_is_idle_and_creates_nothing(tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    status, report = tif.observe(root)
    assert status == tif.IDLE
    assert report["in_flight"] == 0
    assert list(root.iterdir()) == []


def test_a_held_seat_is_busy_and_its_release_is_idle(tmp_path):
    db = tmp_path / tif.SEATS_DB
    seat = seats.acquire(
        "acct", seat_class=seats.CLASS_INTERACTIVE, kind=seats.KIND_CHAT_TURN,
        universe_id="u-village", db=db,
    )
    assert isinstance(seat, seats.Seat)
    status, report = tif.observe(tmp_path)
    assert status == tif.BUSY
    assert report["in_flight"] == 1
    assert report["seats"][0]["kind"] == seats.KIND_CHAT_TURN
    assert report["seats"][0]["universe_id"] == "u-village"

    assert seats.release(seat.seat_id, db=db)
    status, report = tif.observe(tmp_path)
    assert status == tif.IDLE
    assert report["in_flight"] == 0


def test_an_expired_seat_is_a_dead_holder_not_work(tmp_path):
    db = tmp_path / tif.SEATS_DB
    seat = seats.acquire("acct", db=db, now=time.time() - 600, lease_s=120)
    assert isinstance(seat, seats.Seat)
    status, report = tif.observe(tmp_path)
    assert status == tif.IDLE, report


def test_a_working_journal_row_is_reported_but_does_not_hold_the_deploy(tmp_path):
    """A cancelled task leaves ``native_started`` behind until the next boot.
    Gating on it would hold every deploy to the cap behind a phantom."""
    conn = sqlite3.connect(tmp_path / DB_FILENAME, isolation_level=None)
    ensure_schema(conn)
    conn.execute(
        "INSERT INTO agent_turns VALUES (?,?,?,?,?,?,?,?,?)",
        ("owner", "u-village", "652a2f31e82546a1", 1, 1, "native_started", 1, "{}",
         "2026-10-02T01:00:00Z"),
    )
    conn.close()
    status, report = tif.observe(tmp_path)
    assert status == tif.IDLE
    assert report["journal_working"] == [{
        "universe_id": "u-village", "turn": "652a2f31", "state": "native_started",
        "age_s": report["journal_working"][0]["age_s"],
    }]


def test_an_unreadable_ledger_is_unknown_never_idle(tmp_path):
    (tmp_path / tif.SEATS_DB).write_bytes(b"this is not a sqlite database at all" * 40)
    status, report = tif.observe(tmp_path)
    assert status == tif.UNKNOWN
    assert report["in_flight"] is None
    assert "unreadable" in report["error"]


def test_runs_piped_to_python_with_no_repo_on_the_path(tmp_path):
    """Exactly how the workflow runs it: ``docker exec -i ... python - ARGS < file``."""
    db = tmp_path / tif.SEATS_DB
    seat = seats.acquire("acct", db=db)
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    result = subprocess.run(
        [sys.executable, "-I", "-", "--data-dir", str(tmp_path)],
        input=_SCRIPT.read_bytes(), capture_output=True, cwd=str(tmp_path), env=env,
        timeout=60,
    )
    assert result.returncode == tif.BUSY, result.stderr
    assert json.loads(result.stdout)["in_flight"] == 1
    seats.release(seat.seat_id, db=db)
    result = subprocess.run(
        [sys.executable, "-I", "-", "--data-dir", str(tmp_path)],
        input=_SCRIPT.read_bytes(), capture_output=True, cwd=str(tmp_path), env=env,
        timeout=60,
    )
    assert result.returncode == tif.IDLE, result.stderr


# --- the marker and the status field ----------------------------------------


def test_marker_is_visible_in_status_until_it_expires_or_is_cleared(tmp_path, monkeypatch):
    from tinyassets.api import status as status_mod

    monkeypatch.setattr(status_mod, "_base_path", lambda: tmp_path)
    assert status_mod._load_deploy_pending() == {"pending": False}

    seats.acquire("acct", db=tmp_path / tif.SEATS_DB)
    rc = tif.main([
        "--data-dir", str(tmp_path), "--mark-pending", "--target", "abc123",
        "--waiting-since", str(time.time() - 30), "--ttl", "60",
        "--run-url", "https://example.invalid/run",
    ])
    assert rc == tif.BUSY
    seen = status_mod._load_deploy_pending()
    assert seen["pending"] is True
    assert seen["target"] == "abc123"
    assert seen["in_flight"] == 1
    assert seen["run_url"] == "https://example.invalid/run"

    # A deploy job that died mid-wait stops meaning anything once the ttl lapses.
    later = time.time() + 120
    assert status_mod._load_deploy_pending(now=later) == {
        "pending": False, "warning": "deploy_pending_marker_expired",
    }

    assert tif.main(["--data-dir", str(tmp_path), "--clear-pending"]) == tif.IDLE
    assert not (tmp_path / tif.MARKER).exists()
    assert status_mod._load_deploy_pending() == {"pending": False}


def test_a_garbled_marker_never_reads_as_pending(tmp_path, monkeypatch):
    from tinyassets.api import status as status_mod

    monkeypatch.setattr(status_mod, "_base_path", lambda: tmp_path)
    (tmp_path / tif.MARKER).write_text("{not json", encoding="utf-8")
    assert status_mod._load_deploy_pending()["pending"] is False
    (tmp_path / tif.MARKER).write_text('["pending"]', encoding="utf-8")
    assert status_mod._load_deploy_pending()["pending"] is False
    (tmp_path / tif.MARKER).write_text('{"pending": true}', encoding="utf-8")
    assert status_mod._load_deploy_pending()["pending"] is False  # no expires_at


# --- the workflow step -------------------------------------------------------


def _steps() -> list[dict]:
    wf = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
    return wf["jobs"]["deploy"]["steps"]


def _step(name: str) -> dict:
    return next(step for step in _steps() if step.get("name") == name)


@pytest.mark.skipif(yaml is None, reason="pyyaml not installed")
def test_wait_runs_before_the_swap_and_outside_its_lock():
    names = [step.get("name") for step in _steps()]
    wait = names.index("Wait for in-flight turns")
    assert wait == names.index("Run fail-safe deploy on the droplet") - 1
    run = _step("Wait for in-flight turns")["run"]
    assert "turns_in_flight.py" in run
    # The wait must not run under the host-mutation lock: watchdogs need it.
    assert "flock" not in run and "deploy_fail_safe.sh" not in run


@pytest.mark.skipif(yaml is None, reason="pyyaml not installed")
def test_job_and_step_budgets_cover_the_cap():
    step = _step("Wait for in-flight turns")
    cap_s = int(step["env"]["TURN_WAIT_CAP_S"])
    assert cap_s == 2700
    assert step["timeout-minutes"] * 60 > cap_s
    job = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))["jobs"]["deploy"]
    # The job must outlive the wait plus the deploy work behind it.
    assert job["timeout-minutes"] >= step["timeout-minutes"] + 15


_FAKE_SSH = r"""#!/usr/bin/env bash
# Stand-in for the droplet: answers each in-flight check from a script of
# exit codes, one per call, and records every command it was asked to run.
cmd="${@: -1}"
printf '%s\n' "$cmd" >> "$FAKE_DIR/calls"
case "$cmd" in
  *--clear-pending*) echo '{"cleared": true}'; exit 0 ;;
esac
n=$(cat "$FAKE_DIR/n" 2>/dev/null || echo 0)
n=$((n + 1)); echo "$n" > "$FAKE_DIR/n"
rc=$(sed -n "${n}p" "$FAKE_DIR/script")
[ -n "$rc" ] || rc=$(tail -n 1 "$FAKE_DIR/script")
echo "{\"poll\": $n, \"rc\": $rc}"
exit "$rc"
"""


def _run_wait(tmp_path: Path, codes: list[int], *, cap_s: int = 2700) -> dict[str, str]:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash not available")
    fake = tmp_path / "fake"
    bin_dir = fake / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "ssh").write_text(_FAKE_SSH, encoding="utf-8", newline="\n")
    for name, body in (("scp", "exit 0"), ("sleep", "exit 0")):
        (bin_dir / name).write_text(f"#!/usr/bin/env bash\n{body}\n", encoding="utf-8",
                                    newline="\n")
    for tool in bin_dir.iterdir():
        tool.chmod(0o755)
    (fake / "script").write_text("\n".join(str(c) for c in codes) + "\n", encoding="utf-8",
                                 newline="\n")
    out = tmp_path / "gh_output"
    out.write_text("", encoding="utf-8")
    script = tmp_path / "wait.sh"
    script.write_text(_step("Wait for in-flight turns")["run"], encoding="utf-8",
                      newline="\n")
    env = dict(os.environ)
    env.update({
        "PATH": f"{bin_dir.as_posix()}{os.pathsep}{env.get('PATH', '')}",
        "FAKE_DIR": fake.as_posix(),
        "GITHUB_OUTPUT": out.as_posix(),
        "DO_SSH_USER": "deploy", "DO_DROPLET_HOST": "droplet.invalid",
        "TARGET_REVISION": "a" * 40, "TURN_WAIT_CAP_S": str(cap_s), "TURN_POLL_S": "15",
        "RUN_URL": "https://example.invalid/run",
    })
    if os.name == "nt":
        # Git Bash resolves PATH entries in POSIX form; prepend inside bash.
        wrapper = (f'export PATH="$(cygpath -u "{bin_dir}"):$PATH"; '
                   f'bash "$(cygpath -u "{script}")"')
        cmd = [bash, "-c", wrapper]
    else:
        cmd = [bash, str(script)]
    result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    outputs = dict(
        line.split("=", 1) for line in out.read_text(encoding="utf-8").splitlines() if "=" in line
    )
    outputs["_calls"] = (fake / "calls").read_text(encoding="utf-8")
    outputs["_stdout"] = result.stdout
    return outputs


@pytest.mark.skipif(yaml is None, reason="pyyaml not installed")
def test_wait_holds_while_busy_then_deploys_when_idle(tmp_path):
    out = _run_wait(tmp_path, [10, 10, 10, 0])
    assert out["outcome"] == "idle"
    assert out["polls"] == "4"
    calls = out["_calls"]
    assert calls.count("--mark-pending") == 4
    assert "--clear-pending" in calls.splitlines()[-1]


@pytest.mark.skipif(yaml is None, reason="pyyaml not installed")
def test_wait_proceeds_at_the_cap(tmp_path):
    out = _run_wait(tmp_path, [10], cap_s=0)
    assert out["outcome"] == "cap_reached"
    assert out["polls"] == "1"


@pytest.mark.skipif(yaml is None, reason="pyyaml not installed")
def test_a_daemon_that_is_not_serving_is_deployed_at_once(tmp_path):
    out = _run_wait(tmp_path, [20])
    assert out["outcome"] == "daemon_not_serving"
    assert out["polls"] == "1"


@pytest.mark.skipif(yaml is None, reason="pyyaml not installed")
def test_unknown_is_retried_then_proceeds_loudly(tmp_path):
    out = _run_wait(tmp_path, [2, 2, 2])
    assert out["outcome"] == "check_unavailable"
    assert out["polls"] == "3"
    assert "could not answer" in out["_stdout"]


@pytest.mark.skipif(yaml is None, reason="pyyaml not installed")
def test_one_unknown_between_busy_answers_does_not_end_the_wait(tmp_path):
    out = _run_wait(tmp_path, [10, 2, 10, 2, 10, 2, 0])
    assert out["outcome"] == "idle"
    assert out["polls"] == "7"
