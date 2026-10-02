"""backup.sh copies both tiers off-region, and the GitHub copy is brain-only.

target-architecture S1a.3. BACKUP_DEST is a Spaces bucket in sfo3, the droplet's
own region (docs/concerns/2026-10-02-backups-share-the-droplets-region.md). The
full tier is about 4 GB and got a 422 from GitHub's 2 GiB asset limit every
night (docs/concerns/2026-10-02-github-full-tier-backup-exceeds-2gib.md).

Runs the real backup.sh against recording fakes for docker, rclone and the GH
shipper, so it needs bash and flock (the Linux oracle, or a Linux host).
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
BACKUP_SH = REPO / "deploy" / "backup.sh"
_BASH = shutil.which("bash")
_FLOCK = shutil.which("flock")

pytestmark = pytest.mark.skipif(
    not (_BASH and _FLOCK) or os.name == "nt",
    reason="needs bash + flock (Linux)",
)


def _fake(bin_dir: Path, name: str, body: str) -> None:
    path = bin_dir / name
    path.write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8", newline="\n")
    path.chmod(0o755)


ESCROW_VALUES = {
    "TINYASSETS_SESSION_SEAL_KEY": "seal-value-not-to-be-logged-0123456789abcdef",
    "TINYASSETS_BILLING_ENTITLEMENT_KEY": "billing-value-not-to-be-logged-0123456789",
    "TINYASSETS_WEBPUSH_VAPID_PRIVATE_KEY": "-----BEGIN PRIVATE KEY-----\\nVAPIDVALUE\\n-----END",
    "TINYASSETS_APP_INGRESS_HMAC_KEY": "ingress-value-not-to-be-logged-0123456789",
}


def _run(tmp_path: Path, *, offregion: str | None, fail_offregion: bool = False,
         escrow_complete: bool = True):
    volume = tmp_path / "volume"
    volume.mkdir()
    con = sqlite3.connect(volume / ".tinyassets.db")
    con.execute("create table t(x)")
    con.commit()
    con.close()
    (volume / "ledger.json").write_text("{}", encoding="utf-8")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "rclone.calls"
    _fake(bin_dir, "docker", f'echo "{volume}"\n')
    _fake(bin_dir, "rclone", f'''echo "$*" >> "{calls}"
case "$1" in
  copyto)
    if [[ "{1 if fail_offregion else 0}" == "1" && "${{@: -1}}" == offregion:* ]]; then exit 1; fi
    exit 0 ;;
  lsf) exit 0 ;;
  *) exit 0 ;;
esac
''')
    shipped = tmp_path / "shipped"
    # The shipper is resolved relative to backup.sh; stand in a copy of the
    # deploy dir next to a fake scripts/backup_ship_gh.py that records calls.
    root = tmp_path / "root"
    (root / "deploy").mkdir(parents=True)
    (root / "scripts").mkdir()
    shutil.copy(BACKUP_SH, root / "deploy" / "backup.sh")
    shutil.copy(REPO / "scripts" / "backup_prune.py", root / "scripts" / "backup_prune.py")
    shutil.copy(REPO / "scripts" / "host_key_escrow.py", root / "scripts" / "host_key_escrow.py")
    etc = tmp_path / "etc"
    etc.mkdir()
    keys = dict(ESCROW_VALUES)
    if not escrow_complete:
        keys.pop("TINYASSETS_APP_INGRESS_HMAC_KEY")
    (etc / "env").write_text("".join(
        f"{k}={v}\n" for k, v in keys.items() if "INGRESS" not in k), encoding="utf-8")
    (etc / "app-ingress.env").write_text("".join(
        f"{k}={v}\n" for k, v in keys.items() if "INGRESS" in k), encoding="utf-8")
    (root / "scripts" / "backup_ship_gh.py").write_text(
        f"import sys\nopen({str(shipped)!r}, 'a').write(sys.argv[1] + '\\n')\n",
        encoding="utf-8",
    )
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "BACKUP_VOLUME": "tinyassets-test-volume-does-not-exist",
        "BACKUP_DEST": "spaces:sfo3-bucket/backups",
        "BACKUP_LOG": str(tmp_path / "backup.log"),
        "GH_TOKEN": "x",
        "TINYASSETS_ESCROW_ETC": str(etc),
    }
    if offregion is not None:
        env["BACKUP_OFFREGION_DEST"] = offregion
    result = subprocess.run(
        [_BASH, str(root / "deploy" / "backup.sh")],
        capture_output=True, text=True, env=env, timeout=120,
    )
    lines = calls.read_text(encoding="utf-8").splitlines() if calls.exists() else []
    ships = shipped.read_text(encoding="utf-8").splitlines() if shipped.exists() else []
    return result, lines, ships


def test_both_tiers_go_off_region_and_are_pruned_there(tmp_path):
    result, calls, _ = _run(tmp_path, offregion="offregion:tinyassets-offregion/backups")
    assert result.returncode == 0, result.stdout + result.stderr
    off = [c for c in calls
           if c.startswith("copyto") and "offregion:" in c and "/escrow/" not in c]
    assert len(off) == 2
    assert any("/tinyassets-brain-" in c for c in off)
    assert any("/tinyassets-data-" in c for c in off)
    assert "lsf offregion:tinyassets-offregion/backups/" in calls
    assert "lsf spaces:sfo3-bucket/backups/" in calls


def test_a_failed_off_region_copy_fails_the_backup_after_the_independent_work(tmp_path):
    """The GitHub brain copy and retention still run; only then exit 3 (Codex on #4279)."""
    result, calls, ships = _run(tmp_path, offregion="offregion:tinyassets-offregion/backups",
                                fail_offregion=True)
    assert result.returncode == 3
    assert "off-region rclone upload failed" in result.stdout
    assert "WITHOUT its off-region copy" in result.stdout
    assert len(ships) == 1, "the GitHub brain copy must still be shipped"
    assert "lsf spaces:sfo3-bucket/backups/" in calls, "sfo3 retention must still run"


def test_an_unconfigured_off_region_copy_is_loud(tmp_path):
    result, calls, _ = _run(tmp_path, offregion=None)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "NO off-region copy" in result.stdout
    assert not [c for c in calls if "offregion:" in c]


def test_github_gets_the_brain_tier_only(tmp_path):
    result, _, ships = _run(tmp_path, offregion="offregion:tinyassets-offregion/backups")
    assert result.returncode == 0, result.stdout + result.stderr
    assert len(ships) == 1
    assert "/tinyassets-brain-" in ships[0]


# --- host-key escrow ---------------------------------------------------------

def test_the_escrow_goes_to_its_own_prefix_content_addressed_and_latest(tmp_path):
    result, calls, _ = _run(tmp_path, offregion="offregion:tinyassets-offregion/backups")
    assert result.returncode == 0, result.stdout + result.stderr
    escrow = [c for c in calls if "copyto" in c.split() and "/escrow/" in c]
    assert len(escrow) == 2
    assert any("offregion:tinyassets-offregion/escrow/history/host-keys-" in c for c in escrow)
    assert any(c.endswith("offregion:tinyassets-offregion/escrow/host-keys.env") for c in escrow)
    assert "host-key escrow OK" in result.stdout


def test_no_escrowed_value_reaches_the_output_or_the_log(tmp_path):
    result, _, _ = _run(tmp_path, offregion="offregion:tinyassets-offregion/backups")
    log = (tmp_path / "backup.log").read_text(encoding="utf-8")
    for value in ESCROW_VALUES.values():
        assert value not in result.stdout + result.stderr + log


def test_a_partial_key_set_is_never_escrowed_and_fails_the_backup(tmp_path):
    result, calls, _ = _run(tmp_path, offregion="offregion:tinyassets-offregion/backups",
                            escrow_complete=False)
    assert result.returncode == 3
    assert not [c for c in calls if "/escrow/" in c]
    assert "host-key escrow refused" in result.stdout


def test_the_archive_carries_the_key_hash_manifest_not_the_keys(tmp_path):
    result, _, _ = _run(tmp_path, offregion="offregion:tinyassets-offregion/backups")
    assert result.returncode == 0, result.stdout + result.stderr
    manifest = (tmp_path / "volume" / ".escrow-key-hashes").read_text(encoding="utf-8")
    import hashlib

    for name, value in ESCROW_VALUES.items():
        assert f"{name} {hashlib.sha256(value.encode()).hexdigest()}" in manifest
        assert value not in manifest

