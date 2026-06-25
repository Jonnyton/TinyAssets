"""Contract lock: every advertised MCP handle parameter must be labelled.

This is the version-independent guard behind PR-178's labelled tool
surface. FastMCP's own docstring->schema extraction is version-dependent
(absent in fastmcp 3.2.0, present in 3.4.x), so without
``workflow.mcp_schema_utils`` the live ``/mcp`` surface would advertise
unlabelled parameters on some installs and labelled ones on others.

The test asserts the *outcome* (every advertised parameter carries a
non-empty description) rather than the mechanism, so it stays green
regardless of which FastMCP version resolves at test time and fails
loudly if a future parameter or refactor ships an unlabelled param.
"""

from __future__ import annotations

import asyncio
from typing import Annotated

import pytest
from pydantic import Field

from workflow import directory_server, universe_server
from workflow.mcp_schema_utils import describe_signature, parse_docstring_args


def _advertised(mcp) -> list:
    return asyncio.run(mcp.list_tools())


def _unlabelled_params(tools) -> list[str]:
    missing: list[str] = []
    for tool in tools:
        props = (tool.parameters or {}).get("properties", {})
        for pname, pschema in props.items():
            if not str(pschema.get("description", "")).strip():
                missing.append(f"{tool.name}.{pname}")
    return missing


@pytest.mark.parametrize(
    "mcp",
    [universe_server.mcp, directory_server.directory_mcp],
    ids=["universe_server", "directory_server"],
)
def test_every_advertised_param_is_labelled(mcp):
    tools = _advertised(mcp)
    assert tools, "expected the server to advertise at least one tool"
    missing = _unlabelled_params(tools)
    assert not missing, (
        "advertised MCP parameters missing descriptions "
        f"(FastMCP-version-independent contract violated): {missing}"
    )


def test_five_canonical_handles_fully_labelled():
    tools = {t.name: t for t in _advertised(universe_server.mcp)}
    for handle in ("read_graph", "write_graph", "run_graph", "read_page", "write_page"):
        assert handle in tools, f"canonical handle {handle} not advertised"
        props = (tools[handle].parameters or {}).get("properties", {})
        assert props, f"{handle} advertises no parameters"
        for pname, pschema in props.items():
            assert str(pschema.get("description", "")).strip(), (
                f"{handle}.{pname} advertised without a description"
            )


def _parser_sample(a: str = "", b: int = 0) -> str:
    """Summary.

    Args:
        a: First parameter description.
        b: Second parameter
            spanning two lines.

    Returns:
        Nothing useful.
    """


def _override_sample(
    a: Annotated[str, Field(description="explicit override")] = "",
    b: str = "",
) -> str:
    """Summary.

    Args:
        a: docstring default that must lose to the explicit Field.
        b: docstring description that should win.
    """


def test_parser_extracts_google_args_block():
    parsed = parse_docstring_args(_parser_sample.__doc__)
    assert parsed["a"] == "First parameter description."
    assert parsed["b"] == "Second parameter spanning two lines."
    assert "Returns" not in parsed


def test_explicit_field_is_not_overridden():
    # Defined at module scope so get_type_hints resolves Annotated/Field
    # against module globals (mirrors how the real server modules import them).
    _, annotations = describe_signature(_override_sample)
    a_meta = annotations["a"].__metadata__[0]
    b_meta = annotations["b"].__metadata__[0]
    assert a_meta.description == "explicit override"
    assert b_meta.description == "docstring description that should win."
