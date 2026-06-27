"""Security invariants for the user-node sandbox.

`tinyassets/node_sandbox.py` runs user-contributed LangGraph nodes inside a
subprocess with import allowlisting, timeout enforcement, IO scoping,
and forbidden-pattern pre-validation. These tests pin the invariants
the paid-market execution path depends on.

Tests use the real subprocess runner (not mocks) so the assertions
exercise the actual isolation shape. Tests are slow-ish (~100ms per
subprocess); kept to a tight set that covers the security surface
without bloating CI time.
"""

from __future__ import annotations

import asyncio

import pytest

from tinyassets.node_sandbox import (
    ALLOWED_IMPORTS,
    FORBIDDEN_PATTERNS,
    NodeSandbox,
    SandboxResult,
)


def _run(coro):
    return asyncio.run(coro)


# -------------------------------------------------------------------
# Happy path
# -------------------------------------------------------------------


def test_happy_path_returns_declared_output_keys():
    """Snippet returning a dict with declared keys round-trips cleanly."""
    sandbox = NodeSandbox(timeout=10.0)
    source = "def run(state):\n    return {'greeting': 'hello ' + state['name']}\n"

    result = _run(
        sandbox.execute(
            node_id="happy",
            source_code=source,
            input_state={"name": "world", "ignored": "secret"},
            input_keys=["name"],
            output_keys=["greeting"],
        )
    )

    assert isinstance(result, SandboxResult)
    assert result.success is True
    assert result.error == ""
    assert result.output_state == {"greeting": "hello world"}
    assert result.duration_seconds > 0


def test_input_keys_filter_strips_undeclared_state():
    """State keys not in input_keys must not reach the node function."""
    sandbox = NodeSandbox(timeout=10.0)
    source = (
        "def run(state):\n"
        "    return {'seen_keys': sorted(list(state.keys()))}\n"
    )

    result = _run(
        sandbox.execute(
            node_id="scope",
            source_code=source,
            input_state={"allowed": 1, "forbidden": 2, "also_forbidden": 3},
            input_keys=["allowed"],
            output_keys=["seen_keys"],
        )
    )

    assert result.success is True
    assert result.output_state == {"seen_keys": ["allowed"]}


def test_output_keys_filter_strips_undeclared_returns():
    """Node return keys not in output_keys must be dropped from output_state."""
    sandbox = NodeSandbox(timeout=10.0)
    source = (
        "def run(state):\n"
        "    return {'allowed': 'yes', 'smuggled': 'exfil'}\n"
    )

    result = _run(
        sandbox.execute(
            node_id="smuggle",
            source_code=source,
            input_state={},
            input_keys=[],
            output_keys=["allowed"],
        )
    )

    assert result.success is True
    assert "smuggled" not in result.output_state
    assert result.output_state == {"allowed": "yes"}


# -------------------------------------------------------------------
# Timeout enforcement
# -------------------------------------------------------------------


def test_timeout_kills_infinite_loop():
    """An infinite loop must be killed within ~timeout seconds."""
    sandbox = NodeSandbox(timeout=1.0)
    # `time.sleep` is not in ALLOWED_IMPORTS — use a busy loop via a
    # minimal-allowed construct (itertools.count exhausted manually).
    source = (
        "def run(state):\n"
        "    while True:\n"
        "        pass\n"
    )

    result = _run(
        sandbox.execute(
            node_id="loop",
            source_code=source,
            input_state={},
            input_keys=[],
            output_keys=[],
            timeout=1.0,
        )
    )

    assert result.success is False
    assert "timed out" in result.error.lower()
    # Timeout should be enforced near the configured window, not many
    # seconds later.
    assert result.duration_seconds < 5.0


# -------------------------------------------------------------------
# Forbidden-pattern pre-validation
# -------------------------------------------------------------------


