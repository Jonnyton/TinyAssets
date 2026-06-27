"""Tests for scripts/bootstrap_add_second_ssh_key.py — bus-factor SSH key seeder."""

from __future__ import annotations

import importlib.util
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_SCRIPT = Path(__file__).parent.parent / "scripts" / "bootstrap_add_second_ssh_key.py"


def _load() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("bootstrap_add_second_ssh_key", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bsk = _load()


# ── Arg / env validation ──────────────────────────────────────────────


def test_exits_1_without_host(monkeypatch) -> None:
    monkeypatch.delenv("DROPLET_HOST", raising=False)
    with patch("sys.argv", ["bsk", "--primary-key", "/tmp/k"]), \
         pytest.raises(SystemExit) as exc:
        bsk.main()
    assert exc.value.code == 1


def test_exits_1_without_primary_key(monkeypatch) -> None:
    monkeypatch.delenv("PRIMARY_SSH_KEY_PATH", raising=False)
    with patch("sys.argv", ["bsk", "--host", "1.2.3.4"]), \
         pytest.raises(SystemExit) as exc:
        bsk.main()
    assert exc.value.code == 1


# ── Idempotency guard ─────────────────────────────────────────────────


def test_run_skips_when_secret_already_exists_in_legacy_mode(monkeypatch) -> None:
    """Legacy `--gh-secret` mode preserves the original idempotency guard."""
    monkeypatch.setattr(bsk, "_secret_exists", lambda token, repo: True)
    monkeypatch.setattr(bsk, "_gh_token", lambda t: "tok")
    called = []
    monkeypatch.setattr(bsk, "_append_pubkey", lambda *a: called.append("upload"))
    monkeypatch.setattr(bsk, "_seed_secret", lambda *a: called.append("seed"))
    bsk.run(host="1.2.3.4", primary_key="/tmp/k", repo="owner/repo",
            gh_secret=True)
    assert called == []


def test_run_does_not_check_secret_in_default_vault_mode(monkeypatch) -> None:
    """New default path: `gh_secret=False` means we don't gate on the
    GH secret existing (that's a vault-first cutover — Task #7)."""
    called = []
    monkeypatch.setattr(
        bsk, "_secret_exists",
        lambda *a: called.append("secret_check") or False,
    )
    monkeypatch.setattr(bsk, "_gh_token", lambda t: "tok")
    monkeypatch.setattr(bsk, "_append_pubkey", lambda *a: None)
    bsk.run(host="1.2.3.4", primary_key="/tmp/k", repo="owner/repo",
            dry_run=True)
    assert "secret_check" not in called


def test_dry_run_skips_mutations(monkeypatch) -> None:
    monkeypatch.setattr(bsk, "_secret_exists", lambda token, repo: False)
    monkeypatch.setattr(bsk, "_gh_token", lambda t: "tok")
    called = []
    monkeypatch.setattr(bsk, "_seed_secret", lambda *a: called.append("seed"))
    monkeypatch.setattr(bsk, "_append_pubkey", lambda *a: called.append("upload"))
    bsk.run(host="1.2.3.4", primary_key="/tmp/k", repo="owner/repo",
            dry_run=True, gh_secret=True)
    assert called == []


# ── SSH append ────────────────────────────────────────────────────────


def _run_with_fake_keygen(monkeypatch, tmp_path, pubkey_present: bool) -> list:
    """Helper: patches keygen + all I/O, returns list of upload calls."""
    monkeypatch.setattr(bsk, "_secret_exists", lambda t, r: False)
    monkeypatch.setattr(bsk, "_gh_token", lambda t: "tok")
    monkeypatch.setattr(bsk, "_pubkey_already_present", lambda *a: pubkey_present)
    uploaded = []
    monkeypatch.setattr(bsk, "_append_pubkey", lambda *a: uploaded.append(True))
    monkeypatch.setattr(bsk, "_seed_secret", lambda *a: None)

    # Write fake key files that the script will read.
    fake_priv = "-----BEGIN OPENSSH PRIVATE KEY-----\nfake\n-----END OPENSSH PRIVATE KEY-----\n"
    fake_pub = "ssh-ed25519 AAAA tinyassets-backup-key\n"

    real_td = __import__("tempfile").TemporaryDirectory

    original_path_class = Path

    class _PatchedTD:
        def __enter__(self):
            self._real = real_td()
            d = self._real.__enter__()
            (original_path_class(d) / "second_key").write_text(fake_priv)
            (original_path_class(d) / "second_key.pub").write_text(fake_pub)
            return d

        def __exit__(self, *args):
            return self._real.__exit__(*args)

    monkeypatch.setattr("tempfile.TemporaryDirectory", _PatchedTD)
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stderr="", stdout="")
        # Redirect the vault-first default write to tmp_path (default
        # would land in ~/.ssh/ which is not a test-safe location).
        bsk.run(host="1.2.3.4", primary_key="/tmp/k", repo="owner/repo",
                out_dir=str(tmp_path))
    return uploaded


