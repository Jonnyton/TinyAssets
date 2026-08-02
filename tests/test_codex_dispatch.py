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


def test_build_cmd_pipes_prompt_via_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    # The prompt must NEVER be an argv element: the codex.cmd shim goes through
    # cmd.exe, which truncates argv at the first newline (silent reviewed-nothing).
    monkeypatch.setattr(cr, "resolve_codex", lambda: "CODEXBIN")
    cmd = cr.build_cmd(_args())
    assert cmd[-1] == "-"
    assert cr.ADVERSARIAL_PREAMBLE not in " ".join(cmd)


def test_build_prompt_has_preamble_and_diff() -> None:
    plain = cr.build_prompt("ask", None)
    assert cr.ADVERSARIAL_PREAMBLE in plain
    assert "git diff" not in plain  # no diff instruction without --diff-base
    with_diff = cr.build_prompt("ask", "origin/main")
    assert "git diff origin/main...HEAD" in with_diff


# --- codex_dispatch_nudge ---------------------------------------------------


@pytest.mark.parametrize(
    "prompt,label",
    [
        ("let's ship this to production", "high-risk-ship"),
        ("ship it", "high-risk-ship"),
        ("ready to merge to main?", "high-risk-ship"),
        ("run the cross-family review gate on this", "cross-family-gate"),
        ("this is a research-derived finding", "cross-family-gate"),
        ("i'm stuck, it keeps failing with the same error", "stuck-loop"),
        ("can you get a second opinion on this?", "second-opinion"),
    ],
)
def test_nudge_fires_with_label(prompt: str, label: str) -> None:
    match = nudge.classify(prompt)
    assert match is not None
    assert match[0] == label


@pytest.mark.parametrize(
    "prompt",
    [
        "hello there",
        "add a docstring to this function",
        "",
        # Deliberately removed 2026-08-02 (de-bloat): routine review asks and
        # option-picking no longer nudge — only judgment-class moments do.
        "please review this finding for correctness",
        "which approach should we use, A or B?",
    ],
)
def test_nudge_silent_on_non_qualifying(prompt: str) -> None:
    assert nudge.classify(prompt) is None


def test_nudge_render_steers_to_background_offload() -> None:
    text = nudge.render("high-risk-ship", "refute it")
    assert "codex_review.py" in text  # the fail-closed wrapper, not raw exec
    assert "stdin" in text
    assert "BACKGROUND offload" in text
    assert "mcp__codex__codex" in text  # still names the inline gate option


def test_run_feeds_full_prompt_via_stdin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cr, "resolve_codex", lambda: "CODEXBIN")
    seen: dict = {}

    def fake(cmd, timeout=None, **kw):
        seen.update(kw)
        return subprocess_completed(0)

    monkeypatch.setattr(cr.subprocess, "run", fake)
    out = tmp_path / "verdict.md"
    cr.run(_run_args(out, prompt="line one\nline two"))
    assert "line one\nline two" in seen.get("input", "")
    assert cr.ADVERSARIAL_PREAMBLE in seen.get("input", "")


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

    def boom(cmd, timeout=None, **kw):
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
    def boom(cmd, timeout=None, **kw):
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
        cr.subprocess, "run", lambda cmd, timeout=None, **kw: subprocess_completed(0)
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

    def fake(cmd, timeout=None, **kw):
        out.write_text("findings...\nVERDICT: approve\n")
        return subprocess_completed(0)

    monkeypatch.setattr(cr.subprocess, "run", fake)
    assert cr.run(_run_args(out)) == 0
    assert out.read_text() == "findings...\nVERDICT: approve\n"


def test_run_nonzero_with_partial_output_appends_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, _fixed_bin
) -> None:
    out = tmp_path / "verdict.md"

    def fake(cmd, timeout=None, **kw):
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
