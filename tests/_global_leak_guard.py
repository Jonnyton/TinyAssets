"""Detect a test that leaves a process-global patched.

Lives in its own module, not inline in ``conftest.py``, so the lifecycle
semantics can be unit-tested rather than asserted about.

Why this exists
---------------
A test that patches a process-global and fails to restore it corrupts every
later test in the same interpreter, and the damage surfaces in the *victims*
rather than the culprit — which is why this class always reads as flaky
ordering. Two measured incidents: a threaded
``patch("...github_pr.subprocess.run")`` leaked and ~70 unrelated tests received
its canned stdout (#2199), and a ``shutil.which`` stub latched
``git_bridge.is_enabled`` and silently no-opped 138 tests. In both, the guilty
test passed.

What it is, precisely
---------------------
A **five-attribute** detector, not a general process-global leak detector. It
notices rebinding of the module attributes in :data:`WATCHED` and nothing else.
Invisible to it: a consumer alias captured by ``from subprocess import run``, a
mutation performed after the check, and a patch already active before setup.
Those are chosen limits, not oversights — a broad "diff every module attribute"
sweep would be slow and noisy.

Opting out
----------
A fixture that deliberately owns one of these attributes for a whole module or
session is legitimate, and repairing it mid-scope would BREAK it. Mark such
tests::

    @pytest.mark.allow_global_patch("subprocess.run")

That suppresses both the failure and the repair for exactly those attributes.
"""

from __future__ import annotations

import importlib

# (module, attribute) pairs. Kept to the two families with measured incidents.
WATCHED = (
    ("subprocess", "run"),
    ("subprocess", "Popen"),
    ("subprocess", "check_output"),
    ("subprocess", "check_call"),
    ("shutil", "which"),
)

MARKER = "allow_global_patch"


def snapshot() -> dict[tuple[str, str], object]:
    """Current value of every watched attribute."""
    snap: dict[tuple[str, str], object] = {}
    for module_name, attr in WATCHED:
        try:
            module = importlib.import_module(module_name)
        except ImportError:  # pragma: no cover - stdlib, but stay fail-soft
            continue
        snap[(module_name, attr)] = getattr(module, attr, None)
    return snap


def exempt_targets(marker_args: tuple[object, ...]) -> set[str]:
    """Attribute names an ``allow_global_patch`` marker declares ownership of.

    ``@pytest.mark.allow_global_patch("subprocess.run", "shutil.which")`` ->
    ``{"subprocess.run", "shutil.which"}``. A bare marker with no arguments
    exempts everything, which is blunt but explicit.
    """
    if not marker_args:
        return {f"{m}.{a}" for m, a in WATCHED}
    return {str(arg) for arg in marker_args}


def diff(
    baseline: dict[tuple[str, str], object],
    exempt: set[str] | None = None,
) -> list[tuple[str, str, object]]:
    """Watched attributes whose value changed since ``baseline``.

    Returns ``(module, attr, original)`` so the caller can decide whether to
    repair. Exempt targets are skipped entirely — neither reported nor
    repaired, because repairing one would break the fixture that owns it.
    """
    exempt = exempt or set()
    changed: list[tuple[str, str, object]] = []
    for (module_name, attr), original in baseline.items():
        if f"{module_name}.{attr}" in exempt:
            continue
        module = importlib.import_module(module_name)
        if getattr(module, attr, None) is not original:
            changed.append((module_name, attr, original))
    return changed


def repair(changed: list[tuple[str, str, object]]) -> None:
    """Put the originals back.

    One offender should not cascade into a wall of unrelated failures; the
    point of this guard is to *attribute* the leak, not to punish its victims.
    """
    for module_name, attr, original in changed:
        setattr(importlib.import_module(module_name), attr, original)


def describe(node_id: str, changed: list[tuple[str, str, object]]) -> str:
    leaked = ", ".join(
        f"{m}.{a} -> {getattr(importlib.import_module(m), a, None)!r}"
        for m, a, _ in changed
    )
    return (
        f"{node_id} left a process-global patched, which silently corrupts "
        f"every later test in this process: {leaked}. A common cause is "
        f"entering `patch(...)` from inside a thread worker — that swap is not "
        f"thread-local, so two threads can interleave and leave the mock "
        f"installed permanently. Hoist the patch to wrap the whole concurrent "
        f"section on the calling thread. If a fixture legitimately owns this "
        f"attribute for its whole scope, mark the test "
        f"`@pytest.mark.{MARKER}(\"<module>.<attr>\")`."
    )