def test_pubkey_already_present_skips_upload(monkeypatch, tmp_path) -> None:
    uploaded = _run_with_fake_keygen(monkeypatch, tmp_path, pubkey_present=True)
    assert uploaded == []


def test_upload_attempted_when_pubkey_absent(monkeypatch, tmp_path) -> None:
    uploaded = _run_with_fake_keygen(monkeypatch, tmp_path, pubkey_present=False)
    assert uploaded == [True]


# ── GH token resolution ───────────────────────────────────────────────


def test_gh_token_from_env(monkeypatch) -> None:
    monkeypatch.setenv("GH_TOKEN", "env-token")
    assert bsk._gh_token(None) == "env-token"


def test_gh_token_explicit_arg_takes_priority(monkeypatch) -> None:
    monkeypatch.setenv("GH_TOKEN", "env-token")
    assert bsk._gh_token("explicit-token") == "explicit-token"


# ── SSH helpers ───────────────────────────────────────────────────────


def test_pubkey_already_present_parses_yes(monkeypatch) -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="YES\n", stderr="")
        result = bsk._pubkey_already_present("1.2.3.4", "/tmp/k", "AAAA")
    assert result is True


def test_pubkey_not_present_parses_no(monkeypatch) -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="NO\n", stderr="")
        result = bsk._pubkey_already_present("1.2.3.4", "/tmp/k", "AAAA")
    assert result is False


def test_append_pubkey_raises_on_nonzero(monkeypatch) -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="permission denied")
        with pytest.raises(RuntimeError, match="failed to append"):
            bsk._append_pubkey("1.2.3.4", "/tmp/k", "ssh-ed25519 AAAA backup")


# ── Script file exists ────────────────────────────────────────────────


def test_script_exists() -> None:
    assert _SCRIPT.is_file(), f"missing: {_SCRIPT}"


# ── Resilience audit updated ──────────────────────────────────────────


def test_audit_mentions_dual_key() -> None:
    audit = Path(__file__).parent.parent / "docs" / "ops" / "host-off-resilience-audit.md"
    text = audit.read_text(encoding="utf-8")
    assert "DO_SSH_KEY_BACKUP" in text or "dual-key" in text or "bus factor" in text.lower()


def test_audit_mentions_second_key_script() -> None:
    audit = Path(__file__).parent.parent / "docs" / "ops" / "host-off-resilience-audit.md"
    text = audit.read_text(encoding="utf-8")
    assert "bootstrap_add_second_ssh_key" in text


def test_secret_name_constant() -> None:
    assert bsk.SECRET_NAME == "DO_SSH_KEY_BACKUP"


# ── DO account-keys registration ──────────────────────────────────────


def test_do_key_exists_matches_on_key_body(monkeypatch) -> None:
    """_do_key_exists compares the middle field (the base64 key body),
    not the comment or key type — rotating comments shouldn't re-register."""
    fake_response_json = (
        '{"ssh_keys": ['
        '{"id": 1, "public_key": "ssh-ed25519 AAAAC3... operator@laptop"},'
        '{"id": 2, "public_key": "ssh-ed25519 BBBBB2... other"}'
        ']}'
    ).encode()

    class _FakeResp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return fake_response_json

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda req, timeout=None: _FakeResp(),
    )
    # Match by key body — different comment, same key → exists.
    assert bsk._do_key_exists("tok", "ssh-ed25519 AAAAC3... completely-different-comment") is True
    # Different key body → doesn't exist.
    assert bsk._do_key_exists("tok", "ssh-ed25519 ZZZZZ9... anything") is False


