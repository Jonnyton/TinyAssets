"""A governed agent invocation's native CLI gets the canonical engine tool floor.

The governed agent-invocation path hands a native provider CLI its tool set, and
for the claude CLI that denylist IS the filesystem boundary (there is no bwrap
around it). It denied only Bash/Write/Edit/NotebookEdit, leaving ``Read`` /
``Glob`` / ``Grep`` / ``LS`` and ``Monitor`` (which runs shell) able to read
native credential material off disk and send it out through the explicitly
authorized WebFetch egress -- reachable by foreign-authored remixed graph
content.

The fix REUSES ``universe_intelligence._ENGINE_DISALLOWED_TOOLS`` rather than
re-listing it, keeping one documented divergence: WebSearch is explicitly
authorized on this path.

The last test reads the ``ModelConfig`` the provider object ACTUALLY received on
the shipping execution path -- never the source text. No real LLM, credential
or subprocess is involved: the execution path uses the recording fake provider
from ``tests.test_agent_runtime_provider_call``.
"""

from __future__ import annotations

import pytest

from tests.test_agent_runtime_invocation import _request
from tests.test_agent_runtime_provider_call import (  # noqa: F401
    _execution_service,
    _RecordingProvider,
    cloud_runtime,
)
from tinyassets.providers.router import ProviderRouter
from tinyassets.universe_intelligence import _ENGINE_DISALLOWED_TOOLS

_FLOOR_MINUS_WEBSEARCH = tuple(
    tool for tool in _ENGINE_DISALLOWED_TOOLS if tool != "WebSearch"
)
# Every tool the old four-entry denylist left reachable on a native turn.
_PREVIOUSLY_REACHABLE = ("Read", "Glob", "Grep", "LS", "Monitor", "Task", "mcp__*")


def test_disallowed_tools_are_the_canonical_floor_minus_websearch():
    """The floor is REUSED, so a tool added there can never be missing here."""

    from tinyassets.agent_runtime_provider_execution import (
        AGENT_INVOCATION_ALLOWED_TOOLS,
        _agent_invocation_disallowed_tools,
    )

    denied = _agent_invocation_disallowed_tools()

    assert denied == _FLOOR_MINUS_WEBSEARCH
    assert "WebSearch" not in denied
    assert set(AGENT_INVOCATION_ALLOWED_TOOLS) == {"WebFetch", "WebSearch"}
    for tool in _PREVIOUSLY_REACHABLE:
        assert tool in denied, tool


@pytest.mark.usefixtures("cloud_runtime")
def test_executed_provider_call_receives_the_floor_not_the_old_four(
    tmp_path, authenticate_request
):
    """Assert the ``ModelConfig`` the provider ACTUALLY got, not the source text."""

    service, admitted, _universe_dir, _manifest = _execution_service(
        tmp_path, authenticate_request
    )
    provider = _RecordingProvider()
    router = ProviderRouter({"codex": provider})

    service.execute_provider_call(
        admitted.invocation.invocation_id,
        typed_input=_request().typed_input,
        router=router,
    )

    assert provider.calls, "fake provider was never called"
    config = provider.calls[-1][2]
    denied = set(config.disallowed_tools or ())
    allowed = set(config.allowed_tools or ())

    # The canonical floor, except the explicitly authorized WebSearch.
    assert denied == set(_FLOOR_MINUS_WEBSEARCH)
    assert "WebSearch" in allowed and "WebSearch" not in denied
    assert "WebFetch" in allowed and "WebFetch" not in denied
    # Regression guard on the exact gap this closes: the old list was these four.
    assert denied > {"Bash", "Write", "Edit", "NotebookEdit"}
    for tool in _PREVIOUSLY_REACHABLE:
        assert tool in denied, tool
