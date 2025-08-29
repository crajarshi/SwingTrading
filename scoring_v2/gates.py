"""Setup gates with frozen thresholds and inclusive boundaries."""

from typing import Tuple, Optional

# Frozen gate thresholds (version-locked)
GATES_V2 = {
    "atr_ratio": (0.005, 0.08),      # 0.5% to 8% of price (inclusive)
    "trend_filter": 1.0,              # close >= 1.0 × SMA50 (inclusive)
    "pullback_band": (0.05, 0.20)     # 5% to 20% below high20 (inclusive)
}


def evaluate_gates(
    atr_ratio: float,
    close_t: float,
    sma50_t_minus_1: float,
    pullback_pct: float
) -> Tuple[bool, Optional[str]]:
    """Evaluate setup gates in order.
    
    Order: ATR → Trend → Pullback
    All boundaries are INCLUSIVE.
    First failure returns (False, reason).
    
    Args:
        atr_ratio: ATR / Close ratio
        close_t: Current close price
        sma50_t_minus_1: SMA50 calculated on T-1 data
        pullback_pct: Pullback percentage (0-100)
    
    Returns:
        (pass, reason_if_failed)
    """
    
    # Gate 1: ATR ratio check (inclusive both ends)
    min_atr, max_atr = GATES_V2["atr_ratio"]
    if not (min_atr <= atr_ratio <= max_atr):
        return False, "gate_atr_ratio"
    
    # Gate 2: Trend filter (inclusive)
    # Close(T) >= SMA50(T-1)
    if not (close_t >= sma50_t_minus_1 * GATES_V2["trend_filter"]):
        return False, "gate_trend_filter"
    
    # Gate 3: Pullback band (inclusive both ends)
    min_pullback, max_pullback = GATES_V2["pullback_band"]
    pullback_decimal = pullback_pct / 100.0  # Convert to decimal
    if not (min_pullback <= pullback_decimal <= max_pullback):
        return False, "gate_pullback_band"
    
    # All gates passed
    return True, None


def get_gate_config() -> dict:
    """Get current gate configuration."""
    return GATES_V2.copy()


def format_gate_failure(reason: str) -> str:
    """Format gate failure reason for display.
    
    Args:
        reason: Gate failure code
    
    Returns:
        Human-readable failure message
    """
    messages = {
        "gate_atr_ratio": f"ATR ratio outside {GATES_V2['atr_ratio'][0]:.1%}-{GATES_V2['atr_ratio'][1]:.1%}",
        "gate_trend_filter": "Below 50-day moving average",
        "gate_pullback_band": f"Pullback outside {GATES_V2['pullback_band'][0]:.0%}-{GATES_V2['pullback_band'][1]:.0%} range"
    }
    return messages.get(reason, reason)