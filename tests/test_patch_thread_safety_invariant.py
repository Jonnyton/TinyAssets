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
determined which tests ran while the mock was installed.

**Scope of that claim, stated precisely.** This mechanism explains the measured
URL-poisoning and the 111-entry flip; it is *not* established that it was the
suite's only isolation defect, or that removing it makes the suite
order-independent enough to restore xdist. Those are separate questions,
answered by running the suite, not by this file.

The fix is always the same shape: hoist the patch out of the worker and wrap
the whole concurrent section on the calling thread. That keeps the mock in
force for the threads while making install/restore single-threaded — and the
hoisted version must then assert the workers actually finished before the patch
is dropped, which a per-worker patch got for free.

**What this detector is.** A lint over the common spellings, not a proof. It
resolves `Thread(target=…)` (keyword and positional), `functools.partial`
targets, inline `lambda` targets, `submit`/`map`/`apply_async` on a pool that is
not a `ProcessPoolExecutor` (a separate process cannot leak into this one), and
`patch` under an import alias, `patch.object`, or `mock.patch`. It does **not**
follow indirection — a thread target that calls a helper which patches is not
detected — and it cannot resolve dynamically-built callables. Treat a green
result as "the obvious spellings are absent", not "the pattern is impossible".
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_TESTS = Path(__file__).resolve().parent

# Callables that mutate PROCESS-GLOBAL state on enter and restore it on exit.
# Entering one from more than one thread is the unsafe pattern.
#
# Two separate shapes, deliberately not merged into one name set:
#
#   * bare `patch(...)` / `mock.patch(...)` / `mock.patch.object(...)`
#   * `monkeypatch.<verb>(...)` — pytest's fixture, equally process-global
#
# `setattr` etc. are matched ONLY on a `monkeypatch` receiver. Matching them by
# bare name would flag builtin `setattr(obj, "x", 1)` on a thread-local object,
# which is perfectly safe — a false-positive gate is worse than no gate, since
# it blocks correct code and trains people to delete the check.
_PATCH_NAMES = {"patch"}
_MONKEYPATCH_VERBS = {"setattr", "setenv", "delenv", "delattr", "chdir", "syspath_prepend"}
_MONKEYPATCH_RECEIVERS = {"monkeypatch", "mp"}


def _process_pool_vars(tree: ast.Module) -> set[str]:
    """Variables bound to a PROCESS pool.

    `ProcessPoolExecutor.submit` runs the callable in a separate process, so a
    patch there cannot leak into this interpreter. Flagging it would be a false
    positive.
    """
    names: set[str] = set()

    def ctor_name(node: ast.expr) -> str | None:
        if isinstance(node, ast.Call):
            return getattr(node.func, "id", None) or getattr(
                node.func, "attr", None
            )
        return None

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            tgt = node.targets[0]
            if isinstance(tgt, ast.Name) and ctor_name(node.value) == (
                "ProcessPoolExecutor"
            ):
                names.add(tgt.id)
        if isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                if ctor_name(item.context_expr) == "ProcessPoolExecutor":
                    if isinstance(item.optional_vars, ast.Name):
                        names.add(item.optional_vars.id)
    return names


def _callable_names(node: ast.expr) -> set[str]:
    """Names a callable-valued expression could refer to.

    Handles a bare name, a method reference, and `functools.partial(fn, ...)`.
    """
    if isinstance(node, ast.Name):
        return {node.id}
    if isinstance(node, ast.Attribute):
        return {node.attr}
    if isinstance(node, ast.Call):
        callee = getattr(node.func, "id", None) or getattr(
            node.func, "attr", None
        )
        if callee == "partial" and node.args:
            return _callable_names(node.args[0])
    return set()


def _thread_target_names(tree: ast.Module) -> tuple[set[str], list[ast.Lambda]]:
    """Callables handed to a thread/thread-pool, plus inline lambda targets."""
    names: set[str] = set()
    lambdas: list[ast.Lambda] = []
    process_pools = _process_pool_vars(tree)

    def record(expr: ast.expr) -> None:
        if isinstance(expr, ast.Lambda):
            lambdas.append(expr)
        else:
            names.update(_callable_names(expr))

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        callee = getattr(node.func, "id", None) or getattr(
            node.func, "attr", None
        )
        if callee == "Thread":
            for kw in node.keywords:
                if kw.arg == "target":
                    record(kw.value)
            # Positional: Thread(group, target, name, args, ...)
            if len(node.args) >= 2:
                record(node.args[1])
        elif callee in {"submit", "map", "apply_async"}:
            receiver = getattr(node.func, "value", None)
            if isinstance(receiver, ast.Name) and receiver.id in process_pools:
                continue  # separate process — cannot leak into this one
            if node.args:
                record(node.args[0])
    return names, lambdas


def _patch_aliases(tree: ast.Module) -> set[str]:
    """Local names bound to `unittest.mock.patch`, including aliases."""
    aliases = set(_PATCH_NAMES)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").endswith(
            "mock"
        ):
            for a in node.names:
                if a.name == "patch":
                    aliases.add(a.asname or a.name)
    return aliases


