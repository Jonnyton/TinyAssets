"""Guard: no new raw file read or write in a module that touches universe paths.

A workflow provider jail binds its universe read-write and allows ``symlink``,
so any path under the data dir may be a link planted by a universe pointing at
another universe (``docs/concerns/2026-10-01-provider-planted-link-reads-another-universe.md``).
The daemon reads and writes those paths through ONE pair of helpers:
:func:`tinyassets.universe_files.read_data_path` /
:func:`~tinyassets.universe_files.write_data_path` (and the relpath forms
``read_universe_file`` / ``write_universe_file``), which follow no link at any
component and refuse loudly.

This test pins, per module, how many raw file operations remain in every module
that mentions a universe or data-dir path. Adding one fails: route it through
``universe_files``. Removing one also fails until the pin is lowered, so the
count only ever shrinks. Many pinned sites read platform files that are in no
universe (package assets, the data root's own files); the pin does not claim
each is unsafe, only that none is added unreviewed.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_PKG = _REPO / "tinyassets"

#: The helpers themselves: the only modules allowed to do the raw I/O.
_EXEMPT = {"tinyassets/universe_files.py", "tinyassets/workspace_fs.py"}

_TOUCHES_UNIVERSE = re.compile(r"universe_dir|\budir\b|_universe_dir|data_dir\(\)|_base_path\(\)")
_RAW_ATTRS = {"read_text", "read_bytes", "write_text", "write_bytes", "open"}
_RAW_OS = {"replace", "rename"}
_RAW_SHUTIL = {"copy", "copy2", "copyfile", "move"}


def _raw_ops(source: str) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == "open":
            found.append((node.lineno, "open()"))
        elif isinstance(func, ast.Attribute):
            owner = func.value.id if isinstance(func.value, ast.Name) else ""
            if func.attr in _RAW_ATTRS:
                found.append((node.lineno, f"{owner}.{func.attr}()"))
            elif owner == "os" and func.attr in _RAW_OS:
                found.append((node.lineno, f"os.{func.attr}()"))
            elif owner == "shutil" and func.attr in _RAW_SHUTIL:
                found.append((node.lineno, f"shutil.{func.attr}()"))
    return found


def _scan() -> dict[str, list[tuple[int, str]]]:
    out: dict[str, list[tuple[int, str]]] = {}
    for path in sorted(_PKG.rglob("*.py")):
        rel = path.relative_to(_REPO).as_posix()
        if rel in _EXEMPT:
            continue
        source = path.read_text(encoding="utf-8")
        if not _TOUCHES_UNIVERSE.search(source):
            continue
        ops = _raw_ops(source)
        if ops:
            out[rel] = ops
    return out


#: module -> raw file operations remaining (2026-10-01). Lower a number when
#: you convert a site; never raise one.
PINNED: dict[str, int] = {
    "tinyassets/agent_sessions.py": 5,
    "tinyassets/api/pending_requests.py": 1,
    "tinyassets/api/status.py": 1,
    "tinyassets/api/universe.py": 6,
    "tinyassets/api/universe_file_reads.py": 1,
    "tinyassets/api/wiki.py": 14,
    "tinyassets/authoring/store.py": 1,
    "tinyassets/billing/stripe_adapter.py": 2,
    "tinyassets/credential_refresh.py": 1,
    "tinyassets/credential_vault.py": 9,
    "tinyassets/daemon_server.py": 5,
    "tinyassets/desktop/launcher.py": 1,
    "tinyassets/desktop/packaged_entrypoint.py": 3,
    "tinyassets/effectors/wiki_write_back.py": 1,
    "tinyassets/engine_mcp_http.py": 3,
    "tinyassets/mcp_server.py": 9,
    "tinyassets/onboarding/__init__.py": 3,
    "tinyassets/onboarding/hosted_model_auth.py": 1,
    "tinyassets/onboarding/session_store.py": 3,
    "tinyassets/platform_runtime_provenance.py": 2,
    "tinyassets/provider_assignment.py": 1,
    "tinyassets/providers/base.py": 5,
    "tinyassets/providers/claude_provider.py": 1,
    "tinyassets/providers/codex_provider.py": 1,
    "tinyassets/providers/definition.py": 3,
    "tinyassets/soul_edit.py": 2,
    "tinyassets/storage/__init__.py": 4,
    "tinyassets/storage/outbound_connections.py": 4,
    "tinyassets/storage/rotation.py": 2,
    "tinyassets/storage_accounting.py": 1,
    "tinyassets/subscription_refresh.py": 1,
    "tinyassets/universe_bundle.py": 1,
    "tinyassets/universe_intelligence.py": 1,
    "tinyassets/universe_soul.py": 2,
    "tinyassets/universe_tools.py": 10,
    "tinyassets/wiki/okf_export.py": 4,
}


def test_no_new_raw_file_io_in_universe_touching_modules():
    live = _scan()
    grown = {
        mod: (len(ops), PINNED.get(mod, 0))
        for mod, ops in live.items()
        if len(ops) > PINNED.get(mod, 0)
    }
    assert not grown, (
        "new raw file read/write in a module that touches universe paths; route "
        "it through tinyassets.universe_files (read_data_path / write_data_path), "
        "which follows no link and refuses loudly:\n"
        + "\n".join(
            f"{mod}: {now} raw ops, pinned {pin}: "
            + ", ".join(f"L{line} {what}" for line, what in live[mod])
            for mod, (now, pin) in sorted(grown.items())
        )
    )


def test_the_pin_only_shrinks():
    live = {mod: len(ops) for mod, ops in _scan().items()}
    stale = {
        mod: (live.get(mod, 0), pin)
        for mod, pin in PINNED.items()
        if live.get(mod, 0) < pin
    }
    assert not stale, (
        "raw file ops were removed; lower PINNED to the new count so they "
        f"cannot come back: {stale}"
    )


def test_the_scan_sees_a_raw_read_and_write():
    """Detection control: the scanner is not vacuous."""
    ops = {what for _l, what in _raw_ops(
        "import os\n"
        "def f(udir):\n"
        "    (udir / 'a').write_text('x')\n"
        "    os.replace(udir / 'b', udir / 'c')\n"
        "    return open(udir / 'd').read()\n"
    )}
    assert {".write_text()", "os.replace()", "open()"} <= ops