def test_do_register_key_parses_response() -> None:
    fake_post_response = (
        '{"ssh_key": {"id": 42, "fingerprint": "de:ad:be:ef", '
        '"public_key": "ssh-ed25519 AAAA", "name": "tinyassets-deploy-backup"}}'
    ).encode()

    class _FakeResp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return fake_post_response

    def fake_opener(req, timeout=None):
        return _FakeResp()

    rec = bsk._do_register_key(
        "tok", "ssh-ed25519 AAAA tinyassets-backup-key",
        "tinyassets-deploy-backup",
        opener=fake_opener,
    )
    assert rec["id"] == 42
    assert rec["fingerprint"] == "de:ad:be:ef"


# ── New mode flags ────────────────────────────────────────────────────


def test_print_only_emits_private_pem_to_stdout(monkeypatch, tmp_path, capsys):
    """--print-only writes the PEM to stdout and never touches ~/.ssh."""
    monkeypatch.setattr(bsk, "_secret_exists", lambda *a: False)
    monkeypatch.setattr(bsk, "_gh_token", lambda t: "tok")
    monkeypatch.setattr(bsk, "_pubkey_already_present", lambda *a: True)

    fake_priv = (
        "-----BEGIN OPENSSH PRIVATE KEY-----\n"
        "STDOUT-PEM\n-----END OPENSSH PRIVATE KEY-----\n"
    )
    fake_pub = "ssh-ed25519 AAAAFAKE tinyassets-backup-key\n"
    real_td = __import__("tempfile").TemporaryDirectory

    class _PatchedTD:
        def __enter__(self):
            self._real = real_td()
            d = self._real.__enter__()
            (Path(d) / "second_key").write_text(fake_priv)
            (Path(d) / "second_key.pub").write_text(fake_pub)
            return d

        def __exit__(self, *args): return self._real.__exit__(*args)

    monkeypatch.setattr("tempfile.TemporaryDirectory", _PatchedTD)
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        bsk.run(host="1.2.3.4", primary_key="/tmp/k", repo="owner/repo",
                print_only=True)
    captured = capsys.readouterr()
    assert "STDOUT-PEM" in captured.out, "private PEM must land on stdout"


def test_default_mode_writes_key_files_to_out_dir(monkeypatch, tmp_path):
    """Default (no gh_secret, no print_only) writes to --out-dir with
    the DEFAULT_KEY_NAME — what the vault-first runbook documents."""
    monkeypatch.setattr(bsk, "_secret_exists", lambda *a: False)
    monkeypatch.setattr(bsk, "_gh_token", lambda t: "tok")
    monkeypatch.setattr(bsk, "_pubkey_already_present", lambda *a: True)

    fake_priv = "-----BEGIN OPENSSH PRIVATE KEY-----\nFILE-PEM\n-----END OPENSSH PRIVATE KEY-----\n"
    fake_pub = "ssh-ed25519 AAAAFAKE tinyassets-backup-key\n"
    real_td = __import__("tempfile").TemporaryDirectory

    class _PatchedTD:
        def __enter__(self):
            self._real = real_td()
            d = self._real.__enter__()
            (Path(d) / "second_key").write_text(fake_priv)
            (Path(d) / "second_key.pub").write_text(fake_pub)
            return d

        def __exit__(self, *args): return self._real.__exit__(*args)

    monkeypatch.setattr("tempfile.TemporaryDirectory", _PatchedTD)
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        bsk.run(host="1.2.3.4", primary_key="/tmp/k", repo="owner/repo",
                out_dir=str(tmp_path))

    priv = tmp_path / bsk.DEFAULT_KEY_NAME
    pub = tmp_path / f"{bsk.DEFAULT_KEY_NAME}.pub"
    assert priv.is_file(), "private key file should be written"
    assert pub.is_file(), "public key file should be written"
    assert "FILE-PEM" in priv.read_text()
    assert pub.read_text().startswith("ssh-ed25519 AAAAFAKE")