def _offenders(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return []
    targets, lambdas = _thread_target_names(tree)
    if not targets and not lambdas:
        return []
    aliases = _patch_aliases(tree)
    found: list[str] = []

    def scan(body: ast.AST, where: str) -> None:
        for sub in ast.walk(body):
            if not isinstance(sub, ast.Call):
                continue
            name = _unsafe_call_name(sub.func, aliases)
            if name:
                found.append(f"{path.name}:{sub.lineno} — {name} inside {where}")

    for func in ast.walk(tree):
        if isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if func.name in targets:
                scan(func, f"thread target {func.name!r}")
    for lam in lambdas:
        scan(lam, "an inline lambda thread target")
    return found


def _unsafe_call_name(func: ast.expr, aliases: set[str]) -> str | None:
    """Return a label if this call mutates process-global state, else None."""
    # patch(...) — including `from unittest.mock import patch as p`
    if isinstance(func, ast.Name) and func.id in aliases:
        return f"{func.id}()"
    if isinstance(func, ast.Attribute):
        # mock.patch(...)
        if func.attr in aliases:
            return f"{func.attr}()"
        # patch.object(...) / mock.patch.dict(...)
        inner = func.value
        if isinstance(inner, ast.Name) and inner.id in aliases:
            return f"{inner.id}.{func.attr}()"
        if isinstance(inner, ast.Attribute) and inner.attr in aliases:
            return f"{inner.attr}.{func.attr}()"
        receiver = getattr(func.value, "id", None)
        if func.attr in _MONKEYPATCH_VERBS and receiver in _MONKEYPATCH_RECEIVERS:
            return f"{receiver}.{func.attr}()"
    return None


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


# (bad?, source) — every construct the docstring claims to support, both ways.
_DETECTOR_CASES = [
    (True, "kwarg target", """
import threading
from unittest.mock import patch
def worker():
    with patch('subprocess.run'): pass
def test_x():
    threading.Thread(target=worker).start()
"""),
    (True, "positional target", """
import threading
from unittest.mock import patch
def worker():
    with patch('subprocess.run'): pass
def test_x():
    threading.Thread(None, worker).start()
"""),
    (True, "functools.partial target", """
import threading, functools
from unittest.mock import patch
def worker(x):
    with patch('subprocess.run'): pass
def test_x():
    threading.Thread(target=functools.partial(worker, 1)).start()
"""),
    (True, "inline lambda target", """
import threading
from unittest.mock import patch
def test_x():
    threading.Thread(target=lambda: patch('subprocess.run').start()).start()
"""),
    (True, "aliased patch import", """
import threading
from unittest.mock import patch as p
def worker():
    with p('subprocess.run'): pass
def test_x():
    threading.Thread(target=worker).start()
"""),
    (True, "patch.object", """
import threading
from unittest.mock import patch
def worker():
    with patch.object(threading, 'Thread'): pass
def test_x():
    threading.Thread(target=worker).start()
"""),
    (True, "ThreadPoolExecutor.submit", """
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
def worker():
    with patch('subprocess.run'): pass
def test_x():
    ex = ThreadPoolExecutor()
    ex.submit(worker)
"""),
    (True, "monkeypatch.setattr in a thread", """
import threading
def worker(monkeypatch):
    monkeypatch.setattr('subprocess.run', None)
def test_x(monkeypatch):
    threading.Thread(target=worker, args=(monkeypatch,)).start()
"""),
    (False, "correctly hoisted patch", """
import threading
from unittest.mock import patch
def worker(): pass
def test_x():
    with patch('subprocess.run'):
        t = threading.Thread(target=worker)
        t.start(); t.join()
"""),
    (False, "builtin setattr on a local object", """
import threading
class B: pass
def worker(b):
    setattr(b, 'ready', True)
def test_x():
    threading.Thread(target=worker, args=(B(),)).start()
"""),
    (False, "ProcessPoolExecutor.submit (separate process)", """
from concurrent.futures import ProcessPoolExecutor
from unittest.mock import patch
def worker():
    with patch('subprocess.run'): pass
def test_x():
    ex = ProcessPoolExecutor()
    ex.submit(worker)
"""),
    (False, "patch outside any thread target", """
import threading
from unittest.mock import patch
def helper():
    with patch('subprocess.run'): pass
def test_x():
    helper()
"""),
    (False, "no threading at all", """
from unittest.mock import patch
def test_x():
    with patch('subprocess.run'): pass
"""),
]


@pytest.mark.parametrize(
    "should_flag,label,source",
    _DETECTOR_CASES,
    ids=[c[1].replace(" ", "-") for c in _DETECTOR_CASES],
)
def test_detector_matrix(
    should_flag: bool, label: str, source: str, tmp_path: Path
) -> None:
    """Guard the guard, in BOTH directions.

    A scanner that never matches proves nothing; a scanner that matches
    everything is a false-positive gate that gets deleted. Each construct the
    module docstring claims to support appears here, and so does every safe
    lookalike that must not be flagged.
    """
    sample = tmp_path / "test_sample.py"
    sample.write_text(source, encoding="utf-8")
    flagged = bool(_offenders(sample))
    assert flagged is should_flag, (
        f"{label}: expected {'a finding' if should_flag else 'no finding'}, "
        f"got {_offenders(sample) or 'none'}"
    )


def test_indirection_is_a_known_blind_spot(tmp_path: Path) -> None:
    """Documented limitation, pinned so the docstring cannot drift from truth.

    A thread target that calls a helper which patches is NOT detected. If this
    ever starts passing, the detector got smarter and the docstring's "does not
    follow indirection" caveat should be removed.
    """
    sample = tmp_path / "test_indirect.py"
    sample.write_text(
        """
import threading
from unittest.mock import patch
def helper():
    return patch('subprocess.run')
def worker():
    with helper(): pass
def test_x():
    threading.Thread(target=worker).start()
""",
        encoding="utf-8",
    )
    assert not _offenders(sample), (
        "detector unexpectedly followed indirection — update the docstring"
    )