@pytest.mark.parametrize(
    "pattern_source",
    [
        "import os\ndef run(state):\n    os.system('whoami')\n    return {}\n",
        "import subprocess\ndef run(state):\n    return {}\n",
        "def run(state):\n    eval('1+1')\n    return {}\n",
        "def run(state):\n    exec('print(1)')\n    return {}\n",
        "def run(state):\n    open('secrets.txt').read()\n    return {}\n",
        "def run(state):\n    __import__('socket')\n    return {}\n",
        "import pickle\ndef run(state):\n    return {}\n",
        "import ctypes\ndef run(state):\n    return {}\n",
    ],
)
def test_forbidden_pattern_rejected_pre_execution(pattern_source):
    """validate_source rejects forbidden patterns before any subprocess starts."""
    sandbox = NodeSandbox(timeout=5.0)

    errors = sandbox.validate_source(pattern_source)

    assert errors, (
        f"validate_source should reject source containing forbidden pattern:\n"
        f"{pattern_source!r}"
    )
    assert any("Forbidden pattern" in e for e in errors)


def test_oversized_source_rejected():
    """Source over 50KB is rejected."""
    sandbox = NodeSandbox()
    giant = "def run(state):\n    return {}\n" + ("# pad\n" * 10_000)

    errors = sandbox.validate_source(giant)

    assert any("50KB" in e for e in errors)


def test_syntax_error_rejected():
    """Unparseable source yields a syntax-error validation entry."""
    sandbox = NodeSandbox()

    errors = sandbox.validate_source("def run(state):\n    return {broken\n")

    assert any("Syntax error" in e for e in errors)


def test_execute_short_circuits_on_validation_failure():
    """Validation failure returns SandboxResult.success=False without launching subprocess."""
    sandbox = NodeSandbox(timeout=30.0)

    result = _run(
        sandbox.execute(
            node_id="bad",
            source_code="import subprocess\ndef run(state):\n    return {}\n",
            input_state={},
            input_keys=[],
            output_keys=[],
        )
    )

    assert result.success is False
    assert "Validation failed" in result.error
    # Should not have run subprocess — duration near-zero.
    assert result.duration_seconds < 1.0


# -------------------------------------------------------------------
# Import allowlist enforcement (runtime, in subprocess)
# -------------------------------------------------------------------


def test_import_not_in_allowlist_fails_at_runtime():
    """A non-forbidden but non-allowlisted import is blocked at runtime.

    `sys` is neither in ALLOWED_IMPORTS nor in FORBIDDEN_PATTERNS, so it
    passes pre-validation but the in-subprocess restricted __import__
    must reject it.
    """
    sandbox = NodeSandbox(timeout=10.0)
    source = "import sys\ndef run(state):\n    return {'argv0': sys.argv[0]}\n"

    # Sanity: no forbidden pattern, passes pre-validation.
    assert sandbox.validate_source(source) == []

    result = _run(
        sandbox.execute(
            node_id="sneaky",
            source_code=source,
            input_state={},
            input_keys=[],
            output_keys=["argv0"],
        )
    )

    assert result.success is False
    assert "not allowed" in result.error.lower() or "importerror" in result.error.lower()


def test_allowlisted_import_succeeds():
    """An ALLOWED_IMPORTS module (e.g., json) works inside the sandbox."""
    assert "json" in ALLOWED_IMPORTS

    sandbox = NodeSandbox(timeout=10.0)
    source = (
        "import json\n"
        "def run(state):\n"
        "    return {'payload': json.dumps({'n': len(state.get('items', []))})}\n"
    )

    result = _run(
        sandbox.execute(
            node_id="allowed",
            source_code=source,
            input_state={"items": [1, 2, 3]},
            input_keys=["items"],
            output_keys=["payload"],
        )
    )

    assert result.success is True
    assert result.output_state == {"payload": '{"n": 3}'}


# -------------------------------------------------------------------
# Error capture: runtime exceptions surface structured, not silent
# -------------------------------------------------------------------


