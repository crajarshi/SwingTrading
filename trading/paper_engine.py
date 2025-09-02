"""Paper trading engine for order intent generation.

Deterministic construction of order intents from scan results and configuration.
Handles sizing, filtering, and portfolio constraints.
"""

import math
import json
import logging
from pathlib import Path
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple
import pandas as pd

logger = logging.getLogger(__name__)


def generate_run_id(as_of: date) -> str:
    """Generate unique run ID for this execution.
    
    Args:
        as_of: Date of the run
        
    Returns:
        Run ID string (e.g., "2025-01-15_scan")
    """
    return f"{as_of.isoformat()}_scan"


def filter_candidates(
    scan_df: pd.DataFrame,
    min_score: float,
    exclusions: Dict
) -> pd.DataFrame:
    """Filter scan results by score and exclusions.
    
    Args:
        scan_df: DataFrame with scan results
        min_score: Minimum score threshold
        exclusions: Dict with exclusion settings
        
    Returns:
        Filtered DataFrame
    """
    if scan_df.empty:
        return scan_df
    
    # Filter by minimum score
    filtered = scan_df[scan_df['score'] >= min_score].copy()
    
    # Apply leveraged ETF exclusion
    if exclusions.get('leverage_etf', True):
        patterns = exclusions.get('leverage_patterns', [])
        if patterns:
            # Remove any symbols matching leveraged ETF patterns
            mask = ~filtered['symbol'].isin(patterns)
            filtered = filtered[mask]
    
    # Apply earnings exclusion (if earnings data available)
    earnings_map = exclusions.get('earnings_map', {})
    if earnings_map and exclusions.get('earnings_within_days'):
        days_threshold = exclusions['earnings_within_days']
        today = date.today()
        
        def has_upcoming_earnings(symbol):
            if symbol not in earnings_map:
                return False
            earnings_date = earnings_map[symbol]
            if isinstance(earnings_date, str):
                earnings_date = datetime.fromisoformat(earnings_date).date()
            days_until = (earnings_date - today).days
            return 0 <= days_until <= days_threshold
        
        mask = ~filtered['symbol'].apply(has_upcoming_earnings)
        filtered = filtered[mask]
    
    logger.info(f"Filtered {len(scan_df)} candidates to {len(filtered)} "
               f"(min_score={min_score})")
    
    return filtered


def apply_price_guards(
    df: pd.DataFrame,
    min_price: float = 2.0,
    allow_pennies: bool = False
) -> pd.DataFrame:
    """Apply price-based filtering to prevent penny stock issues.
    
    Args:
        df: DataFrame with 'close' column
        min_price: Minimum price threshold
        allow_pennies: If True, override min_price check
        
    Returns:
        Filtered DataFrame
    """
    if df.empty or allow_pennies:
        return df
    
    # Filter by minimum price
    filtered = df[df['close'] >= min_price].copy()
    
    logger.info(f"Price guard: {len(df)} -> {len(filtered)} symbols "
               f"(min_price=${min_price:.2f})")
    
    return filtered


def compute_position_size(
    equity: float,
    entry_price: float,
    atr: float,
    stop_mult: float,
    risk_pct: float,
    min_notional: float,
    max_pos_pct: float
) -> int:
    """Compute position size using risk-based sizing.
    
    Args:
        equity: Account equity
        entry_price: Entry price per share
        atr: Average True Range
        stop_mult: Stop distance in ATR multiples
        risk_pct: Risk per trade as % of equity
        min_notional: Minimum position value
        max_pos_pct: Max position as % of equity
        
    Returns:
        Number of shares (0 if constraints not met)
    """
    # Calculate risk per share (stop distance)
    risk_per_share = atr * stop_mult
    
    # Calculate shares based on risk
    if risk_per_share > 0:
        dollar_risk = equity * (risk_pct / 100)
        shares = dollar_risk / risk_per_share
    else:
        shares = 0
    
    # Round down to integer
    shares = int(math.floor(shares))
    
    # Apply constraints
    if shares < 1:
        return 0
    
    # Check minimum notional
    position_value = shares * entry_price
    if position_value < min_notional:
        return 0
    
    # Check maximum position size
    max_position_value = equity * (max_pos_pct / 100)
    if position_value > max_position_value:
        # Reduce shares to fit within max
        shares = int(math.floor(max_position_value / entry_price))
        # Re-check minimum after reduction
        if shares * entry_price < min_notional:
            return 0
    
    return shares


