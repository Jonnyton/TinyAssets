"""Account tiers have only storage and concurrent seats."""
import pytest

from tinyassets.usage_policy import limits_for, upgrade_url


@pytest.mark.parametrize("tier", ["", "unknown", "enterprise", None])
def test_unknown_tiers_are_free(tier):
    assert limits_for(tier) == limits_for("free")


def test_account_dimensions_and_upgrade():
    free, paid = limits_for("free"), limits_for("paid")
    assert free.seats == 3 and free.background_seats == 2
    assert paid.seats > free.seats
    assert paid.storage_bytes > free.storage_bytes
    assert upgrade_url("free") == "https://tinyassets.io/app?upgrade=1"
    assert upgrade_url("paid") is None
    assert set(free.__dataclass_fields__) == {
        "name", "seats", "interactive_reserve", "storage_bytes",
    }
