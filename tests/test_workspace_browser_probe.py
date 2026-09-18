"""The diagnostic comparison never changes production resource defaults."""

import pytest

from scripts.probes.workspace_browser_compatibility import diagnostic_limits
from tinyassets.node_sandbox import WorkspaceLimits


def test_default_probe_keeps_production_profile():
    assert diagnostic_limits(False, "max") == WorkspaceLimits()
    assert diagnostic_limits(False, "max").rlimit_as == 1536 * 1024 * 1024


@pytest.mark.parametrize("value", ["max", "", "bad", "-1", "0", "2147483649"])
def test_comparison_refuses_unbounded_or_larger_physical_memory(value):
    with pytest.raises(ValueError, match="comparison requires"):
        diagnostic_limits(True, value)


def test_comparison_changes_only_virtual_limit_with_verified_physical_bound():
    comparison = diagnostic_limits(True, "2147483648\n")
    expected = WorkspaceLimits().rlimit_profile()
    expected["RLIMIT_AS"] = -1
    assert comparison.rlimit_profile() == expected
    assert comparison.rss_cap_bytes == WorkspaceLimits().rss_cap_bytes
    assert WorkspaceLimits().rlimit_as == 1536 * 1024 * 1024
