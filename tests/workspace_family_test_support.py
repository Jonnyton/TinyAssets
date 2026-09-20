"""Explicit simulated readiness for dark family lifecycle tests, not startup proof."""

from contextlib import contextmanager

import pytest

from tinyassets import runs
from tinyassets import workspace_family as family


@contextmanager
def simulated_managed_runtime(base):
    ready = family._ManagedRuntimeReadiness(runs.runs_db_path(base))
    token = family._MANAGED_RUNTIME_READY.set(ready)
    try:
        yield ready
    finally:
        ready.retire()
        family._MANAGED_RUNTIME_READY.reset(token)


@pytest.fixture(autouse=True)
def managed_runtime(tmp_path):
    with simulated_managed_runtime(tmp_path):
        yield
