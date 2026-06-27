"""Workflow — first domain implementation on the Workflow Engine.

Owns its own LangGraph graph topology (scene/chapter/book/universe).
Imports shared infrastructure from tinyassets/.
"""

__version__ = "0.1.0"


def _init_producers() -> None:
    """Register fantasy TaskProducers at domain-import time (Phase C.4).

    Kept in a function so tests that monkeypatch registry state can
    call it explicitly. No side effects beyond the registry.
    """
    from domains.fantasy_daemon.producers import register_fantasy_producers
    register_fantasy_producers()


_init_producers()
