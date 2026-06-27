"""Tests for scripts/triage_classify.py — P0 outage auto-triage classifier.

One test per class anchor + priority-ordering + fall-through. Every
regex gets exercised against realistic diag fragments drawn from
journalctl/systemctl/docker-compose output shapes we actually see on
the droplet.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import triage_classify as tc  # noqa: E402

# ---- ENV-UNREADABLE (Task #3 marker, priority 1) -------------------------


def test_classify_env_unreadable_marker():
    diag = (
        "Apr 22 03:00:01 droplet systemd[1]: tinyassets-daemon.service: "
        "Failed to execute ExecStartPre\n"
        "Apr 22 03:00:01 droplet sh[12345]: ENV-UNREADABLE: "
        "/etc/tinyassets/env not readable by user tinyassets (uid 1001)\n"
    )
    result = tc.classify(diag)
    assert result["class"] == tc.TriageClass.ENV_UNREADABLE
    assert result["auto_repairable"] is True
    assert result["manual_only"] is False
    assert "ENV-UNREADABLE" in result["evidence"]


def test_env_unreadable_wins_over_compose_cascade():
    """If the env perms regressed AND compose then failed downstream with
    a generic error, the classifier must still report env as root cause —
    repair order matters, fix the perms before the restart."""
    diag = (
        "ENV-UNREADABLE: /etc/tinyassets/env not readable\n"
        "docker compose up failed: exit code 1\n"
        "Error response from daemon: manifest for ghcr.io/... not found\n"
    )
    result = tc.classify(diag)
    assert result["class"] == tc.TriageClass.ENV_UNREADABLE, (
        "ENV-UNREADABLE is priority 1; must beat the cascading image-pull "
        "error that follows as a symptom"
    )


def test_execstartpre_marker_text_does_not_mask_disk_full():
    diag = (
        "Process: 760709 ExecStartPre=/bin/sh -c test -r /etc/tinyassets/env "
        "|| { echo \"ENV-UNREADABLE: /etc/tinyassets/env not readable\" >&2; "
        "ls -l /etc/tinyassets/env >&2 || true; exit 1; } "
        "(code=exited, status=0/SUCCESS)\n"
        "--- df -h ---\n"
        "Filesystem      Size  Used Avail Use% Mounted on\n"
        "/dev/vda1        50G   48G     0 100% /\n"
    )
    result = tc.classify(diag)
    assert result["class"] == tc.TriageClass.DISK_FULL


# ---- OOM -----------------------------------------------------------------


def test_classify_oom_kernel_killer():
    diag = (
        "Apr 22 03:15:22 droplet kernel: Out of memory: Killed process "
        "12345 (python) total-vm:2097152kB\n"
        "Apr 22 03:15:22 droplet kernel: oom-killer: gfp_mask=0x100dca\n"
    )
    result = tc.classify(diag)
    assert result["class"] == tc.TriageClass.OOM
    assert result["auto_repairable"] is True


def test_classify_oom_container_oomkilled():
    diag = (
        "tinyassets-daemon     Exited (137) 2 seconds ago\n"
        '"State": {"OOMKilled": true, "Dead": false}\n'
    )
    result = tc.classify(diag)
    assert result["class"] == tc.TriageClass.OOM


def test_classify_oom_cgroup_variant():
    diag = "Memory cgroup out of memory: Killed process 9876 (python)\n"
    result = tc.classify(diag)
    assert result["class"] == tc.TriageClass.OOM


# ---- disk full -----------------------------------------------------------


def test_classify_disk_full_root():
    # Classic `df -h` output line.
    diag = (
        "Filesystem      Size  Used Avail Use% Mounted on\n"
        "/dev/vda1        25G   24G  1.0G  96% /\n"
        "tmpfs           395M     0  395M   0% /dev/shm\n"
    )
    result = tc.classify(diag)
    assert result["class"] == tc.TriageClass.DISK_FULL
    assert result["auto_repairable"] is True


def test_classify_disk_full_var_lib_docker():
    diag = (
        "Filesystem      Size  Used Avail Use% Mounted on\n"
        "/dev/vdb1       100G   95G  5.0G  95% /var/lib/docker\n"
    )
    result = tc.classify(diag)
    assert result["class"] == tc.TriageClass.DISK_FULL


def test_classify_disk_full_exactly_90_percent():
    diag = "/dev/vda1        25G   23G  2.5G  90% /\n"
    result = tc.classify(diag)
    assert result["class"] == tc.TriageClass.DISK_FULL


def test_disk_not_full_below_threshold():
    """80% is below our 90% threshold — should NOT trip disk_full."""
    diag = (
        "Filesystem      Size  Used Avail Use% Mounted on\n"
        "/dev/vda1        25G   20G  5.0G  80% /\n"
    )
    result = tc.classify(diag)
    assert result["class"] != tc.TriageClass.DISK_FULL


def test_disk_not_full_wrong_mountpoint():
    """90% on /tmp or other unmanaged mount shouldn't trip — we only
    care about / and /var/lib/docker and /data."""
    diag = (
        "Filesystem      Size  Used Avail Use% Mounted on\n"
        "tmpfs            25G   23G  2.5G  90% /tmp\n"
        "/dev/vda1        25G   10G   15G  40% /\n"
    )
    result = tc.classify(diag)
    assert result["class"] != tc.TriageClass.DISK_FULL


# ---- image pull failure --------------------------------------------------


def test_classify_image_pull_manifest_not_found():
    diag = (
        "Error response from daemon: manifest for "
        "ghcr.io/jonnyton/tinyassets-daemon:abc123def456 not found\n"
        "docker compose up: exit code 1\n"
    )
    result = tc.classify(diag)
    assert result["class"] == tc.TriageClass.IMAGE_PULL_FAILURE
    assert result["auto_repairable"] is True


def test_classify_image_pull_manifest_unknown():
    diag = "Error response from daemon: manifest unknown\n"
    result = tc.classify(diag)
    assert result["class"] == tc.TriageClass.IMAGE_PULL_FAILURE


def test_classify_image_pull_access_denied():
    diag = "docker: pull access denied for ghcr.io/jonnyton/tinyassets-daemon\n"
    result = tc.classify(diag)
    assert result["class"] == tc.TriageClass.IMAGE_PULL_FAILURE


def test_classify_image_pull_head_request():
    diag = 'Error response from daemon: Head "https://ghcr.io/..." EOF\n'
    result = tc.classify(diag)
    assert result["class"] == tc.TriageClass.IMAGE_PULL_FAILURE


# ---- tunnel token --------------------------------------------------------


def test_classify_tunnel_token_unauthorized():
    diag = (
        "workflow-tunnel    | 2026-04-22T03:15:00Z ERR Failed to get tunnel "
        "error=\"Unauthorized: Invalid tunnel secret\"\n"
    )
    result = tc.classify(diag)
    assert result["class"] == tc.TriageClass.TUNNEL_TOKEN
    assert result["auto_repairable"] is False
    assert result["manual_only"] is True, (
        "tunnel token rotation is manual-only — detection must flag it so "
        "the workflow pages the host rather than attempting a repair"
    )


def test_classify_tunnel_token_authentication_failed():
    diag = "cloudflared: authentication failed\n"
    result = tc.classify(diag)
    assert result["class"] == tc.TriageClass.TUNNEL_TOKEN


def test_classify_tunnel_token_unauthorized_error_camelcase():
    diag = "cloudflared: UnauthorizedError while opening connection\n"
    result = tc.classify(diag)
    assert result["class"] == tc.TriageClass.TUNNEL_TOKEN


def test_classify_tunnel_token_priority_beats_image_pull():
    """Tunnel token is priority 2; image_pull is priority 5. If both
    appear in the diag, the tunnel auth failure wins because it's the
    root cause — a token failure might cascade into observed image-pull
    retries on the compose driver, and we want the manual-only flag."""
    diag = (
        "cloudflared: UnauthorizedError\n"
        "docker: manifest not found\n"
    )
    result = tc.classify(diag)
    assert result["class"] == tc.TriageClass.TUNNEL_TOKEN


# ---- watchdog hot-loop ---------------------------------------------------


def test_classify_watchdog_hotloop_start_limit_hit():
    diag = (
        "● tinyassets-daemon.service - TinyAssets MCP daemon\n"
        "   Loaded: loaded (/etc/systemd/system/tinyassets-daemon.service)\n"
        "   Active: failed (Result: start-limit-hit) since Mon 2026-04-22\n"
        "     Docs: https://github.com/Jonnyton/TinyAssets/...\n"
        "  Process: 12345 ExecStart=/usr/bin/docker compose up (code=exited)\n"
    )
    result = tc.classify(diag)
    assert result["class"] == tc.TriageClass.WATCHDOG_HOTLOOP
    assert result["auto_repairable"] is True


def test_classify_watchdog_start_request_repeated():
    diag = (
        "Apr 22 03:20:00 droplet systemd[1]: tinyassets-daemon.service: "
        "Start request repeated too quickly.\n"
    )
    result = tc.classify(diag)
    assert result["class"] == tc.TriageClass.WATCHDOG_HOTLOOP


# ---- unknown (fallthrough) -----------------------------------------------


def test_classify_unknown_falls_through():
    diag = (
        "docker ps: CONTAINER ID   IMAGE   STATUS\n"
        "abc123          tinyassets-daemon    Up 2 hours\n"
        "--- compose ps --- (all healthy)\n"
    )
    result = tc.classify(diag)
    assert result["class"] == tc.TriageClass.UNKNOWN
    assert result["auto_repairable"] is False
    assert result["manual_only"] is False


def test_classify_empty_input_is_unknown():
    result = tc.classify("")
    assert result["class"] == tc.TriageClass.UNKNOWN


def test_classify_whitespace_only_is_unknown():
    result = tc.classify("   \n\n\t\n")
    assert result["class"] == tc.TriageClass.UNKNOWN


# ---- evidence field hygiene ----------------------------------------------


def test_evidence_truncates_past_200_chars():
    long_context = (
        "x" * 500
        + "\nsh[123]: ENV-UNREADABLE: /etc/tinyassets/env\n"
        + "y" * 500
    )
    result = tc.classify(long_context)
    assert result["class"] == tc.TriageClass.ENV_UNREADABLE
    # Window around match is at most ~80 chars (40 before + match + 40 after),
    # well under the 200-char cap. Plus the truncation marker test:
    assert len(result["evidence"]) <= 201  # +1 for the … suffix if hit


def test_evidence_strips_newlines_for_single_line_log():
    diag = "before\nENV-UNREADABLE: problem\nafter"
    result = tc.classify(diag)
    assert "\n" not in result["evidence"]


# ---- CLI entry point -----------------------------------------------------


def test_main_reads_from_stdin_and_emits_json():
    proc = subprocess.run(
        [sys.executable, str(_SCRIPTS / "triage_classify.py")],
        input="ENV-UNREADABLE: /etc/tinyassets/env",
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0, f"exit {proc.returncode}: {proc.stderr}"
    result = json.loads(proc.stdout)
    assert result["class"] == "env_unreadable"
    assert result["auto_repairable"] is True


def test_main_reads_from_input_file(tmp_path):
    diag_file = tmp_path / "diag.txt"
    diag_file.write_text(
        "Out of memory: Killed process 12345 (python)\n",
        encoding="utf-8",
    )
    proc = subprocess.run(
        [
            sys.executable,
            str(_SCRIPTS / "triage_classify.py"),
            "--input-file",
            str(diag_file),
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0
    result = json.loads(proc.stdout)
    assert result["class"] == "oom"


def test_main_exit_2_when_input_file_missing(tmp_path):
    proc = subprocess.run(
        [
            sys.executable,
            str(_SCRIPTS / "triage_classify.py"),
            "--input-file",
            str(tmp_path / "does-not-exist.txt"),
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 2


# ---- priority ordering + multi-class diags ------------------------------


def test_priority_order_env_unreadable_beats_oom():
    """Both markers present; ENV-UNREADABLE wins because it's higher
    priority (root cause of cascading failures)."""
    diag = "ENV-UNREADABLE: /etc/tinyassets/env\nOut of memory: killed process 1\n"
    result = tc.classify(diag)
    assert result["class"] == tc.TriageClass.ENV_UNREADABLE


def test_priority_order_tunnel_beats_disk_full():
    """Manual-only class (tunnel) must win over auto-repairable (disk)
    when both are present — we don't want to 'repair' around a
    fundamentally-broken tunnel token."""
    diag = (
        "cloudflared: UnauthorizedError\n"
        "/dev/vda1  25G  24G  1G  96% /\n"
    )
    result = tc.classify(diag)
    assert result["class"] == tc.TriageClass.TUNNEL_TOKEN


def test_priority_order_oom_beats_image_pull():
    """OOM is root cause if both are present (image pull may retry
    after restart triggered by OOM)."""
    diag = (
        "Out of memory: Killed process 1234\n"
        "Error response from daemon: manifest for x:y not found\n"
    )
    result = tc.classify(diag)
    assert result["class"] == tc.TriageClass.OOM
