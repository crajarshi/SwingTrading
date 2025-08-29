"""Percentile ranking system with winsorization."""

from typing import List, Tuple
import math


def percentile(values: List[float], pcts: List[float]) -> List[float]:
    """Calculate percentiles of a dataset.
    
    Args:
        values: List of values
        pcts: List of percentiles to calculate (0-100)
    
    Returns:
        List of percentile values
    """
    if not values:
        return [0.0] * len(pcts)
    
    sorted_values = sorted(values)
    n = len(sorted_values)
    results = []
    
    for pct in pcts:
        if pct <= 0:
            results.append(sorted_values[0])
        elif pct >= 100:
            results.append(sorted_values[-1])
        else:
            # Linear interpolation
            pos = (pct / 100) * (n - 1)
            lower = int(pos)
            upper = min(lower + 1, n - 1)
            weight = pos - lower
            results.append(sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight)
    
    return results


def winsorize(values: List[float], lower_pct: float = 1, upper_pct: float = 99) -> List[float]:
    """Winsorize values at specified percentiles.
    
    Args:
        values: List of values to winsorize
        lower_pct: Lower percentile cutoff (default 1)
        upper_pct: Upper percentile cutoff (default 99)
    
    Returns:
        Winsorized values
    """
    if not values:
        return []
    
    # Calculate cutoff values
    cutoffs = percentile(values, [lower_pct, upper_pct])
    lower_cutoff, upper_cutoff = cutoffs[0], cutoffs[1]
    
    # Clip values to cutoffs
    return [max(lower_cutoff, min(upper_cutoff, v)) for v in values]


def calculate_percentile_rank(values_252: List[float], current_value: float) -> float:
    """Calculate percentile rank with winsorization.
    
    CRITICAL: values_252 must be strictly ≤ T-1 (excludes current).
    
    Process:
    1. Winsorize values_252 at 1st/99th percentile
    2. Count values ≤ current_value  
    3. Return 100 * count / 252
    
    Args:
        values_252: Last 252 observations (strictly ≤ T-1)
        current_value: Current value to rank
    
    Returns:
        Percentile rank (0-100)
    """
    if not values_252:
        return 50.0  # Default to median if no history
    
    # Step 1: Winsorize at 1st/99th percentile
    winsorized = winsorize(values_252, 1, 99)
    
    # Step 2: Count values ≤ current (tie handling: use "≤")
    count = sum(1 for v in winsorized if v <= current_value)
    
    # Step 3: Calculate percentile
    pct_rank = 100.0 * count / len(winsorized)
    
    return pct_rank


def build_percentile_series(
    historical_values: List[float],
    lookback: int = 252
) -> List[float]:
    """Build time series of percentiles for EMA calculation.
    
    CRITICAL: Each percentile uses 252-day window excluding current day.
    
    Args:
        historical_values: Full history of raw feature values
        lookback: Window size for percentile calculation (default 252)
    
    Returns:
        Time series of percentiles
    """
    if len(historical_values) < lookback + 1:
        return []
    
    percentiles = []
    
    # Start from day 252 (need 252 prior days)
    for i in range(lookback, len(historical_values)):
        # Window: [i-252:i] excludes current position i
        window = historical_values[i-lookback:i]
        current = historical_values[i]
        pct = calculate_percentile_rank(window, current)
        percentiles.append(pct)
    
    return percentiles


def calculate_component_percentiles(
    pullback_raw: float,
    trend_raw: float, 
    rsi_room_raw: float,
    volume_uplift_raw: float,
    historical_data: dict
) -> dict:
    """Calculate percentiles for all components.
    
    Args:
        pullback_raw: Current pullback value
        trend_raw: Current trend value
        rsi_room_raw: Current RSI room value
        volume_uplift_raw: Current volume uplift value
        historical_data: Dict with historical series for each component
    
    Returns:
        Dict with percentile for each component
    """
    results = {}
    
    # Pullback percentile
    if 'pullback_history' in historical_data:
        window = historical_data['pullback_history'][-252:]
        results['pullback_pct'] = calculate_percentile_rank(window, pullback_raw)
    else:
        results['pullback_pct'] = 50.0
    
    # Trend percentile
    if 'trend_history' in historical_data:
        window = historical_data['trend_history'][-252:]
        results['trend_pct'] = calculate_percentile_rank(window, trend_raw)
    else:
        results['trend_pct'] = 50.0
    
    # RSI room percentile
    if 'rsi_room_history' in historical_data:
        window = historical_data['rsi_room_history'][-252:]
        results['rsi_room_pct'] = calculate_percentile_rank(window, rsi_room_raw)
    else:
        results['rsi_room_pct'] = 50.0
    
    # Volume uplift percentile
    if 'volume_uplift_history' in historical_data:
        window = historical_data['volume_uplift_history'][-252:]
        results['volume_uplift_pct'] = calculate_percentile_rank(window, volume_uplift_raw)
    else:
        results['volume_uplift_pct'] = 50.0
    
    return results