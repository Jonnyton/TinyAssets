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


def test_build_prompt_has_preamble_and_diff() -> None:
    plain = cr.build_prompt("ask", None, "n0", None)
    assert cr.ADVERSARIAL_PREAMBLE in plain
    assert "git diff" not in plain  # no diff instruction without --diff-base
    with_diff = cr.build_prompt("ask", "origin/main", "n0", None)
    assert "git diff origin/main...HEAD" in with_diff


def test_prompt_never_travels_through_argv(monkeypatch: pytest.MonkeyPatch) -> None:
    """The prompt goes over stdin, never argv.

    resolve_codex() lands on `codex.CMD` on Windows, so argv is parsed by cmd.exe,
    which truncates an argument at its first newline. The prompt is inherently
    multi-line (preamble + attribution + ask), so any argv-borne prompt silently
    loses everything after the preamble — that is how Codex came to reply "Which
    PR should I review?" to a fully-specified request.
    """
    monkeypatch.setattr(cr, "resolve_codex", lambda: "CODEXBIN")
    cmd = cr.build_cmd(_args(prompt="SENTINEL-ASK review foo.py"))
    assert cmd[-1] == "-", "codex must be told to read the prompt from stdin"
    assert not any("\n" in part for part in cmd), (
        "no argv element may contain a newline — cmd.exe truncates there"
    )
    assert not any("SENTINEL-ASK" in part for part in cmd)
    assert not any(cr.ADVERSARIAL_PREAMBLE in part for part in cmd)


# --- attribution: a verdict must be traceable to its request ----------------


def test_build_prompt_demands_exact_attribution_line() -> None:
    prompt = cr.build_prompt("ask", None, "cafe1234", "PR #1600")
    required = cr.attribution_line("cafe1234", "PR #1600")
    assert required in prompt
    assert "cafe1234" in required and "PR #1600" in required


def test_is_attributed_requires_whole_line_not_substring() -> None:
    required = cr.attribution_line("n1", "sha abc")
    assert cr.is_attributed(f"findings\n{required}\nVERDICT: approve", "n1", "sha abc")
    # Decoration a model might add around the line is tolerated...
    assert cr.is_attributed(f"**{required}**\nVERDICT: approve", "n1", "sha abc")
    # ...but a mere mention inside prose is not attribution.
    assert not cr.is_attributed(f"I was asked for {required} but declined", "n1", "sha abc")
    # A different request's nonce or target must not satisfy this request.
    assert not cr.is_attributed(f"{required}\nVERDICT: approve", "n2", "sha abc")
    assert not cr.is_attributed(f"{required}\nVERDICT: approve", "n1", "sha xyz")


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
    base = dict(
        prompt="ask",
        out=str(out),
        cwd=".",
        diff_base=None,
        timeout=5.0,
        target="PR #1600",
        nonce="feedface",
    )
    base.update(kw)
    return argparse.Namespace(**base)


def _attributed(args: argparse.Namespace, verdict: str = "approve") -> str:
    return f"{cr.attribution_line(args.nonce, args.target)}\nfindings\nVERDICT: {verdict}\n"


@pytest.fixture()
def _fixed_bin(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(cr, "resolve_codex", lambda: "CODEXBIN")


def test_run_timeout_writes_error_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, _fixed_bin
) -> None:
    import subprocess

    def boom(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd="codex", timeout=kw.get("timeout"))

    monkeypatch.setattr(cr.subprocess, "run", boom)
    out = tmp_path / "verdict.md"
    assert cr.run(_run_args(out)) == 124
    text = out.read_text()
    assert "VERDICT: error" in text
    assert "timed out" in text


def test_run_missing_binary_writes_error_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, _fixed_bin
) -> None:
    def boom(cmd, **kw):
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
        cr.subprocess, "run", lambda cmd, **kw: subprocess_completed(0)
    )
    out = tmp_path / "verdict.md"
    assert cr.run(_run_args(out)) == 0
    text = out.read_text()
    assert "VERDICT: error" in text
    assert "wrote no output" in text


