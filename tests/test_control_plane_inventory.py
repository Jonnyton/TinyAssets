"""No timer lives in a box or jail; every platform timer is classified (design D7).

The scan finds every loop that waits on a clock (a ``while`` containing a
``sleep``/``wait`` call) and every ``threading.Timer`` in ``tinyassets/``, and
requires each to be classified in ``tests/control_plane_timer_inventory.py``.
A ``box`` classification is forbidden outright, and the jails that run a
command center's code cannot outlive the call that started them, so nothing
inside one can keep time on its own.
"""

from __future__ import annotations

import ast
from pathlib import Path

from tests import control_plane_timer_inventory as inventory

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "tinyassets"
_WAITS = {"sleep", "wait"}


def _call_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def _waits(node: ast.AST) -> bool:
    return any(isinstance(n, ast.Call) and _call_name(n) in _WAITS for n in ast.walk(node))


def _scan() -> set[str]:
    found: set[str] = set()
    for path in sorted(PACKAGE.rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        stack: list[str] = []

        def visit(node: ast.AST) -> None:
            scoped = isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            if scoped:
                stack.append(node.name)
            if isinstance(node, ast.While) and _waits(node):
                found.add(f"{rel}::{'.'.join(stack) or '<module>'}")
            if isinstance(node, ast.Call) and _call_name(node) == "Timer":
                found.add(f"{rel}::{'.'.join(stack) or '<module>'} [Timer]")
            for child in ast.iter_child_nodes(node):
                visit(child)
            if scoped:
                stack.pop()

        visit(tree)
    return found


def test_every_periodic_loop_is_classified_and_none_is_stale():
    found = _scan()
    listed = set(inventory.SITES)
    assert sorted(found - listed) == [], (
        "a new clock-driven loop must be classified in "
        "tests/control_plane_timer_inventory.py (D7: boxes keep no timers)"
    )
    assert sorted(listed - found) == [], "inventory entries whose loop is gone"


def test_no_timer_is_classified_as_living_in_a_box():
    assert {cls for cls, _note in inventory.SITES.values()} <= inventory.CLASSES
    assert [site for site, (cls, _n) in inventory.SITES.items() if cls == inventory.BOX] == []


def test_jailed_processes_cannot_outlive_their_call(tmp_path, monkeypatch):
    """The four-tool jail (built on ``provider_jail.jail_argv``, which provider
    CLIs share) and the code-node jail (``_bwrap_argv``) die with the platform
    process that started the call, in their own pid namespace: nothing a
    command center runs can keep a timer."""
    from tinyassets import universe_tools
    from tinyassets.node_sandbox import _bwrap_argv
    from tinyassets.providers import provider_jail

    universe = tmp_path / "data" / "cc-jail"
    universe.mkdir(parents=True)
    monkeypatch.setattr(provider_jail, "BWRAP_RESOLVER", lambda: "/usr/bin/bwrap")
    tool = universe_tools.tool_jail_argv(universe, ["/bin/true"])
    node = _bwrap_argv(bwrap_path="/usr/bin/bwrap")
    for argv in (tool, node):
        assert "--die-with-parent" in argv
        assert "--unshare-all" in argv


def test_the_scheduler_package_imports_nothing_from_the_jail_side():
    """The trigger table and tick are control-plane code: they must not reach
    for a jail or a command center's files to decide anything."""
    forbidden = {"universe_tools", "provider_jail", "node_sandbox", "universe_files"}
    for path in (PACKAGE / "control_plane").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                modules = [node.module or ""] + [a.name for a in node.names]
            elif isinstance(node, ast.Import):
                modules = [a.name for a in node.names]
            else:
                continue
            for module in modules:
                assert not forbidden & set(module.split(".")), f"{path.name} imports {module}"
