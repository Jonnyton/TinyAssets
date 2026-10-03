"""Tests for `.claude/hooks/fuse_write_truncation_guard.py`.

Regression origin (2026-08-07): the guard fired 458 non-blocking errors in four
days — essentially every Edit and Write — on a native Windows checkout where
FUSE is not involved at all. Two independent causes, both line-ending related:

* Edit path: the file is read in text mode (folding CRLF to LF) but `new_string`
  was compared raw, so any CRLF-bearing payload mismatched at its first newline.
  The real-world symptom was "only first 36 chars survive" — 36 being the length
  of the first line.
* Write path: content sent with LF that lands on disk as CRLF drifts one byte
  per line, which no fixed `TOLERANCE_BYTES` budget can absorb.

Both directions are asserted here on purpose: the CRLF cases must come back
clean, and genuine truncation must still be caught. A test that only pinned the
"clean" direction would pass against a guard that never fires at all.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = (
    Path(__file__).resolve().parents[1]
    / ".claude"
    / "hooks"
    / "fuse_write_truncation_guard.py"
)

CLEAN = 0
TRUNCATED = 2


def run_hook(tool: str, tool_input: dict, *, on_fuse: bool = True) -> tuple[int, str]:
    """Invoke the guard. `on_fuse` forces the FUSE-only checks on/off.

    The guard no-ops off FUSE, so almost every test here forces it ON; that is
    the branch with logic worth pinning. `test_no_op_off_fuse` covers the other.
    """
    env = dict(os.environ)
    if on_fuse:
        env["TINYASSETS_FUSE_GUARD_FORCE"] = "1"
    else:
        env.pop("TINYASSETS_FUSE_GUARD_FORCE", None)
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps({"tool_name": tool, "tool_input": tool_input}),
        capture_output=True,
        text=True,
        env=env,
    )
    return proc.returncode, proc.stderr


def write_bytes(path: Path, lines: list[str], eol: str) -> None:
    path.write_bytes(eol.join(lines).encode("utf-8"))


LINES = [
    "# Heading here that is long enough to matter",
    "second line of the document",
    "third line of the document",
    "",
]


def test_hook_exists() -> None:
    assert HOOK.is_file(), f"guard hook missing at {HOOK}"


# --- Edit path -------------------------------------------------------------


@pytest.mark.parametrize("disk_eol", ["\r\n", "\n"])
@pytest.mark.parametrize("payload_eol", ["\r\n", "\n"])
def test_edit_line_endings_never_read_as_truncation(
    tmp_path: Path, disk_eol: str, payload_eol: str
) -> None:
    """A correct edit is clean in all four CRLF/LF combinations."""
    target = tmp_path / "doc.md"
    write_bytes(target, LINES, disk_eol)
    new_string = payload_eol.join(LINES[:2])

    rc, err = run_hook("Edit", {"file_path": str(target), "new_string": new_string})

    assert rc == CLEAN, (
        f"false positive with disk={disk_eol!r} payload={payload_eol!r}: {err}"
    )


def test_edit_real_truncation_is_still_caught(tmp_path: Path) -> None:
    """The guard must still fire when the tail genuinely did not land."""
    target = tmp_path / "doc.md"
    write_bytes(target, LINES, "\r\n")
    # Only the first line is on disk; the payload claims far more.
    target.write_bytes(LINES[0].encode("utf-8"))
    new_string = "\r\n".join(LINES[:3])

    rc, err = run_hook("Edit", {"file_path": str(target), "new_string": new_string})

    assert rc == TRUNCATED, "genuine truncation went undetected"
    assert "FUSE_WRITE_TRUNCATION_GUARD" in err


def test_edit_missing_file_is_not_a_truncation(tmp_path: Path) -> None:
    rc, _ = run_hook(
        "Edit", {"file_path": str(tmp_path / "nope.md"), "new_string": "anything"}
    )
    assert rc == CLEAN


# --- Write path ------------------------------------------------------------


def test_write_crlf_drift_scales_past_tolerance_but_is_clean(tmp_path: Path) -> None:
    """200 lines drift 199 bytes LF->CRLF — well past any fixed byte tolerance."""
    target = tmp_path / "big.md"
    big = [f"line {i} of a reasonably long document" for i in range(200)]
    write_bytes(target, big, "\r\n")
    sent = "\n".join(big)

    rc, err = run_hook("Write", {"file_path": str(target), "content": sent})

    assert rc == CLEAN, f"CRLF drift misread as truncation: {err}"


def test_write_real_truncation_is_still_caught(tmp_path: Path) -> None:
    target = tmp_path / "big.md"
    big = [f"line {i} of a reasonably long document" for i in range(200)]
    sent = "\n".join(big)
    # Only a fraction of the content actually landed.
    target.write_bytes("\n".join(big[:20]).encode("utf-8"))

    rc, err = run_hook("Write", {"file_path": str(target), "content": sent})

    assert rc == TRUNCATED, "genuine write truncation went undetected"
    assert "FUSE_WRITE_TRUNCATION_GUARD" in err


def test_write_exact_content_is_clean(tmp_path: Path) -> None:
    target = tmp_path / "doc.md"
    sent = "\n".join(LINES)
    target.write_bytes(sent.encode("utf-8"))

    rc, err = run_hook("Write", {"file_path": str(target), "content": sent})

    assert rc == CLEAN, err


def test_write_crlf_payload_onto_lf_disk_is_clean(tmp_path: Path) -> None:
    """The reverse direction of the drift test: CRLF payload, LF on disk."""
    target = tmp_path / "doc.md"
    big = [f"line {i} of a reasonably long document" for i in range(200)]
    write_bytes(target, big, "\n")

    rc, err = run_hook("Write", {"file_path": str(target), "content": "\r\n".join(big)})

    assert rc == CLEAN, err


def test_write_lone_cr_endings_are_clean(tmp_path: Path) -> None:
    target = tmp_path / "doc.md"
    write_bytes(target, LINES, "\r")

    rc, err = run_hook("Write", {"file_path": str(target), "content": "\n".join(LINES)})

    assert rc == CLEAN, err


def test_write_utf8_bom_on_disk_is_clean(tmp_path: Path) -> None:
    target = tmp_path / "doc.md"
    sent = "\n".join(LINES)
    target.write_bytes(b"\xef\xbb\xbf" + sent.encode("utf-8"))

    rc, err = run_hook("Write", {"file_path": str(target), "content": sent})

    assert rc == CLEAN, err


# --- Counterexamples from the 2026-08-07 cross-family review -----------------
# Both of these passed as "clean" against the first attempt at the CRLF fix.


def test_write_whole_lines_lost_is_caught_despite_crlf_normalization(
    tmp_path: Path,
) -> None:
    """16 complete CRLF lines lost must not hide inside the tolerance.

    Raw delta 48 bytes, normalized delta 32 — exactly the old TOLERANCE_BYTES.
    """
    target = tmp_path / "doc.md"
    target.write_bytes(b"HEAD")
    payload = "HEAD" + "x\r\n" * 16

    rc, err = run_hook("Write", {"file_path": str(target), "content": payload})

    assert rc == TRUNCATED, "16 lost lines were waved through as within tolerance"
    assert "FUSE_WRITE_TRUNCATION_GUARD" in err


def test_write_truncation_midway_through_multibyte_char_is_caught(
    tmp_path: Path,
) -> None:
    """Measuring via errors='replace' re-encoding shrank this delta below tolerance."""
    target = tmp_path / "doc.md"
    payload = "A" * 100 + "\U0001f600" * 8  # 132 bytes
    target.write_bytes(payload.encode("utf-8")[:101])  # cut 1 byte into an emoji

    rc, err = run_hook("Write", {"file_path": str(target), "content": payload})

    assert rc == TRUNCATED, "multibyte-boundary truncation went undetected"
    assert "FUSE_WRITE_TRUNCATION_GUARD" in err


def test_write_undecodable_disk_bytes_are_measured_raw(tmp_path: Path) -> None:
    """Undecodable bytes must be counted as-is, never decoded and re-encoded.

    Decoding 100 invalid bytes with errors="replace" and re-encoding yields 300
    (each byte becomes a 3-byte U+FFFD), a 3x inflation that fabricates numbers.
    The content here genuinely differs from what was sent, so alerting is right —
    what is asserted is that the REPORTED sizes are the true 100/100.
    """
    target = tmp_path / "doc.bin"
    target.write_bytes(bytes([0xFF]) * 100)

    rc, err = run_hook(
        "Write", {"file_path": str(target), "content": "ÿ" * 50}
    )  # 100 bytes as UTF-8

    assert rc == TRUNCATED
    assert "sent 100 bytes, 100 on disk" in err, f"sizes were distorted: {err}"
    assert "300" not in err, f"errors='replace' inflation leaked into the report: {err}"


def test_write_two_byte_shortfall_is_caught(tmp_path: Path) -> None:
    target = tmp_path / "doc.md"
    target.write_bytes(b"A" * 98)

    rc, _ = run_hook("Write", {"file_path": str(target), "content": "A" * 100})

    assert rc == TRUNCATED


def test_write_single_byte_loss_is_caught(tmp_path: Path) -> None:
    """Negative control: a one-byte loss is real truncation, not slack.

    The interim "TOLERANCE_BYTES = 1" design forgave exactly this.
    """
    target = tmp_path / "doc.md"
    target.write_bytes(b"A")

    rc, _ = run_hook("Write", {"file_path": str(target), "content": "AB"})

    assert rc == TRUNCATED


def test_write_stale_suffix_left_behind_is_caught(tmp_path: Path) -> None:
    """A partial overwrite can leave old bytes, making the file LONGER but corrupt.

    Any directional "disk is not shorter, so it's fine" shortcut misses this.
    """
    target = tmp_path / "doc.md"
    target.write_bytes(b"ABYZQQ")

    rc, err = run_hook("Write", {"file_path": str(target), "content": "ABCD"})

    assert rc == TRUNCATED, "stale-suffix corruption went undetected"
    assert "differs" in err


def test_write_newline_only_loss_is_caught(tmp_path: Path) -> None:
    """A lost tail made entirely of newlines is still lost content."""
    target = tmp_path / "doc.md"
    target.write_bytes(b"abc")

    rc, _ = run_hook("Write", {"file_path": str(target), "content": "abc\n\n"})

    assert rc == TRUNCATED, "newline-only truncation was forgiven"


def test_write_empty_payload_against_nonempty_disk_is_caught(tmp_path: Path) -> None:
    target = tmp_path / "doc.md"
    target.write_bytes(b"X")

    rc, _ = run_hook("Write", {"file_path": str(target), "content": ""})

    assert rc == TRUNCATED


# --- Scoping: the guard only runs where the failure mode exists --------------


def test_no_op_off_fuse(tmp_path: Path) -> None:
    """Off a FUSE mount the guard must stay silent even on blatant truncation.

    This is the branch that ended the 458-errors-in-four-days flood on a native
    Windows checkout, where FUSE truncation cannot happen at all.
    """
    target = tmp_path / "doc.md"
    target.write_bytes(b"A")

    rc, err = run_hook(
        "Write", {"file_path": str(target), "content": "A" * 5000}, on_fuse=False
    )

    assert rc == CLEAN, "guard fired off-FUSE, where the bug cannot occur"
    assert err.strip() == "", f"guard emitted output off-FUSE: {err}"


def test_same_case_is_caught_on_fuse(tmp_path: Path) -> None:
    """Control for the test above: identical input DOES alert when on FUSE.

    Without this pair, `test_no_op_off_fuse` would also pass against a guard
    that never fires under any circumstances.
    """
    target = tmp_path / "doc.md"
    target.write_bytes(b"A")

    rc, _ = run_hook(
        "Write", {"file_path": str(target), "content": "A" * 5000}, on_fuse=True
    )

    assert rc == TRUNCATED


def test_edit_leading_bom_in_new_string_is_content_not_signature(
    tmp_path: Path,
) -> None:
    """A U+FEFF starting `new_string` is mid-file content and must not be stripped.

    Stripping it would accept a file missing a character the edit meant to insert.
    """
    target = tmp_path / "doc.md"
    target.write_bytes(b"prefix\nABC\n")
    new_string = "﻿ABC"

    rc, _ = run_hook("Edit", {"file_path": str(target), "new_string": new_string})

    assert rc == TRUNCATED, "BOM-as-content was silently accepted as absent"


def test_edit_crlf_boundary_truncation_is_caught(tmp_path: Path) -> None:
    """A CRLF payload whose tail is missing must still alert after normalization."""
    target = tmp_path / "doc.md"
    target.write_bytes(b"HEAD\r\nkept line\r\n")
    new_string = "HEAD\r\nkept line\r\n" + "tail line\r\n" * 5

    rc, err = run_hook("Edit", {"file_path": str(target), "new_string": new_string})

    assert rc == TRUNCATED, "CRLF tail loss went undetected"
    assert "bytes survive" in err


def test_malformed_payload_is_ignored() -> None:
    proc = subprocess.run(
        [sys.executable, str(HOOK)], input="not json", capture_output=True, text=True
    )
    assert proc.returncode == CLEAN


# --- The mount classifier itself --------------------------------------------
# Forcing TINYASSETS_FUSE_GUARD_FORCE exercises the override, never the
# classifier. Without these, a `_is_fuse_path` that returned False for every
# real mount on earth would still pass the whole suite above.


def load_guard():
    spec = importlib.util.spec_from_file_location("fuse_guard", HOOK)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


PROC_MOUNTS = (
    "/dev/sda1 / ext4 rw,relatime 0 0\n"
    "tmpfs /tmp tmpfs rw 0 0\n"
    "cowork /sessions/abc/mnt fuse.cowork rw,nosuid 0 0\n"
    "spaced /mnt/my\\040drive fuse.sshfs rw 0 0\n"
    "/dev/sdb1 /sessions/abc/mnt/nested ext4 rw 0 0\n"
)


@pytest.mark.parametrize(
    "path,expected",
    [
        ("/sessions/abc/mnt/docs/file.md", True),  # under a fuse mount
        ("/sessions/abc/mnt", True),  # the mount point itself
        ("/home/u/repo/file.md", False),  # plain ext4 root
        ("/tmp/scratch.md", False),  # tmpfs
        ("/mnt/my drive/file.md", True),  # octal-escaped mount point
        ("/sessions/abc/mnt/nested/f.md", False),  # longest match wins: ext4
    ],
)
def test_is_fuse_path_classifies_linux_mounts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, path: str, expected: bool
) -> None:
    mod = load_guard()
    fake = tmp_path / "mounts"
    fake.write_text(PROC_MOUNTS, encoding="utf-8")

    real_open = open

    def fake_open(name, *a, **kw):
        if name == "/proc/mounts":
            return real_open(fake, *a, **kw)
        return real_open(name, *a, **kw)

    monkeypatch.setattr(mod, "sys", type("S", (), {"platform": "linux"}))
    monkeypatch.setattr(mod.os.path, "realpath", lambda p: p)
    monkeypatch.setattr(mod.os.environ, "get", lambda *a: None)
    monkeypatch.setitem(mod.__builtins__, "open", fake_open)

    assert mod._is_fuse_path(path) is expected


def test_is_fuse_path_is_false_on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    """Windows has no FUSE mount type — this is what silenced the 458 alarms."""
    mod = load_guard()
    monkeypatch.setattr(mod, "sys", type("S", (), {"platform": "win32"}))
    monkeypatch.setattr(mod.os.environ, "get", lambda *a: None)

    assert mod._is_fuse_path("C:/Users/x/repo/file.md") is False


def test_force_env_overrides_classification(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = load_guard()
    monkeypatch.setenv("TINYASSETS_FUSE_GUARD_FORCE", "1")

    assert mod._is_fuse_path("C:/anything") is True


def test_unescape_mount_decodes_octal() -> None:
    mod = load_guard()
    assert mod._unescape_mount("/mnt/my\\040drive") == "/mnt/my drive"
    assert mod._unescape_mount("/plain/path") == "/plain/path"
    assert mod._unescape_mount("/tab\\011here") == "/tab\there"
