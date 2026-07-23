from __future__ import annotations

import ast
import asyncio
import inspect
import json
import subprocess
import sys
from pathlib import Path

from tinyassets import directory_server


def test_directory_import_has_no_universe_challenge_side_effect() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import json, sys; "
                "import tinyassets.directory_server; "
                "from tinyassets.auth.middleware import "
                "anonymous_write_challenge_tools; "
                "print(json.dumps({"
                "'universe_server_imported': "
                "'tinyassets.universe_server' in sys.modules, "
                "'challenge_tools': sorted(anonymous_write_challenge_tools())"
                "}))"
            ),
        ],
        cwd=repo_root,
        capture_output=True,
        check=True,
        text=True,
    )

    assert json.loads(probe.stdout) == {
        "universe_server_imported": False,
        "challenge_tools": [],
    }


def test_every_mutating_directory_tool_has_its_own_inline_write_gate() -> None:
    source_tree = ast.parse(inspect.getsource(directory_server))
    functions = {
        node.name: node
        for node in source_tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    wire_handlers: dict[str, str] = {}

    for call in (node for node in ast.walk(source_tree) if isinstance(node, ast.Call)):
        if not isinstance(call.func, ast.Name):
            continue
        if call.func.id != "_register_structured_tool" or not call.args:
            continue
        server = next((kw.value for kw in call.keywords if kw.arg == "server"), None)
        if not isinstance(server, ast.Name) or server.id != "directory_mcp":
            continue
        handler = call.args[0]
        if not isinstance(handler, ast.Name):
            continue
        name = next((kw.value for kw in call.keywords if kw.arg == "name"), None)
        wire_name = name.value if isinstance(name, ast.Constant) else handler.id
        wire_handlers[wire_name] = handler.id

    tools = asyncio.run(directory_server.directory_mcp.list_tools(run_middleware=False))
    mutating_tools = {
        tool.name
        for tool in tools
        if tool.annotations is None or tool.annotations.readOnlyHint is not True
    }
    missing_gates = set()
    for wire_name in mutating_tools:
        handler = functions.get(wire_handlers.get(wire_name, ""))
        has_matching_gate = handler is not None and any(
            isinstance(call.func, ast.Name)
            and call.func.id == "write_gate_rejection"
            and bool(call.args)
            and isinstance(call.args[0], ast.Constant)
            and call.args[0].value == wire_name
            for call in ast.walk(handler)
            if isinstance(call, ast.Call)
        )
        if not has_matching_gate:
            missing_gates.add(wire_name)

    assert not missing_gates, (
        "non-read-only directory tools must gate their own handler: "
        f"{sorted(missing_gates)}"
    )
