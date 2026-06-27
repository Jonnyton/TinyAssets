"""Logger namespace regression tests for extracted API modules."""

from __future__ import annotations


def test_branch_api_logger_uses_module_namespace() -> None:
    from tinyassets.api import branches

    assert branches.logger.name == "tinyassets.api.branches"


def test_branch_api_uses_workflow_db_helper_name() -> None:
    from tinyassets.api import branches

    assert hasattr(branches, "_ensure_workflow_db")
    assert not hasattr(branches, "_ensure_author_server_db")


def test_extensions_api_logger_uses_module_namespace() -> None:
    from tinyassets.api import extensions

    assert extensions.logger.name == "tinyassets.api.extensions"