def test_run_success_leaves_attributed_verdict_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, _fixed_bin
) -> None:
    out = tmp_path / "verdict.md"
    args = _run_args(out)
    body = _attributed(args)

    def fake(cmd, **kw):
        out.write_text(body, encoding="utf-8")
        return subprocess_completed(0)

    monkeypatch.setattr(cr.subprocess, "run", fake)
    assert cr.run(args) == 0
    assert out.read_text(encoding="utf-8") == body  # the gate can pass, not only fail


def test_run_sends_prompt_over_stdin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, _fixed_bin
) -> None:
    """The full ask must actually reach the CLI — the mode-2 regression."""
    out = tmp_path / "verdict.md"
    args = _run_args(out, prompt="SENTINEL-ASK audit the probe catalog")
    seen: dict = {}

    def fake(cmd, **kw):
        seen.update(kw)
        out.write_text(_attributed(args), encoding="utf-8")
        return subprocess_completed(0)

    monkeypatch.setattr(cr.subprocess, "run", fake)
    assert cr.run(args) == 0
    assert "SENTINEL-ASK audit the probe catalog" in seen["input"]
    assert cr.attribution_line(args.nonce, args.target) in seen["input"]


def test_run_does_not_return_a_stale_file_as_a_fresh_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, _fixed_bin
) -> None:
    """Mode 1: another lane's verdict must not be handed back as this lane's.

    codex can exit 0 having written nothing (documented v0.122+ auth-failure
    mode). If a previous review left a file at this --out path, the caller reads
    that file back and sees a confident `VERDICT: approve` for a PR it never
    asked about.
    """
    out = tmp_path / "verdict.md"
    out.write_text(
        "Reviewed PR #1537 (a different lane). Looks correct.\nVERDICT: approve\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(cr.subprocess, "run", lambda cmd, **kw: subprocess_completed(0))

    cr.run(_run_args(out))
    text = out.read_text(encoding="utf-8")
    assert "VERDICT: error" in text
    # The other lane's approval must not survive anywhere as a readable verdict.
    assert "VERDICT: approve" not in text
    assert "1537" not in text


def test_run_quarantines_a_verdict_from_a_different_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, _fixed_bin
) -> None:
    """A canned verdict body carrying ANOTHER request's attribution is rejected."""
    out = tmp_path / "verdict.md"
    args = _run_args(out, nonce="0000aaaa", target="PR #1600")
    foreign = (
        f"{cr.attribution_line('9999zzzz', 'PR #1537')}\n"
        "Reviewed the other lane.\nVERDICT: approve\n"
    )

    def fake(cmd, **kw):
        out.write_text(foreign, encoding="utf-8")
        return subprocess_completed(0)

    monkeypatch.setattr(cr.subprocess, "run", fake)
    assert cr.run(args) != 0
    text = out.read_text(encoding="utf-8")
    assert text.startswith("VERDICT: error")
    assert "0000aaaa" in text  # what was required, for the re-dispatch
    assert "| VERDICT: approve" in text  # evidence kept, but neutralised
    assert "\nVERDICT: approve" not in text


def test_run_refuses_an_empty_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, _fixed_bin
) -> None:
    """`--prompt ""` satisfies argparse but must not spend a Codex run."""
    out = tmp_path / "verdict.md"
    dispatched: list = []
    monkeypatch.setattr(cr.subprocess, "run", lambda cmd, **kw: dispatched.append(cmd))

    assert cr.run(_run_args(out, prompt="   \n  ")) == 2
    assert dispatched == []
    assert "VERDICT: error" in out.read_text(encoding="utf-8")


def test_run_quarantines_a_clarifying_question(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, _fixed_bin
) -> None:
    """The captured artifact: a question filed under a `-codex-review.md` name."""
    out = tmp_path / "verdict.md"

    def fake(cmd, **kw):
        out.write_text(
            "Which PR, branch, commit range, or worktree should I review?",
            encoding="utf-8",
        )
        return subprocess_completed(0)

    monkeypatch.setattr(cr.subprocess, "run", fake)
    assert cr.run(_run_args(out)) != 0
    assert "VERDICT: error" in out.read_text(encoding="utf-8")


def test_run_nonzero_with_partial_output_appends_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, _fixed_bin
) -> None:
    out = tmp_path / "verdict.md"

    def fake(cmd, **kw):
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
