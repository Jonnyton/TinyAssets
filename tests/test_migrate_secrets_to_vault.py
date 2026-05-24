"""Tests for scripts/migrate_secrets_to_vault.py.

Focus on pure-ish logic — parse_plaintext, migrate() decision matrix,
_read_keys. Vendor CLI subprocess calls are mocked via injectable
`runner` + `op_item_exists_fn` / `bw_item_id_fn` seams.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import migrate_secrets_to_vault as m  # noqa: E402

# ---- parse_plaintext ------------------------------------------------------


def test_parse_plaintext_basic():
    text = """
    # a comment
    KEY_A=value-a
    KEY_B=value-b

    # another
    KEY_C=value c with spaces
    """
    out = m.parse_plaintext(text)
    assert out == {
        "KEY_A": "value-a",
        "KEY_B": "value-b",
        "KEY_C": "value c with spaces",
    }


def test_parse_plaintext_strips_quotes():
    text = 'Q1="with double"\nQ2=\'with single\'\nQ3=no-quote'
    out = m.parse_plaintext(text)
    assert out == {"Q1": "with double", "Q2": "with single", "Q3": "no-quote"}


def test_parse_plaintext_preserves_mismatched_quotes():
    text = 'MIXED="left-only\nOTHER=\'right-only"'
    out = m.parse_plaintext(text)
    # mismatched quotes are preserved as literal chars.
    assert out["MIXED"] == '"left-only'
    assert out["OTHER"] == "'right-only\""


def test_parse_plaintext_later_wins_on_duplicate():
    out = m.parse_plaintext("K=first\nK=second\n")
    assert out == {"K": "second"}


def test_parse_plaintext_skips_malformed_lines():
    text = "GOOD=ok\nno-equals-here\n=missing-key\n"
    out = m.parse_plaintext(text)
    assert out == {"GOOD": "ok"}


def test_parse_plaintext_handles_empty_value():
    out = m.parse_plaintext("EMPTY=\nSET=x")
    assert out == {"EMPTY": "", "SET": "x"}


# ---- _read_keys -----------------------------------------------------------


def test_read_keys_happy(tmp_path):
    kf = tmp_path / "keys.txt"
    kf.write_text("# comment\nA\n\nB\n  # inline comment-ish\nC\n",
                  encoding="utf-8")
    assert m._read_keys(kf) == ["A", "B", "C"]


def test_read_keys_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        m._read_keys(tmp_path / "nope.txt")


def test_canonical_keys_include_github_push_token():
    assert "GH_TOKEN" in m._read_keys(_SCRIPTS / "secrets_keys.txt")


# ---- migrate() decision matrix --------------------------------------------


class _FakeRunner:
    """Records invocations + returns scripted exit codes."""

    def __init__(self, returncode: int = 0, stderr: str = "", stdout: str = ""):
        self.returncode = returncode
        self.stderr = stderr
        self.stdout = stdout
        self.calls: list[list[str]] = []

    def __call__(self, args, **kwargs):
        self.calls.append(args)
        # Return a CompletedProcess-shaped object the code expects.
        class _R:
            returncode = self.returncode
            stderr = self.stderr
            stdout = self.stdout
        return _R()


def test_migrate_dry_run_does_not_invoke_vendor():
    pairs = {"K1": "val1", "K2": "val2"}
    keys = ["K1", "K2"]
    runner = _FakeRunner()
    succ, fail = m.migrate(
        pairs, keys, "1password", "workflow", dry_run=True,
        runner=runner,
        op_item_exists_fn=lambda k, v: False,
        bw_item_id_fn=lambda k: None,
    )
    assert len(succ) == 2
    assert len(fail) == 0
    assert runner.calls == [], "dry-run must not invoke the vendor CLI"
    assert all("DRY-RUN" in msg for _, msg in succ)


def test_migrate_missing_key_in_plaintext_is_failure():
    pairs = {"K1": "val1"}
    keys = ["K1", "K2"]  # K2 missing
    runner = _FakeRunner()
    succ, fail = m.migrate(
        pairs, keys, "1password", "workflow", dry_run=True,
        runner=runner,
        op_item_exists_fn=lambda k, v: False,
        bw_item_id_fn=lambda k: None,
    )
    assert succ == [("K1", "DRY-RUN would write 4-char value")]
    assert fail == [("K2", "missing from plaintext file")]


def test_migrate_empty_value_is_failure():
    runner = _FakeRunner()
    succ, fail = m.migrate(
        {"K1": ""}, ["K1"], "1password", "workflow", dry_run=False,
        runner=runner,
        op_item_exists_fn=lambda k, v: False,
        bw_item_id_fn=lambda k: None,
    )
    assert fail == [("K1", "empty value in plaintext file")]
    assert runner.calls == []


def test_migrate_1password_create_vs_edit():
    """When item doesn't exist → `op item create`. When it exists → `op item edit`."""
    runner = _FakeRunner(returncode=0)
    exists_map = {"EXISTING_KEY": True, "NEW_KEY": False}
    succ, fail = m.migrate(
        {"EXISTING_KEY": "v1", "NEW_KEY": "v2"},
        ["EXISTING_KEY", "NEW_KEY"],
        "1password", "workflow", dry_run=False,
        runner=runner,
        op_item_exists_fn=lambda k, v: exists_map[k],
        bw_item_id_fn=lambda k: None,
    )
    assert len(succ) == 2
    assert len(fail) == 0
    # First call should be `op item edit EXISTING_KEY ...`
    assert runner.calls[0][:4] == ["op", "item", "edit", "EXISTING_KEY"]
    # Second call should be `op item create`.
    assert runner.calls[1][:3] == ["op", "item", "create"]
    assert "--title" in runner.calls[1]
    assert "NEW_KEY" in runner.calls[1]