def test_mutually_exclusive_print_only_and_gh_secret(monkeypatch) -> None:
    """CLI enforcement: --print-only + --gh-secret together is exit 1."""
    with patch("sys.argv", ["bsk", "--host", "1.2.3.4", "--primary-key", "/tmp/k",
                            "--print-only", "--gh-secret"]), \
         pytest.raises(SystemExit) as exc:
        bsk.main()
    assert exc.value.code == 1


def test_do_register_skipped_when_no_token(monkeypatch, tmp_path) -> None:
    """Without --do-token, DO account registration is silently skipped."""
    monkeypatch.setattr(bsk, "_secret_exists", lambda *a: False)
    monkeypatch.setattr(bsk, "_gh_token", lambda t: "tok")
    monkeypatch.setattr(bsk, "_pubkey_already_present", lambda *a: True)
    do_calls = []
    monkeypatch.setattr(bsk, "_do_register_key",
                        lambda *a, **k: do_calls.append("registered") or {})
    monkeypatch.setattr(bsk, "_do_key_exists", lambda *a: False)

    fake_priv = "-----BEGIN OPENSSH PRIVATE KEY-----\nFAKE\n-----END OPENSSH PRIVATE KEY-----\n"
    fake_pub = "ssh-ed25519 AAAA tinyassets-backup-key\n"
    real_td = __import__("tempfile").TemporaryDirectory

    class _PatchedTD:
        def __enter__(self):
            self._real = real_td()
            d = self._real.__enter__()
            (Path(d) / "second_key").write_text(fake_priv)
            (Path(d) / "second_key.pub").write_text(fake_pub)
            return d

        def __exit__(self, *args): return self._real.__exit__(*args)

    monkeypatch.setattr("tempfile.TemporaryDirectory", _PatchedTD)
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        bsk.run(host="1.2.3.4", primary_key="/tmp/k", repo="owner/repo",
                out_dir=str(tmp_path), do_token=None)
    assert do_calls == []


def test_do_register_runs_when_token_set(monkeypatch, tmp_path) -> None:
    """With --do-token set, DO registration fires (unless already present)."""
    monkeypatch.setattr(bsk, "_secret_exists", lambda *a: False)
    monkeypatch.setattr(bsk, "_gh_token", lambda t: "tok")
    monkeypatch.setattr(bsk, "_pubkey_already_present", lambda *a: True)
    do_calls = []
    monkeypatch.setattr(bsk, "_do_key_exists", lambda *a: False)
    monkeypatch.setattr(
        bsk, "_do_register_key",
        lambda *a, **k: do_calls.append((a, k)) or {"id": 99, "fingerprint": "xx"},
    )

    fake_priv = "-----BEGIN OPENSSH PRIVATE KEY-----\nFAKE\n-----END OPENSSH PRIVATE KEY-----\n"
    fake_pub = "ssh-ed25519 AAAA tinyassets-backup-key\n"
    real_td = __import__("tempfile").TemporaryDirectory

    class _PatchedTD:
        def __enter__(self):
            self._real = real_td()
            d = self._real.__enter__()
            (Path(d) / "second_key").write_text(fake_priv)
            (Path(d) / "second_key.pub").write_text(fake_pub)
            return d

        def __exit__(self, *args): return self._real.__exit__(*args)

    monkeypatch.setattr("tempfile.TemporaryDirectory", _PatchedTD)
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        bsk.run(host="1.2.3.4", primary_key="/tmp/k", repo="owner/repo",
                out_dir=str(tmp_path), do_token="do-tok-abc")
    assert len(do_calls) == 1
    # Verify label passed through (positional arg 2 is label).
    assert do_calls[0][0][2] == bsk.DEFAULT_DO_KEY_LABEL


def test_default_key_name_and_do_label_constants() -> None:
    """Regression guard — runbook + vault path depend on these names."""
    assert bsk.DEFAULT_KEY_NAME == "tinyassets_deploy_backup_ed25519"
    assert bsk.DEFAULT_DO_KEY_LABEL == "tinyassets-deploy-backup"
    assert bsk.DO_API_KEYS == "https://api.digitalocean.com/v2/account/keys"
