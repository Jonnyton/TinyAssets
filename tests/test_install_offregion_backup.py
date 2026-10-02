"""install-host-services converges the off-region backup remote (S1a.3).

The step mirrors "Ensure off-host backup configuration" (the sfo3 remote): a
fail-closed state classifier, keys minted through the DO API from DO_API_TOKEN,
rollback that requires HTTP 204, a bounded propagation probe, and every droplet
mutation inside guard-host-mutation. What is new is the bucket: it does not
exist yet, so a `fullaccess` key is minted only to create it, on the runner,
and deleted before anything reaches the droplet.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
WORKFLOW = REPO / ".github" / "workflows" / "install-host-services.yml"
STEP = "Ensure off-region backup configuration"
_BASH = shutil.which("bash")


def _steps() -> list[dict]:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]["install"]["steps"]


def _run() -> str:
    return next(s for s in _steps() if s.get("name") == STEP)["run"]


def _heredoc(run: str, tag: str) -> str:
    body = run.split(f"<<'{tag}'\n", 1)[1]
    return body.split(f"\n{tag}\n", 1)[0]


def test_ordering_after_the_sfo3_remote_and_before_the_bundle_and_timers():
    names = [s.get("name") for s in _steps()]
    assert names.index("Refuse host mutation during stop-writer cutover") < names.index(STEP)
    assert names.index("Ensure off-host backup configuration") < names.index(STEP)
    assert names.index(STEP) < names.index("Install exact uptime bundle")


def test_target_is_a_different_region_from_backup_dest():
    run = _run()
    assert 'bucket="tinyassets-offregion"' in run
    assert 'endpoint="nyc3.digitaloceanspaces.com"' in run
    assert "sfo3" not in run.split("OFFREGION_STATE", 1)[0].replace("sfo3,", "")


def test_fullaccess_is_bootstrap_only_and_deleted_before_the_droplet_sees_a_key():
    run = _run()
    assert run.count('"permission":"fullaccess"') == 1
    # Search the main flow only: cleanup() carries the same call for failure paths.
    main_flow_start = run.index("trap cleanup EXIT")
    bootstrap_delete = run.index(
        'if ! delete_key "${bootstrap_access_key}"; then', main_flow_start)
    droplet_key = run.index('"permission":"readwrite"')
    first_droplet_copy = run.index("offregion.section")
    assert bootstrap_delete < droplet_key
    assert bootstrap_delete < first_droplet_copy
    # The cleanup also deletes the bootstrap key on any failure path.
    cleanup = run.split("cleanup() {", 1)[1].split("trap cleanup EXIT", 1)[0]
    assert 'delete_key "${bootstrap_access_key}"' in cleanup


def test_key_deletion_requires_http_204():
    run = _run()
    delete_fn = run.split("delete_key() {", 1)[1].split("\n}", 1)[0]
    assert "-X DELETE" in delete_fn
    assert '"${status}" == "204"' in delete_fn


def test_secrets_are_masked_and_never_in_argv_or_logs():
    run = _run()
    assert run.count("::add-mask::") >= 4
    assert "Authorization: Bearer ${DO_API_TOKEN}" not in run
    assert '-H @"${api_header_file}"' in run
    assert 'cat "${response_file}"' not in run
    assert "--max-filesize 4096" in run


def test_every_droplet_mutation_is_inside_the_host_mutation_guard():
    run = _run()
    # remote install + rollback
    assert run.count("guard-host-mutation") == 2
    assert run.count("--command-timeout") == 2


def test_the_sfo3_remote_is_kept_when_offregion_is_added():
    remote = _heredoc(_run(), "OFFREGION_REMOTE")
    assert 'rclone_conf_section.py" add' in remote
    assert "install -m 0600" not in remote, "must merge, never overwrite rclone.conf"
    assert 'install-tinyassets-env.sh" set BACKUP_OFFREGION_DEST' in remote
    assert "for delay in 0 5 10 20 30" in remote


@pytest.mark.skipif(not _BASH, reason="bash is unavailable")
def test_the_step_and_its_remote_blocks_parse():
    run = _run()
    for text in (run, _heredoc(run, "OFFREGION_STATE"), _heredoc(run, "OFFREGION_REMOTE")):
        parsed = subprocess.run([_BASH, "-n"], input=text.encode(), capture_output=True)
        assert parsed.returncode == 0, parsed.stderr.decode(errors="replace")


@pytest.mark.skipif(not _BASH or shutil.which("awk") is None, reason="needs bash + awk")
@pytest.mark.parametrize(
    ("env_text", "conf_text", "rclone_rc", "expected"),
    [
        ("BACKUP_OFFREGION_DEST=offregion:tinyassets-offregion/backups\n",
         "[spaces]\n[offregion]\n", 0, "configured_ready"),
        ("BACKUP_OFFREGION_DEST=offregion:tinyassets-offregion/backups\n",
         "[spaces]\n[offregion]\n", 1, "partial_or_invalid"),
        ("", "[spaces]\n", 0, "completely_absent"),
        ("BACKUP_OFFREGION_DEST=offregion:tinyassets-offregion/backups\n",
         "[spaces]\n", 0, "partial_or_invalid"),
        ("", "[spaces]\n[offregion]\n", 0, "partial_or_invalid"),
        ("BACKUP_OFFREGION_DEST=offregion:other/backups\n",
         "[spaces]\n[offregion]\n", 0, "partial_or_invalid"),
        ("BACKUP_OFFREGION_DEST=offregion:tinyassets-offregion/backups\n" * 2,
         "[spaces]\n[offregion]\n", 0, "partial_or_invalid"),
    ],
)
def test_state_classifier_is_fail_closed(tmp_path, env_text, conf_text, rclone_rc, expected):
    env_file = tmp_path / "env"
    env_file.write_text(env_text, encoding="utf-8", newline="\n")
    conf = tmp_path / "rclone.conf"
    conf.write_text(conf_text, encoding="utf-8", newline="\n")
    fake = tmp_path / "rclone"
    fake.write_text(f"#!/usr/bin/env bash\nexit {rclone_rc}\n", encoding="utf-8", newline="\n")
    fake.chmod(0o755)
    script = tmp_path / "state.sh"
    script.write_text(_heredoc(_run(), "OFFREGION_STATE"), encoding="utf-8", newline="\n")

    def posix(path: Path) -> str:
        return path.as_posix()

    result = subprocess.run(
        [_BASH, posix(script), "offregion:tinyassets-offregion/backups",
         posix(env_file), posix(conf), posix(fake)],
        capture_output=True, text=True,
    )
    assert result.stdout.strip() == expected, result.stderr