def test_migrate_1password_cli_failure_reports():
    runner = _FakeRunner(returncode=1, stderr="op: not signed in")
    succ, fail = m.migrate(
        {"K": "v"}, ["K"], "1password", "workflow", dry_run=False,
        runner=runner,
        op_item_exists_fn=lambda k, v: False,
        bw_item_id_fn=lambda k: None,
    )
    assert succ == []
    assert len(fail) == 1
    assert "op exit 1" in fail[0][1]
    assert "not signed in" in fail[0][1]


def test_migrate_bitwarden_calls_encode_then_edit_or_create():
    """Bitwarden writes need `bw encode` + then `bw create/edit item <encoded>`."""
    # Each key generates 2 runner calls: encode + create/edit.
    encoded_stdout = "eyJmYWtlIjogInBheWxvYWQifQ=="  # fake base64

    class _SequencedRunner:
        def __init__(self):
            self.calls = []

        def __call__(self, args, **kwargs):
            self.calls.append(args)

            class _R:
                pass

            if args[:2] == ["bw", "encode"]:
                _R.returncode = 0
                _R.stdout = encoded_stdout
                _R.stderr = ""
            else:
                _R.returncode = 0
                _R.stdout = ""
                _R.stderr = ""
            return _R()

    runner = _SequencedRunner()
    succ, fail = m.migrate(
        {"NEW_KEY": "v1", "EXIST_KEY": "v2"},
        ["NEW_KEY", "EXIST_KEY"],
        "bitwarden", "workflow", dry_run=False,
        runner=runner,
        op_item_exists_fn=lambda k, v: False,
        bw_item_id_fn=lambda k: "abc-123" if k == "EXIST_KEY" else None,
    )
    assert len(succ) == 2
    assert len(fail) == 0
    # Expect 4 calls total: encode + create, encode + edit.
    assert len(runner.calls) == 4
    assert runner.calls[0][:2] == ["bw", "encode"]
    assert runner.calls[1][:3] == ["bw", "create", "item"]
    assert runner.calls[2][:2] == ["bw", "encode"]
    assert runner.calls[3][:3] == ["bw", "edit", "item"]
    assert "abc-123" in runner.calls[3]


def test_migrate_unsupported_vendor_fails_all():
    runner = _FakeRunner()
    succ, fail = m.migrate(
        {"K": "v"}, ["K"], "keychain", "whatever", dry_run=False,
        runner=runner,
        op_item_exists_fn=lambda k, v: False,
        bw_item_id_fn=lambda k: None,
    )
    assert succ == []
    assert len(fail) == 1
    assert "unsupported vendor" in fail[0][1]


# ---- main() integration with mocks ---------------------------------------


def _fake_cli_ok_env(monkeypatch):
    """Monkey-patch all 4 vendor-availability probes to green."""
    monkeypatch.setattr(m, "_op_available", lambda: True)
    monkeypatch.setattr(m, "_op_signed_in", lambda: True)
    monkeypatch.setattr(m, "_bw_available", lambda: True)
    monkeypatch.setattr(m, "_bw_unlocked", lambda: True)


def test_main_returns_2_when_plaintext_missing(tmp_path, monkeypatch, capsys):
    nonexistent = tmp_path / "nope.env"
    rc = m.main(["--plaintext", str(nonexistent), "--vendor", "1password",
                 "--dry-run"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "not readable" in err


def test_main_returns_3_when_keys_config_missing(tmp_path, monkeypatch, capsys):
    pt = tmp_path / "pt.env"
    pt.write_text("K=v\n", encoding="utf-8")
    rc = m.main([
        "--plaintext", str(pt),
        "--vendor", "1password",
        "--keys-file", str(tmp_path / "nope.txt"),
        "--dry-run",
    ])
    assert rc == 3


def test_main_returns_4_when_op_cli_missing(tmp_path, monkeypatch, capsys):
    pt = tmp_path / "pt.env"
    pt.write_text("K=v\n", encoding="utf-8")
    kf = tmp_path / "keys.txt"
    kf.write_text("K\n", encoding="utf-8")
    monkeypatch.setattr(m, "_op_available", lambda: False)
    rc = m.main(["--plaintext", str(pt), "--vendor", "1password",
                 "--keys-file", str(kf)])
    assert rc == 4


def test_main_returns_5_when_op_not_signed_in(tmp_path, monkeypatch):
    pt = tmp_path / "pt.env"
    pt.write_text("K=v\n", encoding="utf-8")
    kf = tmp_path / "keys.txt"
    kf.write_text("K\n", encoding="utf-8")
    monkeypatch.setattr(m, "_op_available", lambda: True)
    monkeypatch.setattr(m, "_op_signed_in", lambda: False)
    rc = m.main(["--plaintext", str(pt), "--vendor", "1password",
                 "--keys-file", str(kf)])
    assert rc == 5


def test_main_returns_0_on_happy_dry_run(tmp_path):
    pt = tmp_path / "pt.env"
    pt.write_text("K1=v1\nK2=v2\n", encoding="utf-8")
    kf = tmp_path / "keys.txt"
    kf.write_text("K1\nK2\n", encoding="utf-8")
    rc = m.main(["--plaintext", str(pt), "--vendor", "1password",
                 "--keys-file", str(kf), "--dry-run"])
    assert rc == 0


def test_main_returns_6_when_any_key_missing_in_plaintext(tmp_path):
    pt = tmp_path / "pt.env"
    pt.write_text("K1=v1\n", encoding="utf-8")
    kf = tmp_path / "keys.txt"
    kf.write_text("K1\nK2_MISSING\n", encoding="utf-8")
    rc = m.main(["--plaintext", str(pt), "--vendor", "1password",
                 "--keys-file", str(kf), "--dry-run"])
    assert rc == 6
