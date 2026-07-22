"""Regression coverage for the packaged legacy MCP process fence."""

import pytest

from tinyassets import mcp_server


def test_main_refuses_to_start_without_explicit_legacy_opt_in(monkeypatch):
    monkeypatch.delenv("TINYASSETS_ENABLE_LEGACY_MCP", raising=False)
    run_called = False

    def unexpected_run():
        nonlocal run_called
        run_called = True

    monkeypatch.setattr(mcp_server.mcp, "run", unexpected_run)

    with pytest.raises(SystemExit, match="legacy MCP server is disabled"):
        mcp_server.main()

    assert run_called is False
