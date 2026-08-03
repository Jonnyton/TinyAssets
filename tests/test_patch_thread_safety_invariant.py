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

Covered: a `threading.Thread(target=…)` — keyword or positional — whose target is
a named function, a `functools.partial` of one, or an inline `lambda`, entering
`unittest.mock.patch` (bare, aliased, as `mock.patch`, or as `patch.object`) or
any `monkeypatch.<verb>()`.

**Bindings are resolved from imports, never from spelling.** `Thread` must come
from `threading` and `patch` from `unittest.mock`/`mock`. Review found three
false positives when this matched by name — an unrelated `widgets.Thread(...)`,
a locally-defined `patch()` helper, and `from custom_package import mock` —
each of which would have wedged a correct PR.

**Not covered, and pinned by tests below so this list cannot drift:**

* `ThreadPoolExecutor.submit` / `.map` and other executor APIs;
* indirection — a thread target that calls a helper which patches;
* dynamically-built `Thread` constructors (e.g. `getattr(threading, "Thread")`).

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

# Two shapes mutate PROCESS-GLOBAL state on enter and restore it on exit, and
# are deliberately matched by different rules rather than one name set:
#
#   * `patch(...)` / `mock.patch(...)` / `patch.object(...)` — resolved from
#     imports, never from spelling;
#   * `monkeypatch.<verb>(...)` — pytest's fixture, equally process-global.
#     The verbs are matched ONLY on a `monkeypatch`/`mp` receiver, because
#     matching them by bare name flags builtin `setattr(obj, "x", 1)` on a
#     thread-local object, which is perfectly safe.
#
# Only these modules bind the real `patch`. Matching any module whose name ends
# in "mock" flagged `from custom_package import mock`, and matching a bare
# `patch()` with no import at all flagged a locally-defined helper called
# `patch` — both wedge correct PRs.
_MOCK_MODULES = {"unittest.mock", "mock"}

# pytest's MonkeyPatch, which is process-global exactly like mock.patch.
# The full mutating surface, so the docstring's claim is true rather than
# approximately true. `undo` is included because calling it from one thread
# reverts another thread's patches.
_MONKEYPATCH_VERBS = {
    "setattr",
    "delattr",
    "setitem",
    "delitem",
    "setenv",
    "delenv",
    "chdir",
    "syspath_prepend",
    "undo",
}
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
    ctor_names, ctor_modules = _thread_ctor_names(tree)

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

    def is_threading_thread(func: ast.expr) -> bool:
        if isinstance(func, ast.Name):
            return func.id in ctor_names
        if isinstance(func, ast.Attribute):
            return func.attr == "Thread" and (
                getattr(func.value, "id", None) in ctor_modules
            )
        return False

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not is_threading_thread(node.func):
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

    Resolved from actual imports, not from spelling. Name-based matching
    produced three separate false positives in review — an unrelated
    `quilt.patch(hole)`, a locally-defined `patch()` helper, and
    `from custom_package import mock` — each of which would wedge a correct PR.
    """
    aliases: set[str] = set()
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for a in node.names:
                # `from unittest.mock import patch [as p]`
                if module in _MOCK_MODULES and a.name == "patch":
                    aliases.add(a.asname or a.name)
                # `from unittest import mock [as m]`
                if module == "unittest" and a.name == "mock":
                    modules.add(a.asname or a.name)
        elif isinstance(node, ast.Import):
            for a in node.names:
                # `import mock` / `import unittest.mock as m`
                if a.name in _MOCK_MODULES:
                    modules.add(a.asname or a.name.split(".")[-1])
    return aliases, modules


def _thread_ctor_names(tree: ast.Module) -> tuple[set[str], set[str]]:
    """(names bound to `threading.Thread`, names bound to `threading`).

    Matching any callee spelled `Thread` flagged an unrelated
    `widgets.Thread(...)`. The constructor has to come from `threading`.
    """
    names: set[str] = set()
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "threading":
            for a in node.names:
                if a.name == "Thread":
                    names.add(a.asname or a.name)
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.name == "threading":
                    modules.add(a.asname or a.name)
    return names, modules


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
        # mock.patch(...) — the attribute is literally `patch` and the receiver
        # is a name bound to the mock MODULE. (`aliases` is the separate
        # from-import binding; a module-attribute access does not use it.) A
        # bare `.patch` match flags any unrelated object with a patch method.
        if func.attr == "patch" and receiver in mock_modules:
            return f"{receiver}.patch()"
        # patch.object(...) / patch.dict(...) — receiver is `patch` itself
        inner = func.value
        if isinstance(inner, ast.Name) and inner.id in aliases:
            return f"{inner.id}.{func.attr}()"
        # mock.patch.object(...)
        if (
            isinstance(inner, ast.Attribute)
            and inner.attr == "patch"
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
    # Three false positives found in round-3 review; each would wedge a
    # correct PR, which is why binding is now resolved from imports.
    (False, "unrelated widgets.Thread is not threading.Thread", """
import widgets
from unittest.mock import patch
def worker():
    with patch('subprocess.run'): pass
def test_x():
    widgets.Thread(target=worker).start()
"""),
    (False, "locally-defined patch() helper is not mock.patch", """
import threading
from contextlib import contextmanager
@contextmanager
def patch(x):
    yield
def worker():
    with patch('anything'): pass
def test_x():
    threading.Thread(target=worker).start()
"""),
    (False, "from custom_package import mock is not unittest.mock", """
import threading
from custom_package import mock
def worker():
    with mock.patch('subprocess.run'): pass
def test_x():
    threading.Thread(target=worker).start()
"""),
    (True, "monkeypatch.setitem mutates process-global state too", """
import threading, os
def worker(monkeypatch):
    monkeypatch.setitem(os.environ, 'X', '1')
def test_x(monkeypatch):
    threading.Thread(target=worker, args=(monkeypatch,)).start()
"""),
    (True, "monkeypatch.undo reverts another thread's patches", """
import threading
def worker(monkeypatch):
    monkeypatch.undo()
def test_x(monkeypatch):
    threading.Thread(target=worker, args=(monkeypatch,)).start()
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
