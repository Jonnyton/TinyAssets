"""Paid-market pure logic (Tracks E-I + tokens): spot index, buckets,
forwards, ceiling feed, training, pools, licenses, shuttles,
fabrication, fund, ledger, matching.

Nothing in this package does I/O; transport layers on top. Every
money-path computation is integer/Fraction exact with conservation
invariants asserted internally. See SUCCESSION-2026-07-08.md.
"""

from tinyassets.paid_market.buckets import (  # noqa: F401
    BucketError,
    enumerate_buckets,
    is_aligned,
    next_bucket_start,
    validate_bucket_start,
)
from tinyassets.paid_market.ceiling import (  # noqa: F401
    CeilingError,
    ModelPrice,
    ceiling_for_capability,
    parse_models_payload,
)
from tinyassets.paid_market.fabrication import (  # noqa: F401
    FabricationError,
    SellerOffer,
    quote_print_job,
    rank_sellers,
    settle_physical_job,
)
from tinyassets.paid_market.forwards import (  # noqa: F401
    ForwardError,
    ForwardState,
    Settlement,
    assert_transition,
    collateral_micros,
    contract_total_micros,
    settle_forward,
)
from tinyassets.paid_market.fund import (  # noqa: F401
    FundError,
    FundState,
    mint_at_nav,
    mint_at_nav_with_fee,
    nav_micros_per_token,
    record_fee_inflow,
    redeem_at_nav,
    redeem_at_nav_with_fee,
    redemption_capacity_base_units,
)
from tinyassets.paid_market.index import (  # noqa: F401
    IndexError_,
    SettledTrade,
    SpotQuote,
    compute_spot_quote,
    compute_vwap,
)
from tinyassets.paid_market.ledger import (  # noqa: F401
    Ledger,
    LedgerError,
    escrow_lock_entries,
    forward_sale_entries,
    forward_settlement_entries,
    physical_settlement_entries,
    pool_close_entries,
    training_settlement_entries,
)
from tinyassets.paid_market.license_terms import (  # noqa: F401
    LicenseError,
    Terms,
    check_trainable,
    compose_terms,
    terms_for,
)
from tinyassets.paid_market.match import (  # noqa: F401
    BookOffer,
    MatchError,
    best_execution,
)
from tinyassets.paid_market.pool import (  # noqa: F401
    PoolError,
    apportion_exact,
    distribute_revenue,
    settle_pool_funding,
)
from tinyassets.paid_market.shuttle import (  # noqa: F401
    ShuttleError,
    allocate_shuttle,
)
from tinyassets.paid_market.training import (  # noqa: F401
    TrainingError,
    TrainingSettlement,
    settle_training_window,
)
