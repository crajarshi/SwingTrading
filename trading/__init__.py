"""Trading modules for paper trading system."""

from .paper_engine import (
    generate_run_id,
    filter_candidates,
    compute_position_size,
    construct_entry_leg,
    construct_bracket_levels,
    enforce_portfolio_caps,
    derive_candidate_reason,
    build_order_intents,
    serialize_intents,
    apply_price_guards,
    compute_safe_position_size,
    generate_fallback_strategy
)

from .executor import (
    ensure_not_already_placed,
    place_orders,
    write_orders_log,
    place_with_fallback
)

from .reconciliation import (
    morning_reconcile,
    handle_partial_fill,
    cancel_stale_opg,
    clean_stale_intents
)

from .position_manager import (
    close_positions_by_age,
    close_positions_with_earnings,
    emergency_close_all
)

__all__ = [
    # paper_engine
    'generate_run_id',
    'filter_candidates',
    'compute_position_size',
    'construct_entry_leg',
    'construct_bracket_levels',
    'enforce_portfolio_caps',
    'derive_candidate_reason',
    'build_order_intents',
    'serialize_intents',
    'apply_price_guards',
    'compute_safe_position_size',
    'generate_fallback_strategy',
    
    # executor
    'ensure_not_already_placed',
    'place_orders',
    'write_orders_log',
    'place_with_fallback',
    
    # reconciliation
    'morning_reconcile',
    'handle_partial_fill',
    'cancel_stale_opg',
    'clean_stale_intents',
    
    # position_manager
    'close_positions_by_age',
    'close_positions_with_earnings',
    'emergency_close_all'
]