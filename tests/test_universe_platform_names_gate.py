"""universe-runtime-state: no platform name is joined onto a path outside the
resolver.

Every platform-owned name of a universe lives under ``.runtime/state`` and is
reached through ``universe_paths.platform_path``. A reader that still joins one
onto a directory -- ``udir / "status.json"``, ``Path(u) / _DB_NAME``,
``os.path.join(root, "story.db")`` -- reads the universe root, which the agent
can write. This scans every executable tree for that shape.

A text scan alone cannot prove completeness (refute round 1), so it is one of
three layers: the scope-split APIs, this gate, and the tombstones that make any
missed reader fail loudly at runtime.

Names shared with the DATA ROOT (``.runs.db``, ``outbound.db`` ...) are joined
onto the data root legitimately. Each such site is listed in ``ALLOWED`` with
its reason, and an entry that no longer matches anything fails the test, so
the list cannot rot into a blanket exemption.
"""

from __future__ import annotations

import ast
from pathlib import Path

from tinyassets import universe_paths as up

REPO = Path(__file__).resolve().parents[1]
TREES = ("tinyassets", "fantasy_daemon", "domains", "scripts")
SKIP = {
    Path("tinyassets/universe_paths.py"),
}

#: Joined onto the data root, never a universe. Grouped by store.
_DATA_ROOT_OUTBOUND = (
    "the data root's outbound connection ledger (joined onto the base, or onto a "
    "universe's parent)"
)
_DATA_ROOT_RUNS = "the data root's shared runs database"

#: (file, name) -> why joining it there is not a universe read.
ALLOWED: dict[tuple[str, str], str] = {
    ('scripts/workspace_bwrap_oracle.py', 'outbound.db'): _DATA_ROOT_OUTBOUND,
    ('tinyassets/api/cloud_connections.py', 'outbound.db'): _DATA_ROOT_OUTBOUND,
    ('tinyassets/api/compute_connection.py', 'outbound.db'): _DATA_ROOT_OUTBOUND,
    ('tinyassets/api/connection_uses.py', 'outbound.db'): _DATA_ROOT_OUTBOUND,
    ('tinyassets/api/http_connection.py', 'outbound.db'): _DATA_ROOT_OUTBOUND,
    ('tinyassets/api/model_access_requests.py', 'outbound.db'): _DATA_ROOT_OUTBOUND,
    ('tinyassets/api/pending_requests.py', 'outbound.db'): _DATA_ROOT_OUTBOUND,
    ('tinyassets/api/provider_capability.py', 'outbound.db'): _DATA_ROOT_OUTBOUND,
    ('tinyassets/effectors/authenticated_external_call.py', 'outbound.db'): _DATA_ROOT_OUTBOUND,
    ('tinyassets/effectors/workspace.py', 'outbound.db'): _DATA_ROOT_OUTBOUND,
    ('tinyassets/onboarding/connections.py', 'outbound.db'): _DATA_ROOT_OUTBOUND,
    ('tinyassets/onboarding/model_bootstrap.py', 'outbound.db'): _DATA_ROOT_OUTBOUND,
    ('tinyassets/onboarding/model_bootstrap_candidate.py', 'outbound.db'): _DATA_ROOT_OUTBOUND,
    ('tinyassets/onboarding/realtime_voice.py', 'outbound.db'): _DATA_ROOT_OUTBOUND,
    ('tinyassets/onboarding/source_connect.py', 'outbound.db'): _DATA_ROOT_OUTBOUND,
    ('tinyassets/provider_serving_binding.py', 'outbound.db'): _DATA_ROOT_OUTBOUND,
    ('tinyassets/providers/api_key_http_provider.py', 'outbound.db'): _DATA_ROOT_OUTBOUND,
    ('tinyassets/providers/connection_lifecycle.py', 'outbound.db'): _DATA_ROOT_OUTBOUND,
    ('tinyassets/providers/discovery_snapshot.py', 'outbound.db'): _DATA_ROOT_OUTBOUND,
    ('tinyassets/providers/source_display.py', 'outbound.db'): _DATA_ROOT_OUTBOUND,
    ('tinyassets/workspace_intents.py', 'outbound.db'): _DATA_ROOT_OUTBOUND,
    ('tinyassets/api/engine_helpers.py', 'ledger.json'):
        "the data root's global ledger (branch definitions are not universe-scoped)",
    ('tinyassets/api/market.py', '.runs.db'): _DATA_ROOT_RUNS,
    ('tinyassets/daemon_server.py', '.runs.db'): _DATA_ROOT_RUNS,
    ('tinyassets/runs.py', '.runs.db'):
        "runs_db_path: the data root's runs database (a universe's is universe_runs_db_path)",
    ('tinyassets/scheduler.py', '.runs.db'): _DATA_ROOT_RUNS,
    ('tinyassets/scoped_reset.py', '.runs.db'):
        "operator reset of the data root's runs database",
    ('tinyassets/storage/conversation_reset.py', '.runs.db'): _DATA_ROOT_RUNS,
    ('tinyassets/storage_accounting.py', '.runs.db'):
        "accounting reads the data root's runs database",
    ('tinyassets/runs.py', '.langgraph_runs.db'):
        "the data root's LangGraph run checkpointer",
    ('tinyassets/storage_accounting.py', '.langgraph_runs.db'):
        "accounting reads the data root's run checkpointer",
    ('tinyassets/authoring/store.py', '.authoring.db'):
        "the data root's authoring store",
    ('tinyassets/idempotency.py', '.idempotency.db'):
        "the data root's idempotency store",
    ('tinyassets/daemon_brain.py', 'lancedb'):
        "the data root's daemon-brain vector index",
    ('tinyassets/memory/archival.py', 'knowledge.db'):
        'a sibling of the already-resolved story.db path, so it follows that store',
}


