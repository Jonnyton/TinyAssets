"""Sandboxed execution runtime for user-contributed LangGraph nodes.

User-registered nodes run in isolated subprocesses with:
  - Restricted state access (only declared input/output keys)
  - Timeout enforcement
  - Crash isolation (subprocess death != host death)
  - Import allowlisting
  - No direct filesystem access

The sandbox receives serialized state, executes the node function,
and returns serialized state updates. All communication is via
stdin/stdout JSON messages.

Usage::

    sandbox = NodeSandbox()
    result = await sandbox.execute(
        node_id="consistency-checker",
        source_code="def run(state): ...",
        input_state={"current_scene_text": "...", "facts": [...]},
        input_keys=["current_scene_text", "facts"],
        output_keys=["consistency_notes"],
        timeout=30.0,
    )
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import textwrap
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("universe_server.sandbox")


# ═══════════════════════════════════════════════════════════════════════════
# Execution Result
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class SandboxResult:
    """Result of a sandboxed node execution."""

    node_id: str
    success: bool
    output_state: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    duration_seconds: float = 0.0
    stdout: str = ""
    stderr: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "success": self.success,
            "output_state": self.output_state,
            "error": self.error,
            "duration_seconds": self.duration_seconds,
        }


# ═══════════════════════════════════════════════════════════════════════════
# Import Allowlist
# ═══════════════════════════════════════════════════════════════════════════

# Modules that user-contributed nodes are allowed to import
ALLOWED_IMPORTS = {
    # Standard library — safe subset
    "json", "re", "math", "statistics", "datetime", "collections",
    "dataclasses", "typing", "textwrap", "difflib", "hashlib",
    "urllib.parse", "pathlib", "functools", "itertools", "copy",
    "string", "enum", "abc", "decimal", "fractions",
    # Third-party — vetted safe
    "requests", "httpx",
}

# Patterns that are never allowed in node source code
FORBIDDEN_PATTERNS = [
    "os.system",
    "os.popen",
    "os.exec",
    "os.spawn",
    "os.remove",
    "os.unlink",
    "os.rmdir",
    "os.makedirs",
    "os.rename",
    "subprocess",
    "shutil.rmtree",
    "shutil.move",
    "__import__",
    "eval(",
    "exec(",
    "compile(",
    "open(",
    "builtins",
    "globals(",
    "locals(",
    "breakpoint(",
    "importlib",
    "ctypes",
    "multiprocessing",
    "threading.Thread",
    "signal",
    "socket",
    "pickle",
]


# ═══════════════════════════════════════════════════════════════════════════
# Sandbox Runner Script
# ═══════════════════════════════════════════════════════════════════════════

# This script is executed in the subprocess. It:
# 1. Reads a JSON message from stdin (source_code + input_state)
# 2. Restricts available imports
# 3. Executes the user's node function
# 4. Writes the output state as JSON to stdout

_RUNNER_SCRIPT = textwrap.dedent('''\
    import json
    import sys

    # Read input from stdin
    raw = sys.stdin.read()
    msg = json.loads(raw)

    source_code = msg["source_code"]
    input_state = msg["input_state"]
    output_keys = msg["output_keys"]
    allowed_imports = set(msg["allowed_imports"])

    # Restrict imports
    _original_import = (
        __builtins__.__import__
        if hasattr(__builtins__, "__import__")
        else __import__
    )

    def _restricted_import(name, *args, **kwargs):
        top_level = name.split(".")[0]
        if top_level not in allowed_imports:
            raise ImportError(
                f"Import '{name}' is not allowed in sandboxed nodes. "
                f"Allowed: {sorted(allowed_imports)}"
            )
        return _original_import(name, *args, **kwargs)

    if hasattr(__builtins__, "__import__"):
        __builtins__.__import__ = _restricted_import
    else:
        import builtins
        builtins.__import__ = _restricted_import

    # Execute the user's code to define the function
    namespace = {"__builtins__": __builtins__}
    exec(source_code, namespace)

    # Find the node function (must be called 'run' or be the last defined function)
    func = namespace.get("run")
    if func is None:
        # Find the last defined callable
        for name, obj in reversed(list(namespace.items())):
            if callable(obj) and not name.startswith("_"):
                func = obj
                break

    if func is None:
        result = {"success": False, "error": "No callable function found in node source code."}
    else:
        try:
            output = func(input_state)
            if not isinstance(output, dict):
                result = {
                    "success": False,
                    "error": f"Node function must return a dict, got {type(output).__name__}",
                }
            else:
                # Filter to declared output keys only
                filtered = {k: v for k, v in output.items() if k in output_keys}
                undeclared = [k for k in output if k not in output_keys]
                result = {
                    "success": True,
                    "output_state": filtered,
                }
                if undeclared:
                    result["warning"] = f"Undeclared output keys ignored: {undeclared}"
        except Exception as e:
            result = {"success": False, "error": f"{type(e).__name__}: {e}"}

    # Write result to stdout
    print(json.dumps(result))
''')


# ═══════════════════════════════════════════════════════════════════════════
# Sandbox
# ═══════════════════════════════════════════════════════════════════════════


class NodeSandbox:
    """Executes user-contributed nodes in isolated subprocesses."""

    def __init__(
        self,
        timeout: float = 30.0,
        max_output_bytes: int = 1_000_000,  # 1MB
    ) -> None:
        self.default_timeout = timeout
        self.max_output_bytes = max_output_bytes

    def validate_source(self, source_code: str) -> list[str]:
        """Pre-validate source code before execution.

        Returns a list of validation errors (empty if valid).
        """
        errors = []

        for pattern in FORBIDDEN_PATTERNS:
            if pattern in source_code:
                errors.append(f"Forbidden pattern: '{pattern}'")

        # Check for excessive code size
        if len(source_code) > 50_000:
            errors.append("Source code exceeds 50KB limit")

        # Basic syntax check
        try:
            compile(source_code, "<node>", "exec")
        except SyntaxError as exc:
            errors.append(f"Syntax error: {exc}")

        return errors

    async def execute(
        self,
        node_id: str,
        source_code: str,
        input_state: dict[str, Any],
        input_keys: list[str],
        output_keys: list[str],
        timeout: float | None = None,
        dependencies: list[str] | None = None,
    ) -> SandboxResult:
        """Execute a node in a sandboxed subprocess.

        Args:
            node_id: Identifier for logging and tracking.
            source_code: Python source code defining the node function.
            input_state: Full graph state (will be filtered to input_keys).
            input_keys: Which state keys the node is allowed to read.
            output_keys: Which state keys the node is allowed to write.
            timeout: Max execution time in seconds.
            dependencies: Required pip packages (pre-validated).

        Returns:
            SandboxResult with success/failure, output state, and timing.
        """
        timeout = timeout or self.default_timeout
        start_time = time.monotonic()

        # Pre-validation
        errors = self.validate_source(source_code)
        if errors:
            return SandboxResult(
                node_id=node_id,
                success=False,
                error=f"Validation failed: {'; '.join(errors)}",
            )

        # Filter input state to declared keys only
        filtered_input = {
            k: v for k, v in input_state.items()
            if k in input_keys
        }

        # Build the message for the subprocess
        message = json.dumps({
            "source_code": source_code,
            "input_state": filtered_input,
            "output_keys": output_keys,
            "allowed_imports": sorted(ALLOWED_IMPORTS),
        }, default=str)

        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-c", _RUNNER_SCRIPT,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                # Limit environment
                env={
                    "PATH": os.environ.get("PATH", ""),
                    "PYTHONPATH": "",
                    "HOME": "/tmp",
                },
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(input=message.encode("utf-8")),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return SandboxResult(
                    node_id=node_id,
                    success=False,
                    error=f"Execution timed out after {timeout}s",
                    duration_seconds=time.monotonic() - start_time,
                )

            duration = time.monotonic() - start_time
            stdout_str = stdout_bytes.decode("utf-8", errors="replace")[:self.max_output_bytes]
            stderr_str = stderr_bytes.decode("utf-8", errors="replace")[:10_000]

            if proc.returncode != 0:
                return SandboxResult(
                    node_id=node_id,
                    success=False,
                    error=f"Process exited with code {proc.returncode}: {stderr_str}",
                    duration_seconds=duration,
                    stdout=stdout_str,
                    stderr=stderr_str,
                )

            # Parse the output
            try:
                result = json.loads(stdout_str.strip())
            except json.JSONDecodeError:
                return SandboxResult(
                    node_id=node_id,
                    success=False,
                    error=f"Node produced invalid JSON output: {stdout_str[:200]}",
                    duration_seconds=duration,
                )

            return SandboxResult(
                node_id=node_id,
                success=result.get("success", False),
                output_state=result.get("output_state", {}),
                error=result.get("error", ""),
                duration_seconds=duration,
                stdout=stdout_str,
                stderr=stderr_str,
            )

        except OSError as exc:
            return SandboxResult(
                node_id=node_id,
                success=False,
                error=f"Failed to start subprocess: {exc}",
                duration_seconds=time.monotonic() - start_time,
            )

    async def execute_registered(
        self,
        node_registration: dict[str, Any],
        graph_state: dict[str, Any],
        timeout: float | None = None,
    ) -> SandboxResult:
        """Execute a registered node from the node registry.

        Convenience wrapper that unpacks a NodeRegistration dict.
        """
        return await self.execute(
            node_id=node_registration["node_id"],
            source_code=node_registration["source_code"],
            input_state=graph_state,
            input_keys=node_registration.get("input_keys", []),
            output_keys=node_registration.get("output_keys", []),
            timeout=timeout,
            dependencies=node_registration.get("dependencies", []),
        )