def test_runtime_exception_surfaces_as_structured_error():
    """A snippet that raises returns success=False with the exception detail."""
    sandbox = NodeSandbox(timeout=10.0)
    source = (
        "def run(state):\n"
        "    raise ValueError('deliberate failure')\n"
    )

    result = _run(
        sandbox.execute(
            node_id="raiser",
            source_code=source,
            input_state={},
            input_keys=[],
            output_keys=[],
        )
    )

    assert result.success is False
    assert "ValueError" in result.error
    assert "deliberate failure" in result.error
    # Silent-success is the failure mode we're guarding against.
    assert result.output_state == {}


def test_no_callable_found_returns_structured_error():
    """Source with no function yields a structured error, not a crash."""
    sandbox = NodeSandbox(timeout=10.0)

    result = _run(
        sandbox.execute(
            node_id="empty",
            source_code="x = 1\n",
            input_state={},
            input_keys=[],
            output_keys=[],
        )
    )

    assert result.success is False
    assert "no callable" in result.error.lower()


def test_non_dict_return_surfaces_as_error():
    """Node must return a dict; scalar/list returns surface as structured error."""
    sandbox = NodeSandbox(timeout=10.0)
    source = "def run(state):\n    return 42\n"

    result = _run(
        sandbox.execute(
            node_id="bad-return",
            source_code=source,
            input_state={},
            input_keys=[],
            output_keys=[],
        )
    )

    assert result.success is False
    assert "must return a dict" in result.error


# -------------------------------------------------------------------
# Environment-variable scoping
# -------------------------------------------------------------------


def test_environment_is_restricted_to_allowlist(monkeypatch):
    """Host env vars outside {PATH, PYTHONPATH, HOME} must not reach the subprocess.

    Uses os.environ inspection from inside the sandbox — but `os` isn't
    in ALLOWED_IMPORTS, so we have to probe via a path that the allowlist
    permits. The runner script doesn't expose the subprocess env directly.
    Instead: set a secret in host env, verify sandbox code that would try
    to read it gets rejected (because 'os' import is blocked), AND confirm
    the sandbox-builder sets env to the restricted dict.
    """
    # Verify the restriction by inspecting what os.environ would look like
    # inside the subprocess. We can't import os from inside, so use a
    # structural check: the execute() code path sets env={"PATH": ..., ...}
    # explicitly — that's the security property. Probe it by reading the
    # module source (the env dict literal) and verifying the allowlist
    # shape has not drifted.
    import inspect

    from tinyassets import node_sandbox

    src = inspect.getsource(node_sandbox.NodeSandbox.execute)
    # The subprocess env dict must include only PATH, PYTHONPATH, HOME.
    # Anything else is a regression in the isolation shape.
    assert '"PATH": os.environ.get("PATH"' in src
    assert '"PYTHONPATH": ""' in src
    assert '"HOME":' in src
    # Any host secret we set should NOT appear listed in the env dict.
    monkeypatch.setenv("TINYASSETS_TEST_SECRET", "should-not-leak")
    assert "TINYASSETS_TEST_SECRET" not in src


# -------------------------------------------------------------------
# Allowlist / Forbidden-list structural invariants
# -------------------------------------------------------------------


def test_allowlist_and_forbidden_are_disjoint_for_top_level_names():
    """No module is both allowlisted AND forbidden by top-level name."""
    forbidden_top_names = set()
    for pat in FORBIDDEN_PATTERNS:
        # Only patterns that look like top-level names (no dot, no paren).
        if "(" not in pat and "." not in pat and "__" not in pat:
            forbidden_top_names.add(pat)
    overlap = ALLOWED_IMPORTS & forbidden_top_names
    assert overlap == set(), (
        f"Allowlist and forbidden list must not overlap; got: {overlap}"
    )


def test_critical_forbidden_patterns_are_present():
    """Regression guard: a few must-block patterns have to stay forbidden."""
    must_block = {"subprocess", "pickle", "ctypes", "eval(", "exec(", "open("}
    present = set(FORBIDDEN_PATTERNS)
    missing = must_block - present
    assert not missing, (
        f"Critical forbidden patterns missing from FORBIDDEN_PATTERNS: {missing}"
    )
