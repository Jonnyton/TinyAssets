"""Immutable per-execution universe pin (round-22 #1).

Carries WHICH universe an engine execution runs for, from the run/resume/compiler
boundary down toward the provider chokepoint. It is a defense-in-depth SEAM: the
PRIMARY fail-closed gate is the graph-execution chokepoint
(:func:`tinyassets.runs._invoke_graph` / ``_invoke_graph_resume``), which refuses to
run a blocked universe BEFORE any node/provider is reached. This pin lets a
same-thread provider call (one not routed through a separate timeout executor) also
resolve the run's universe at the router preflight without every node having to thread
``UniverseContext`` explicitly.

Kept deliberately tiny + dependency-free so both ``tinyassets.runs`` and
``tinyassets.providers.router`` can import it with no cycle.
"""

from __future__ import annotations

import contextlib
from contextvars import ContextVar
from pathlib import Path
from typing import Iterator

_EXECUTION_UNIVERSE: ContextVar[str | None] = ContextVar(
    "execution_universe", default=None,
)


def get_execution_universe() -> Path | None:
    """Return the pinned execution universe for the current context, or ``None``."""
    value = _EXECUTION_UNIVERSE.get()
    return Path(value) if value else None


def set_execution_universe(universe_dir: str | Path | None):
    """Pin the execution universe for the current context (thread/task). Returns the
    reset token. Use inside a worker thread that cannot wrap the whole run in a
    ``with`` block; pair with :func:`reset_execution_universe`."""
    value = str(Path(universe_dir)) if universe_dir is not None else None
    return _EXECUTION_UNIVERSE.set(value)


def reset_execution_universe(token) -> None:
    """Reset the pin using the token returned by :func:`set_execution_universe`."""
    try:
        _EXECUTION_UNIVERSE.reset(token)
    except (ValueError, LookupError):
        pass


@contextlib.contextmanager
def pin_execution_universe(universe_dir: str | Path | None) -> Iterator[None]:
    """Context-manager form: pin *universe_dir* for the duration of the block."""
    token = set_execution_universe(universe_dir)
    try:
        yield
    finally:
        reset_execution_universe(token)