def compute_safe_position_size(
    equity: float,
    price: float,
    atr: float,
    stop_mult: float,
    risk_pct: float,
    min_notional: float = 200,
    max_pos_pct: float = 0.10
) -> int:
    """Compute position size with all safety guards.
    
    Enhanced version with additional safety checks.
    
    Args:
        equity: Account equity
        price: Current price
        atr: Average True Range
        stop_mult: Stop distance multiplier
        risk_pct: Risk percentage
        min_notional: Minimum position value
        max_pos_pct: Max position as decimal (0.10 = 10%)
        
    Returns:
        Safe number of shares
    """
    # Basic calculation
    shares = compute_position_size(
        equity=equity,
        entry_price=price,
        atr=atr,
        stop_mult=stop_mult,
        risk_pct=risk_pct,
        min_notional=min_notional,
        max_pos_pct=max_pos_pct * 100  # Convert to percentage
    )
    
    # Additional guard: prevent huge share counts for low-price stocks
    if price < 5 and shares > 5000:
        shares = 5000  # Cap at 5000 shares for stocks under $5
    elif price < 1 and shares > 2000:
        shares = 2000  # Cap at 2000 shares for stocks under $1
    
    return shares


def construct_entry_leg(
    style: str,
    ref_price: float,
    buffer_bps: int
) -> Dict:
    """Construct entry order leg configuration.
    
    Args:
        style: "open" or "market-now"
        ref_price: Reference price (close)
        buffer_bps: Basis points buffer for limit orders
        
    Returns:
        Entry leg configuration dict
    """
    if style == "open":
        # Limit-on-open with buffer
        buffer_mult = 1 + (buffer_bps / 10000)
        limit_price = round(ref_price * buffer_mult, 2)
        
        return {
            "type": "limit",
            "time_in_force": "opg",
            "limit_price": limit_price,
            "open_only": True
        }
    else:
        # Market order now
        return {
            "type": "market",
            "time_in_force": "day",
            "limit_price": None,
            "open_only": False
        }


def construct_bracket_levels(
    entry_price: float,
    atr: float,
    stop_mult: float,
    target_mult: float
) -> Tuple[float, float]:
    """Calculate stop loss and take profit levels.
    
    Args:
        entry_price: Entry price
        atr: Average True Range
        stop_mult: Stop distance in ATR multiples
        target_mult: Target distance in ATR multiples
        
    Returns:
        Tuple of (stop_loss, take_profit) prices
    """
    stop_loss = round(entry_price - (atr * stop_mult), 2)
    take_profit = round(entry_price + (atr * target_mult), 2)
    
    # Ensure stop is not negative
    stop_loss = max(0.01, stop_loss)
    
    return stop_loss, take_profit


def enforce_portfolio_caps(
    intents: List[Dict],
    account_equity: float,
    max_symbols: int,
    max_gross_exposure_pct: float
) -> List[Dict]:
    """Apply portfolio-level constraints to order intents.
    
    Args:
        intents: List of order intents
        account_equity: Current account equity
        max_symbols: Maximum number of positions
        max_gross_exposure_pct: Max total exposure as %
        
    Returns:
        Filtered list of intents that fit within constraints
    """
    if not intents:
        return intents
    
    # Sort by score (highest first)
    sorted_intents = sorted(intents, key=lambda x: x['meta']['score'], reverse=True)
    
    selected = []
    total_exposure = 0
    max_exposure = account_equity * (max_gross_exposure_pct / 100)
    
    for intent in sorted_intents:
        # Check symbol count
        if len(selected) >= max_symbols:
            break
        
        # Calculate position value
        qty = intent['qty']
        price = intent['entry'].get('limit_price') or intent['meta'].get('close', 0)
        position_value = qty * price
        
        # Check exposure limit
        if total_exposure + position_value > max_exposure:
            continue
        
        selected.append(intent)
        total_exposure += position_value
    
    logger.info(f"Portfolio caps: {len(intents)} -> {len(selected)} intents "
               f"(exposure=${total_exposure:.0f})")
    
    return selected


def derive_candidate_reason(row: pd.Series) -> str:
    """Generate human-readable reason for candidate selection.
    
    Args:
        row: Pandas Series with candidate data
        
    Returns:
        Reason string
    """
    reasons = []
    
    # Score-based reason
    score = row.get('score', 0)
    if score >= 80:
        reasons.append("high-score")
    elif score >= 65:
        reasons.append("qualified-score")
    
    # RSI-based reason
    rsi = row.get('rsi14', 50)
    if rsi < 30:
        reasons.append("oversold")
    elif rsi < 50:
        reasons.append("pullback")
    
    # Trend reason
    if 'sma50' in row and 'close' in row:
        if row['close'] > row['sma50']:
            reasons.append("above-trend")
    
    # Volume reason
    if 'volume_ratio' in row and row['volume_ratio'] > 1.5:
        reasons.append("high-volume")
    
    return " ".join(reasons) if reasons else "score-qualified"


def generate_fallback_strategy(broker_caps: Dict) -> str:
    """Determine order placement strategy based on broker capabilities.
    
    Args:
        broker_caps: Dict with broker capability flags
        
    Returns:
        Strategy string: 'opg_bracket', 'opg_then_oco', or 'day_bracket'
    """
    if broker_caps.get('supports_opg_bracket', False):
        return 'opg_bracket'
    elif broker_caps.get('supports_opg', True):
        return 'opg_then_oco'
    else:
        return 'day_bracket'


