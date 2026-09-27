"""Tests for the programmatic Codex dispatch layer.

Covers `scripts/peer_agent.py` (Windows/PATH resolution, MSYS path
normalization, and the safe `codex exec` command it builds). Loaded by path
since it lives outside the importable package tree.
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
