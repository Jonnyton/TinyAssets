"""Forbid `patch()` / `setattr()` entered from inside a thread target.

`unittest.mock.patch` swaps a module attribute. That attribute is
process-global, not thread-local. When two threads enter the *same* patch, they
can interleave so that the second thread saves the first thread's mock as the
"original" value and restores that mock on exit — leaving it installed for the
remainder of the pytest process.

This is not a theoretical concern in this repo. One occurrence
(`tests/test_external_write_phase_2_atomicity.py`, fixed alongside this file)
patched `tinyassets.effectors.github_pr.subprocess.run` inside a thread worker.
Because that module does a plain `import subprocess`, the patch target *is* the
global `subprocess` module, so the leak replaced `subprocess.run` for every
later test in the process. Its canned stdout —
`https://github.com/x/x/pull/99` — was observed in CI as the output of
`subprocess.run` in roughly 70 unrelated tests across a dozen files (git
integration, packaging, invariants, release-reconcile, worktree status).

The visible cost: 111 quarantine-ledger entries flipped between two CI runs
whose trees differed by two test functions (#2197), because collection order
determined which tests ran while the mock was installed. That is what made the
suite look "order-dependent" and forced `scripts/ci_required_tests.py` to run
serially.

The fix is always the same shape: hoist the patch out of the worker and wrap
the whole concurrent section on the calling thread. That keeps the mock in
force for the threads while making install/restore single-threaded.
"""

from __future__ import annotations

import ast
from pathlib import Path

_TESTS = Path(__file__).resolve().parent

# Callables that mutate shared state on enter and restore it on exit. Entering
# one of these from more than one thread is the unsafe pattern.
_UNSAFE_IN_THREAD = {"patch", "setattr", "setenv", "delenv", "chdir"}


def _thread_target_names(tree: ast.Module) -> set[str]:
    """Function names handed to a thread/executor as the callable to run."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func_repr = ast.dump(node.func)
        if "Thread" in func_repr:
            for kw in node.keywords:
                if kw.arg == "target":
                    if isinstance(kw.value, ast.Name):
                        names.add(kw.value.id)
                    elif isinstance(kw.value, ast.Attribute):
                        names.add(kw.value.attr)
        # executor.submit(fn, ...) / executor.map(fn, ...)
        if isinstance(node.func, ast.Attribute) and node.func.attr in {
            "submit",
            "map",
        }:
            for arg in node.args:
                if isinstance(arg, ast.Name):
                    names.add(arg.id)
    return names


def _offenders(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return []
    targets = _thread_target_names(tree)
    if not targets:
        return []
    found: list[str] = []
    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if func.name not in targets:
            continue
        for sub in ast.walk(func):
            if not isinstance(sub, ast.Call):
                continue
            name = getattr(sub.func, "id", None) or getattr(
                sub.func, "attr", None
            )
            if name in _UNSAFE_IN_THREAD:
                found.append(
                    f"{path.name}:{sub.lineno} — {name}() inside thread target "
                    f"{func.name!r}"
                )
    return found


def test_no_patching_from_inside_a_thread_target() -> None:
    offenders: list[str] = []
    for path in sorted(_TESTS.rglob("test_*.py")):
        offenders.extend(_offenders(path))
    assert not offenders, (
        "patch()/setattr() must not be entered from inside a thread target — "
        "the swap is process-global, so two threads can interleave and leave "
        "the mock permanently installed, poisoning every later test in the "
        "process. Hoist it around the whole concurrent section instead:\n  "
        + "\n  ".join(offenders)
    )


def test_the_detector_can_actually_fire(tmp_path: Path) -> None:
    """Guard the guard: a scanner that never matches proves nothing."""
    sample = tmp_path / "test_sample.py"
    sample.write_text(
        "import threading\n"
        "from unittest.mock import patch\n"
        "def worker():\n"
        "    with patch('subprocess.run'):\n"
        "        pass\n"
        "def test_x():\n"
        "    t = threading.Thread(target=worker)\n"
        "    t.start(); t.join()\n",
        encoding="utf-8",
    )
    assert _offenders(sample), "detector failed to flag the known-bad pattern"

    safe = tmp_path / "test_safe.py"
    safe.write_text(
        "import threading\n"
        "from unittest.mock import patch\n"
        "def worker():\n"
        "    pass\n"
        "def test_x():\n"
        "    with patch('subprocess.run'):\n"
        "        t = threading.Thread(target=worker)\n"
        "        t.start(); t.join()\n",
        encoding="utf-8",
    )
    assert not _offenders(safe), "detector flagged the correct hoisted pattern"