def build_order_intents(
    scan_df: pd.DataFrame,
    config: Dict,
    account_equity: float,
    open_positions: List[Dict],
    as_of: date
) -> Tuple[List[Dict], Dict]:
    """Build complete order intents from scan results.
    
    Args:
        scan_df: DataFrame with scan results
        config: Paper trading configuration
        account_equity: Current account equity
        open_positions: List of existing positions
        as_of: Date for this run
        
    Returns:
        Tuple of (intents list, summary dict)
    """
    run_id = generate_run_id(as_of)
    
    # Extract config sections
    entry_config = config.get('entry', {})
    sizing_config = config.get('sizing', {})
    risk_config = config.get('risk', {})
    order_config = config.get('order', {})
    exclusions = config.get('exclusions', {})
    
    # Filter candidates
    filtered = filter_candidates(scan_df, entry_config['min_score'], exclusions)
    
    # Apply price guards
    filtered = apply_price_guards(
        filtered,
        sizing_config.get('min_price', 2.0),
        sizing_config.get('allow_penny_stocks', False)
    )
    
    # Sort by score (and secondary criteria)
    sort_by = entry_config.get('sort_by', 'score')
    if sort_by == 'score':
        filtered = filtered.sort_values('score', ascending=False)
    elif sort_by == 'rsi_room' and 'rsi14' in filtered.columns:
        filtered['rsi_room'] = 70 - filtered['rsi14']
        filtered = filtered.sort_values('rsi_room', ascending=False)
    
    # Get existing symbols to avoid duplicates
    existing_symbols = {pos['symbol'] for pos in open_positions}
    
    # Build intents
    intents = []
    skipped = {'insufficient_data': 0, 'sizing_failed': 0, 'duplicate': 0}
    
    for _, row in filtered.iterrows():
        symbol = row['symbol']
        
        # Skip if already have position
        if symbol in existing_symbols:
            skipped['duplicate'] += 1
            continue
        
        # Required fields check
        if 'close' not in row or 'atr20' not in row:
            skipped['insufficient_data'] += 1
            continue
        
        close = row['close']
        atr = row.get('atr20', close * 0.02)  # Default 2% if missing
        
        # Calculate position size
        qty = compute_safe_position_size(
            equity=account_equity,
            price=close,
            atr=atr,
            stop_mult=risk_config['stop_atr_mult'],
            risk_pct=sizing_config['risk_per_trade_pct'],
            min_notional=sizing_config['min_notional'],
            max_pos_pct=sizing_config['max_pos_pct_of_equity'] / 100
        )
        
        if qty == 0:
            skipped['sizing_failed'] += 1
            continue
        
        # Construct entry
        entry_leg = construct_entry_leg(
            style=order_config['entry_style'],
            ref_price=close,
            buffer_bps=order_config['price_buffer_bps']
        )
        
        # Calculate bracket levels - use close price for market orders
        entry_price = entry_leg.get('limit_price') if entry_leg.get('limit_price') else close
        stop_loss, take_profit = construct_bracket_levels(
            entry_price=entry_price,
            atr=atr,
            stop_mult=risk_config['stop_atr_mult'],
            target_mult=risk_config['target_atr_mult']
        )
        
        # Build intent
        intent = {
            "run_id": run_id,
            "symbol": symbol,
            "side": "buy",
            "qty": qty,
            "entry": entry_leg,
            "bracket": {
                "stop_loss": stop_loss,
                "take_profit": take_profit
            },
            "meta": {
                "score": row['score'],
                "atr": atr,
                "rsi14": row.get('rsi14', 0),
                "sma50": row.get('sma50'),
                "close": close,
                "reason": derive_candidate_reason(row)
            },
            "client_order_id": f"{run_id}:{symbol}:{as_of.isoformat()}"
        }
        
        intents.append(intent)
    
    # Apply portfolio caps
    final_intents = enforce_portfolio_caps(
        intents,
        account_equity,
        entry_config['max_symbols'],
        sizing_config['max_gross_exposure_pct']
    )
    
    # Build summary
    summary = {
        "candidates": len(scan_df),
        "filtered": len(filtered),
        "selected": len(final_intents),
        "skipped": skipped,
        "run_id": run_id,
        "as_of": as_of.isoformat()
    }
    
    logger.info(f"Built {len(final_intents)} order intents from {len(scan_df)} candidates")
    
    return final_intents, summary


def serialize_intents(intents: List[Dict], out_path: Path) -> Path:
    """Save intents to JSON file.
    
    Args:
        intents: List of order intents
        out_path: Output file path
        
    Returns:
        Path to saved file
    """
    # Ensure directory exists
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Write JSON
    with open(out_path, 'w') as f:
        json.dump(intents, f, indent=2, default=str)
    
    logger.info(f"Saved {len(intents)} intents to {out_path}")
    
    return out_path