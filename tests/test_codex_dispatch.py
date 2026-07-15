"""Tests for the programmatic Codex dispatch layer.

Covers the wrapper `scripts/codex_review.py` (Windows/PATH resolution, MSYS path
normalization, and the safe `codex exec` command it builds) and the
`.claude/hooks/codex_dispatch_nudge.py` UserPromptSubmit nudge. Both are loaded
by path since they live outside the importable package tree.
"""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(rel: str):
    path = ROOT / rel
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cr = _load("scripts/codex_review.py")
nudge = _load(".claude/hooks/codex_dispatch_nudge.py")


# --- to_native_path ---------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("/c/foo/bar", "C:/foo/bar"),
        ("/d/x", "D:/x"),
        ("/c/", "C:/"),
        ("C:/already/native", "C:/already/native"),
        (".", "."),
        ("relative/path", "relative/path"),
        ("/home/user", "/home/user"),  # not a single-letter drive -> unchanged
    ],
)
def test_to_native_path(raw: str, expected: str) -> None:
    assert cr.to_native_path(raw) == expected


# --- resolve_codex ----------------------------------------------------------


def test_resolve_codex_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = tmp_path / "codex.cmd"
    fake.write_text("echo")
    monkeypatch.setenv("CODEX_BIN", str(fake))
    assert cr.resolve_codex() == str(fake)


def test_resolve_codex_ignores_missing_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODEX_BIN", "/does/not/exist/codex")
    # Falls through to PATH / known-dir logic; never returns the bad override.
    assert cr.resolve_codex() != "/does/not/exist/codex"


# --- build_cmd --------------------------------------------------------------


def _args(**kw) -> argparse.Namespace:
    base = dict(prompt="ask", out="C:/o.md", cwd="C:/repo", diff_base=None)
    base.update(kw)
    return argparse.Namespace(**base)


def test_build_cmd_is_read_only_and_no_approval(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cr, "resolve_codex", lambda: "CODEXBIN")
    cmd = cr.build_cmd(_args())
    assert cmd[0] == "CODEXBIN"
    assert cmd[1] == "exec"
    assert cmd[cmd.index("-s") + 1] == "read-only"
    assert cmd[cmd.index("-c") + 1] == "approval_policy=never"
    # write access is never granted from this path
    assert "workspace-write" not in cmd
    assert "danger-full-access" not in cmd
    assert "--dangerously-bypass-approvals-and-sandbox" not in cmd


def test_build_cmd_passes_cwd_and_out(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cr, "resolve_codex", lambda: "CODEXBIN")
    cmd = cr.build_cmd(_args(cwd="C:/repo", out="C:/verdict.md"))
    assert cmd[cmd.index("-C") + 1] == "C:/repo"
    assert cmd[cmd.index("-o") + 1] == "C:/verdict.md"


def test_build_cmd_prompt_has_preamble_and_diff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cr, "resolve_codex", lambda: "CODEXBIN")
    plain = cr.build_cmd(_args())[-1]
    assert cr.ADVERSARIAL_PREAMBLE in plain
    assert "git diff" not in plain  # no diff instruction without --diff-base
    with_diff = cr.build_cmd(_args(diff_base="origin/main"))[-1]
    assert "git diff origin/main...HEAD" in with_diff


# --- codex_dispatch_nudge ---------------------------------------------------


@pytest.mark.parametrize(
    "prompt,label",
    [
        ("please review this finding for correctness", "review/finding"),
        ("let's ship this to production", "risky/ship"),
        ("which approach should we use, A or B?", "decision/recommend"),
        ("i'm stuck, it keeps failing with the same error", "stuck-loop"),
    ],
)
def test_nudge_fires_with_label(prompt: str, label: str) -> None:
    match = nudge.classify(prompt)
    assert match is not None
    assert match[0] == label


@pytest.mark.parametrize("prompt", ["hello there", "add a docstring to this function", ""])
def test_nudge_silent_on_non_qualifying(prompt: str) -> None:
    assert nudge.classify(prompt) is None


def test_nudge_render_steers_to_background_offload() -> None:
    text = nudge.render("review/finding", "do the review")
    assert "codex_review.py" in text
    assert "BACKGROUND offload" in text
    assert "mcp__codex__codex" in text  # still names the inline gate option


# --- run(): background contract — the out file always exists ----------------


def _run_args(out: Path, **kw) -> argparse.Namespace:
    base = dict(prompt="ask", out=str(out), cwd=".", diff_base=None, timeout=5.0)
    base.update(kw)
    return argparse.Namespace(**base)


@pytest.fixture()
def _fixed_bin(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(cr, "resolve_codex", lambda: "CODEXBIN")


def test_run_timeout_writes_error_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, _fixed_bin
) -> None:
    import subprocess

    def boom(cmd, timeout=None):
        raise subprocess.TimeoutExpired(cmd="codex", timeout=timeout)

    monkeypatch.setattr(cr.subprocess, "run", boom)
    out = tmp_path / "verdict.md"
    assert cr.run(_run_args(out)) == 124
    text = out.read_text()
    assert "VERDICT: error" in text
    assert "timed out" in text


def test_run_missing_binary_writes_error_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, _fixed_bin
) -> None:
    def boom(cmd, timeout=None):
        raise FileNotFoundError(cmd[0])

    monkeypatch.setattr(cr.subprocess, "run", boom)
    out = tmp_path / "verdict.md"
    assert cr.run(_run_args(out)) == 127
    text = out.read_text()
    assert "VERDICT: error" in text
    assert "CODEX_BIN" in text


def test_run_zero_exit_empty_output_writes_error_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, _fixed_bin
) -> None:
    # codex exec "succeeds" but never writes the file: a silent poller trap.
    monkeypatch.setattr(
        cr.subprocess, "run", lambda cmd, timeout=None: subprocess_completed(0)
    )
    out = tmp_path / "verdict.md"
    assert cr.run(_run_args(out)) == 0
    text = out.read_text()
    assert "VERDICT: error" in text
    assert "wrote no output" in text


def test_run_success_leaves_codex_verdict_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, _fixed_bin
) -> None:
    out = tmp_path / "verdict.md"

    def fake(cmd, timeout=None):
        out.write_text("findings...\nVERDICT: approve\n")
        return subprocess_completed(0)

    monkeypatch.setattr(cr.subprocess, "run", fake)
    assert cr.run(_run_args(out)) == 0
    assert out.read_text() == "findings...\nVERDICT: approve\n"


def test_run_nonzero_with_partial_output_appends_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, _fixed_bin
) -> None:
    out = tmp_path / "verdict.md"

    def fake(cmd, timeout=None):
        out.write_text("partial findings\n")
        return subprocess_completed(3)

    monkeypatch.setattr(cr.subprocess, "run", fake)
    assert cr.run(_run_args(out)) == 3
    text = out.read_text()
    assert text.startswith("partial findings")  # partial output preserved
    assert "WARNING" in text
    assert "exited 3" in text


def subprocess_completed(rc: int):
    import subprocess

    return subprocess.CompletedProcess(args=["codex"], returncode=rc)