def _platform_name(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    entry = up.platform_name_for(value)
    return value if entry is not None else None


def _module_constants(tree: ast.Module) -> dict[str, str]:
    found: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            for target in node.targets:
                if isinstance(target, ast.Name) and _platform_name(node.value.value):
                    found[target.id] = node.value.value
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and isinstance(node.value, ast.Constant)
            and _platform_name(node.value.value)
        ):
            found[node.target.id] = node.value.value
    return found


def _joined_name(node: ast.AST, constants: dict[str, str]) -> str | None:
    if isinstance(node, ast.Constant):
        return _platform_name(node.value)
    if isinstance(node, ast.Name):
        return constants.get(node.id)
    if isinstance(node, ast.JoinedStr) and node.values:
        head = node.values[0]
        if isinstance(head, ast.Constant):
            text = str(head.value)
            for entry in up.PLATFORM_NAMES.values():
                if text.startswith(entry.name) and (
                    entry.kind == "prefix" or text[len(entry.name):].startswith(("-", "."))
                ):
                    return entry.name
    return None


def _joins(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    constants = _module_constants(tree)
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            name = _joined_name(node.right, constants)
            if name:
                hits.append((node.lineno, name))
        elif isinstance(node, ast.Call):
            func = node.func
            dotted = (
                f"{func.value.id}.{func.attr}"
                if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name)
                else ""
            )
            if dotted in ("path.join", "os.path.join") or (
                isinstance(func, ast.Attribute)
                and func.attr == "join"
                and isinstance(func.value, ast.Attribute)
                and func.value.attr == "path"
            ):
                for arg in node.args[1:]:
                    name = _joined_name(arg, constants)
                    if name:
                        hits.append((node.lineno, name))
            if isinstance(func, ast.Attribute) and func.attr in ("joinpath", "glob"):
                for arg in node.args:
                    name = _joined_name(arg, constants)
                    if name:
                        hits.append((node.lineno, name))
    return hits


def _all_joins() -> dict[tuple[str, str], list[int]]:
    found: dict[tuple[str, str], list[int]] = {}
    for tree in TREES:
        for path in sorted((REPO / tree).rglob("*.py")):
            rel = path.relative_to(REPO)
            if rel in SKIP or "__pycache__" in rel.parts:
                continue
            for line, name in _joins(path):
                found.setdefault((rel.as_posix(), name), []).append(line)
    return found


def test_no_platform_name_is_joined_onto_a_path_outside_the_resolver():
    joins = _all_joins()
    unexplained = {
        f"{file}:{lines[0]} {name}": lines
        for (file, name), lines in joins.items()
        if (file, name) not in ALLOWED
    }
    assert not unexplained, (
        "platform names joined onto a path outside universe_paths.platform_path. "
        "A universe read must go through the resolver; a DATA-ROOT store goes in "
        "ALLOWED with its reason:\n" + "\n".join(sorted(unexplained))
    )


def test_every_allowance_still_matches_something():
    joins = _all_joins()
    stale = sorted(f"{file} {name}" for (file, name) in ALLOWED if (file, name) not in joins)
    assert not stale, f"ALLOWED entries that match nothing any more: {stale}"


def test_the_gate_catches_each_shape(tmp_path):
    sample = tmp_path / "sample.py"
    sample.write_text(
        "import os\n"
        "from pathlib import Path\n"
        "_DB = '.effector_consents.db'\n"
        "a = Path(u) / 'status.json'\n"
        "b = Path(u) / _DB\n"
        "c = os.path.join(u, 'story.db')\n"
        "d = u / f'.worker_supervisor.{x}.json'\n"
        "e = u / 'soul.md'\n",
        encoding="utf-8",
    )
    assert [name for _, name in _joins(sample)] == [
        "status.json", ".effector_consents.db", "story.db", ".worker_supervisor.",
    ]
