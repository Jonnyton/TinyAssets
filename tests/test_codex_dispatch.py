"""Tests for the programmatic Codex dispatch layer.

Covers `scripts/peer_agent.py` (Windows/PATH resolution, MSYS path
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


cr = _load("scripts/peer_agent.py")
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


def _run_args(out: Path, **kw) -> argparse.Namespace:
    base = dict(prompt="ask", out=str(out), cwd=".", diff_base=None, timeout=5.0)
    base.update(kw)
    return argparse.Namespace(**base)


@pytest.fixture()
def _fixed_bin(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(cr, "resolve_codex", lambda: "CODEXBIN")


def subprocess_completed(rc: int):
    import subprocess

    return subprocess.CompletedProcess(args=["codex"], returncode=rc)


# --- The nudge's rendered command must actually be runnable ------------------
#
# `test_nudge_render_steers_to_background_offload` was DELETED with
# `codex_review.py` rather than retargeted, leaving only classification
# coverage. That is how the hook shipped a command argparse rejects
# (`peer_agent.py --out ...` with no positional provider) in the first place:
# nothing asserted the rendered text. Restored against the current wrapper, and
# the command is parsed rather than string-matched, so a shape error fails here
# instead of at the moment an agent tries to run it.
# (Cross-family review of PR #2561, round 5.)


def test_nudge_render_names_the_wrapper_and_the_inline_gate() -> None:
    text = nudge.render("high-risk-ship", "refute it")
    assert "peer_agent.py" in text
    assert "codex_review.py" not in text, "names the deleted wrapper"
    assert "BACKGROUND offload" in text
    assert "stdin" in text, "the argv-truncation warning must survive"
    assert "mcp__codex__codex" in text, "still names the inline gate option"
    assert "[peer_agent] ERROR" in text, "the fail-closed marker must be named"


def test_nudge_rendered_command_parses() -> None:
    """Feed the rendered command to peer_agent's OWN parser.

    Checking flag PRESENCE is not parsing: `--out --prompt-file` with no values
    passes a membership test and argparse rejects it (cross-family review of
    PR #2561, round 6, mutation-proven). The parser is the only thing that
    agrees with what actually runs, so `build_arg_parser()` was extracted from
    `main()` and is used here. Angle-bracket placeholders become syntactically
    valid values, since the SHAPE is under test, not the paths.
    """
    import re
    import shlex

    text = nudge.render("high-risk-ship", "refute it")
    match = re.search(r"`(python scripts/peer_agent\.py[^`]*)`", text)
    assert match, f"no runnable peer_agent command in:\n{text}"

    tokens = shlex.split(match.group(1))
    assert tokens[:2] == ["python", "scripts/peer_agent.py"], tokens
    argv = [
        "brief.md" if t.startswith("<") and t.endswith(">") else t for t in tokens[2:]
    ]

    try:
        args = cr.build_arg_parser().parse_args(argv)
    except SystemExit as exc:  # argparse exits rather than raising
        raise AssertionError(
            f"the nudge renders a command argparse rejects: {argv} ({exc})"
        ) from exc

    assert args.provider in {"claude", "codex"}, args
    assert args.out and not args.out.startswith("-"), f"--out took a flag as its value: {args}"
    assert args.prompt or args.prompt_file, f"no prompt source survived parsing: {args}"
