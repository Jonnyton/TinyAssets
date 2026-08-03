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

**What this detector is.** A deliberately narrow lint, not a proof.

Covered: `threading.Thread(target=…)` — keyword or positional — where the target
is a named function, a `functools.partial` of one, or an inline `lambda`; and
`patch` spelled bare, under an import alias, as `mock.patch`, or as
`patch.object`, plus `monkeypatch.<verb>()`.

**Not covered, and pinned by tests below so this list cannot drift:**

* `ThreadPoolExecutor.submit` / `.map` and other executor APIs;
* indirection — a thread target that calls a helper which patches;
* dynamically-built or aliased `Thread` constructors.

Those exclusions are chosen, not accidental. An earlier revision did try to
resolve executors, and review found every broadening unsound: builtin
`map(worker, xs)` matched, an unrelated `obj.patch()` matched as `mock.patch`,
and the `ProcessPoolExecutor` exemption keyed on a module-wide *variable name*,
so reusing `executor` for a thread pool elsewhere in the same file silently
suppressed a real offender. A false positive wedges a correct PR and teaches
people to delete the check; a false negative in a lint is survivable. So the
unsound half was removed rather than patched.

Treat a green result as "the obvious spelling is absent", not "the pattern is
impossible".
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


def _thread_target_names(tree: ast.Module) -> tuple[set[str], list[ast.Lambda]]:
    """Callables handed to `threading.Thread`, plus inline lambda targets.

    Scope is deliberately narrow: `threading.Thread` ONLY. An earlier version
    also tried to resolve `submit`/`map`/`apply_async` on executors, and every
    one of those broadenings turned out unsound in review:

      * builtin `map(worker, xs)` matched, flagging non-threaded code;
      * `obj.patch()` on an unrelated object matched as `mock.patch`;
      * the `ProcessPoolExecutor` exemption keyed on a module-wide VARIABLE
        NAME, so reusing `executor` for a thread pool elsewhere in the same
        file silently suppressed a real offender.

    A false positive wedges a correct PR and teaches people to delete the
    check; a false negative in a lint is survivable. So the unsound half was
    removed rather than patched, and executors are a documented blind spot
    with a pinned test below.
    """
    names: set[str] = set()
    lambdas: list[ast.Lambda] = []

    def record(expr: ast.expr) -> None:
        if isinstance(expr, ast.Lambda):
            lambdas.append(expr)
        elif isinstance(expr, ast.Name):
            names.add(expr.id)
        elif isinstance(expr, ast.Attribute):
            names.add(expr.attr)
        elif isinstance(expr, ast.Call):
            callee = getattr(expr.func, "id", None) or getattr(
                expr.func, "attr", None
            )
            if callee == "partial" and expr.args:
                record(expr.args[0])

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        callee = getattr(node.func, "id", None) or getattr(
            node.func, "attr", None
        )
        if callee != "Thread":
            continue
        for kw in node.keywords:
            if kw.arg == "target":
                record(kw.value)
        # Positional signature: Thread(group, target, name, args, kwargs)
        if len(node.args) >= 2:
            record(node.args[1])
    return names, lambdas


def _patch_aliases(tree: ast.Module) -> tuple[set[str], set[str]]:
    """(names bound to `mock.patch`, names bound to the `mock` MODULE).

    Both halves matter. Without the second, any attribute call spelled `.patch`
    matches — so an unrelated `quilt.patch(hole)` inside a thread target was
    flagged as mock patching, which would wedge a correct PR. The receiver has
    to be a name actually bound to the mock module.
    """
    aliases = set(_PATCH_NAMES)
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for a in node.names:
                if module.endswith("mock") and a.name == "patch":
                    aliases.add(a.asname or a.name)
                # `from unittest import mock`
                if a.name == "mock":
                    modules.add(a.asname or a.name)
        elif isinstance(node, ast.Import):
            for a in node.names:
                # `import mock` / `import unittest.mock as m`
                if a.name == "mock" or a.name.endswith(".mock"):
                    modules.add(a.asname or a.name.split(".")[-1])
    return aliases, modules


def _offenders(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return []
    targets, lambdas = _thread_target_names(tree)
    if not targets and not lambdas:
        return []
    aliases, mock_modules = _patch_aliases(tree)
    found: list[str] = []

    def scan(body: ast.AST, where: str) -> None:
        for sub in ast.walk(body):
            if not isinstance(sub, ast.Call):
                continue
            name = _unsafe_call_name(sub.func, aliases, mock_modules)
            if name:
                found.append(f"{path.name}:{sub.lineno} — {name} inside {where}")

    for func in ast.walk(tree):
        if isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if func.name in targets:
                scan(func, f"thread target {func.name!r}")
    for lam in lambdas:
        scan(lam, "an inline lambda thread target")
    return found


def _unsafe_call_name(
    func: ast.expr, aliases: set[str], mock_modules: set[str]
) -> str | None:
    """Return a label if this call mutates process-global state, else None."""
    # patch(...) — including `from unittest.mock import patch as p`
    if isinstance(func, ast.Name) and func.id in aliases:
        return f"{func.id}()"
    if isinstance(func, ast.Attribute):
        receiver = getattr(func.value, "id", None)
        # mock.patch(...) — ONLY on a receiver bound to the mock module. A bare
        # `.patch` match flags any unrelated object with a `patch` method.
        if func.attr in aliases and receiver in mock_modules:
            return f"{receiver}.{func.attr}()"
        # patch.object(...) / patch.dict(...) — receiver is `patch` itself
        inner = func.value
        if isinstance(inner, ast.Name) and inner.id in aliases:
            return f"{inner.id}.{func.attr}()"
        # mock.patch.object(...)
        if (
            isinstance(inner, ast.Attribute)
            and inner.attr in aliases
            and getattr(inner.value, "id", None) in mock_modules
        ):
            return f"{inner.attr}.{func.attr}()"
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
    # Documented blind spot, asserted as such: executors are out of scope.
    (False, "ThreadPoolExecutor.submit (BLIND SPOT, not covered)", """
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
def worker():
    with patch('subprocess.run'): pass
def test_x():
    ex = ThreadPoolExecutor()
    ex.submit(worker)
"""),
    (False, "builtin map() must never be treated as a thread pool", """
from unittest.mock import patch
def worker(x):
    with patch('subprocess.run'): pass
def test_x():
    list(map(worker, [1, 2]))
"""),
    (False, "unrelated obj.patch() is not mock.patch", """
import threading
class Quilt:
    def patch(self, x): return x
def worker(q):
    q.patch('hole')
def test_x():
    threading.Thread(target=worker, args=(Quilt(),)).start()
"""),
    (True, "mock.patch attribute spelling", """
import threading
from unittest import mock
def worker():
    with mock.patch('subprocess.run'): pass
def test_x():
    threading.Thread(target=worker).start()
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
