"""Host-side key escrow: values never printed, partial sets never written."""

from __future__ import annotations

import hashlib
import os
import shutil
import stat
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import host_key_escrow as esc  # noqa: E402

_POSIX_BASH = pytest.mark.skipif(
    shutil.which("bash") is None or os.name == "nt",
    reason="needs a POSIX bash (host behaviour)",
)

VALUES = {
    "TINYASSETS_SESSION_SEAL_KEY": "c2VhbC1rZXktMzItYnl0ZXMtbG9uZy4uLi4uLi4uLi4=",
    "TINYASSETS_BILLING_ENTITLEMENT_KEY": "billing-token-urlsafe-48-bytes-xxxxxxxxxxxx",
    "TINYASSETS_WEBPUSH_VAPID_PRIVATE_KEY":
        "-----BEGIN PRIVATE KEY-----\\nABC\\n-----END PRIVATE KEY-----\\n",
    "TINYASSETS_APP_INGRESS_HMAC_KEY": "aW5ncmVzcy1rZXktMzItYnl0ZXMtbG9uZy4uLi4uLi4=",
}


def _h(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


@pytest.fixture
def host(tmp_path, monkeypatch):
    """A fake /etc/tinyassets with all four keys, wired into the module."""
    etc = tmp_path / "etc"
    etc.mkdir()
    env_lines = [f"{k}={v}" for k, v in VALUES.items() if k != "TINYASSETS_APP_INGRESS_HMAC_KEY"]
    (etc / "env").write_text("OTHER=x\n" + "\n".join(env_lines) + "\n", encoding="utf-8")
    (etc / "app-ingress.env").write_text(
        f"TINYASSETS_APP_INGRESS_HMAC_KEY={VALUES['TINYASSETS_APP_INGRESS_HMAC_KEY']}\n",
        encoding="utf-8")
    paths = {k: str(etc / ("app-ingress.env" if "INGRESS" in k else "env")) for k in VALUES}
    monkeypatch.setattr(esc, "ESCROWED_KEYS", paths)
    monkeypatch.setattr(esc, "_LEGACY_FOR", {str(etc / "app-ingress.env"): str(etc / "no-legacy")})
    return etc


def _escrow_text() -> str:
    return "".join(f"{k}={v}\n" for k, v in VALUES.items())


@pytest.mark.parametrize("text", [
    "TINYASSETS_SESSION_SEAL_KEY=old\nexport TINYASSETS_SESSION_SEAL_KEY=new\n",
    "TINYASSETS_SESSION_SEAL_KEY=old\nTINYASSETS_SESSION_SEAL_KEY=new\n",
    "TINYASSETS_SESSION_SEAL_KEY='quoted'\n",
    "  TINYASSETS_SESSION_SEAL_KEY=indented\n",
    "TINYASSETS_SESSION_SEAL_KEY = spaced\n",
    "TINYASSETS_SESSION_SEAL_KEY=value # comment\n",
])
def test_ambiguous_shapes_are_unsupported_never_guessed(text):
    assert esc.parse_value(text, "TINYASSETS_SESSION_SEAL_KEY") is esc.UNSUPPORTED


def test_write_produces_exactly_the_four_keys_at_0600(host, tmp_path, capsys):
    out = tmp_path / "escrow.env"
    assert esc.write(out) == 0
    assert out.read_text(encoding="utf-8") == _escrow_text()
    if os.name != "nt":
        assert stat.S_IMODE(out.stat().st_mode) == 0o600
    captured = capsys.readouterr()
    for value in VALUES.values():
        assert value not in captured.out + captured.err


def test_write_refuses_a_partial_set_and_writes_nothing(host, tmp_path, capsys):
    (host / "app-ingress.env").write_text("", encoding="utf-8")
    out = tmp_path / "escrow.env"
    assert esc.write(out) == 2
    assert not out.exists()
    assert "TINYASSETS_APP_INGRESS_HMAC_KEY" in capsys.readouterr().err


def test_write_never_overwrites_an_existing_file(host, tmp_path):
    out = tmp_path / "escrow.env"
    out.write_text("keep", encoding="utf-8")
    with pytest.raises(FileExistsError):
        esc.write(out)
    assert out.read_text(encoding="utf-8") == "keep"


def test_verify_prints_verdicts_only(host, capsys):
    tampered = _escrow_text().replace(VALUES["TINYASSETS_BILLING_ENTITLEMENT_KEY"], "other")
    assert esc.verify(tampered) == 1
    out = capsys.readouterr().out
    assert "TINYASSETS_SESSION_SEAL_KEY: match" in out
    assert "TINYASSETS_BILLING_ENTITLEMENT_KEY: MISMATCH" in out
    for value in VALUES.values():
        assert value not in out and _h(value) not in out


def test_verify_all_match_exits_zero(host, capsys):
    assert esc.verify(_escrow_text()) == 0
    assert capsys.readouterr().out.count(": match") == 4


def test_verify_reports_missing_and_unsupported(host, capsys):
    text = "TINYASSETS_SESSION_SEAL_KEY='x'\n"
    assert esc.verify(text) == 1
    out = capsys.readouterr().out
    assert "TINYASSETS_SESSION_SEAL_KEY: escrow-format-unsupported" in out
    assert "TINYASSETS_APP_INGRESS_HMAC_KEY: not-in-escrow" in out


def test_check_manifest_proves_the_keys_match_the_backup(host, capsys):
    manifest = "".join(f"{k} {_h(v)}\n" for k, v in VALUES.items())
    assert esc.check_manifest(manifest) == 0
    wrong = manifest.replace(_h(VALUES["TINYASSETS_SESSION_SEAL_KEY"]), "0" * 64)
    assert esc.check_manifest(wrong) == 1
    assert "TINYASSETS_SESSION_SEAL_KEY: MISMATCH" in capsys.readouterr().out


@_POSIX_BASH
def test_install_sets_each_key_once_into_its_own_file(host, tmp_path, capsys):
    record = tmp_path / "helper.calls"
    helper = tmp_path / "helper.sh"
    helper.write_text(
        "#!/usr/bin/env bash\n"
        f'printf "%s %s %s %s\\n" "$1" "$2" "$TINYASSETS_ENV_FILE" '
        f'"${{TINYASSETS_LEGACY_ENV_FILE:-none}}" >> "{record.as_posix()}"\n'
        "cat > /dev/null\n",
        encoding="utf-8", newline="\n")
    assert esc.install(_escrow_text(), str(helper)) == 0
    calls = record.read_text(encoding="utf-8").splitlines()
    assert len(calls) == 4
    assert all(c.startswith("set-once TINYASSETS_") for c in calls)
    ingress = next(c for c in calls if "INGRESS" in c)
    assert ingress.split()[2].endswith("app-ingress.env") and ingress.split()[3] != "none"
    out = capsys.readouterr().out
    for value in VALUES.values():
        assert value not in out


@_POSIX_BASH
def test_install_reports_a_refusal_and_fails(host, tmp_path, capsys):
    helper = tmp_path / "helper.sh"
    helper.write_text("#!/usr/bin/env bash\ncat > /dev/null\nexit 5\n",
                      encoding="utf-8", newline="\n")
    assert esc.install(_escrow_text(), str(helper)) == 1
    assert "refused (helper exit 5)" in capsys.readouterr().out


def test_install_refuses_a_partial_escrow(host, tmp_path):
    assert esc.install("TINYASSETS_SESSION_SEAL_KEY=x\n", str(tmp_path / "unused")) == 2


def test_the_verify_workflow_compares_on_the_host_and_never_traces():
    wf = yaml.safe_load((REPO / ".github/workflows/verify-escrowed-keys.yml").read_text())
    assert set(wf[True]) == {"workflow_dispatch", "schedule"}
    steps = wf["jobs"]["verify"]["steps"]
    step = next(s for s in steps if s.get("name", "").startswith("Compare"))
    run = step["run"]
    remote = run.split("<<'ESCROW_VERIFY'\n", 1)[1].split("\nESCROW_VERIFY", 1)[0]
    assert 'rclone cat "${dest%/*}/escrow/host-keys.env" | python3' in remote
    assert "host_key_escrow.py\" verify" in remote
    assert "trap 'rm -rf -- \"${stage}\"' EXIT" in remote
    for s in steps:
        text = s.get("run", "") or ""
        assert "set -x" not in text and "xtrace" not in text
    workflow = (REPO / ".github/workflows/verify-escrowed-keys.yml").read_text()
    assert "secrets.TINYASSETS_" not in workflow


def test_restore_installs_the_escrow_and_proves_it_against_the_archive():
    restore = (REPO / "deploy" / "backup-restore.sh").read_text(encoding="utf-8")
    block = restore.split("# ----- 4b. restore the escrowed host keys", 1)[1]
    block = block.split("# ----- 5.", 1)[0]
    assert 'host_key_escrow.py"' in restore
    assert '"${escrow_tool}" install "${env_helper}" < "${ESCROW_FILE}"' in block
    assert '"${escrow_tool}" check-manifest "${manifest}"' in block
    assert block.count("exit 6") >= 3
    assert "-L \"${ESCROW_FILE}\"" in block, "a symlinked escrow file is refused"
