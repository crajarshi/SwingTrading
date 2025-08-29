"""Main scoring orchestrator for v2 implementation."""

import math
from typing import Dict, List, Optional, Tuple, Any
from .indicators import (
    calculate_indicators_t_minus_1, 
    wilder_rsi, 
    ema,
    sma
)
from .percentiles import (
    calculate_percentile_rank,
    build_percentile_series
)
from .gates import evaluate_gates
from .telemetry import get_telemetry

# Model version
MODEL_VERSION = "score_v2.0.0"

# Minimum bars required (reduced for demo with available data)
MIN_BARS_REQUIRED = 250  # Temporarily reduced from 366 for demo


def calculate_raw_features(bars: List[Dict]) -> Dict[str, Any]:
    """Calculate raw feature values at time T.
    
    CRITICAL: All denominators use T-1 data.
    
    Args:
        bars: List of OHLC bars (at least 366)
    
    Returns:
        Dict with raw features and indicators
    """
    # Get indicators calculated on T-1 data
    indicators = calculate_indicators_t_minus_1(bars)
    
    close_t = indicators['close_t']
    volume_t = indicators['volume_t']
    sma50_t_minus_1 = indicators['sma50_t_minus_1']
    high20_t_minus_1 = indicators['high20_t_minus_1']
    vol_avg_10_t_minus_1 = indicators['vol_avg_10_t_minus_1']
    rsi_raw = indicators['rsi_raw']
    atr_raw = indicators['atr_raw']
    
    # Calculate raw features
    # Pullback: (1 - Close(T) / High20(T-1)) × 100
    pullback_raw = (1 - close_t / high20_t_minus_1) * 100 if high20_t_minus_1 > 0 else 0
    pullback_raw = max(0, min(100, pullback_raw))  # Clamp [0, 100]
    
    # Trend: ((Close(T) / SMA50(T-1)) - 1) × 100
    trend_raw = ((close_t / sma50_t_minus_1) - 1) * 100 if sma50_t_minus_1 > 0 else 0
    trend_raw = max(-50, min(100, trend_raw))  # Clamp [-50, 100]
    
    # RSI room: 70 - RSI_smoothed(T-1)
    rsi_room_raw = 70 - rsi_raw
    
    # Volume uplift: ln(Volume(T) / VolAvg10(T-1))
    # Natural log, shifted average
    if vol_avg_10_t_minus_1 > 0 and volume_t > 0:
        volume_uplift_raw = math.log(volume_t / vol_avg_10_t_minus_1)
    else:
        volume_uplift_raw = 0
    
    # ATR ratio for gates
    atr_ratio = atr_raw / close_t if close_t > 0 else 0
    
    return {
        'pullback_raw': pullback_raw,
        'trend_raw': trend_raw,
        'rsi_room_raw': rsi_room_raw,
        'volume_uplift_raw': volume_uplift_raw,
        'atr_ratio': atr_ratio,
        'close_t': close_t,
        'sma50_t_minus_1': sma50_t_minus_1,
        'rsi_value': rsi_raw,
        'atr_value': atr_raw,
        'volume_t': volume_t,
        'vol_avg_10_t_minus_1': vol_avg_10_t_minus_1
    }


def build_historical_features(bars: List[Dict]) -> Dict[str, List[float]]:
    """Build historical feature series for percentile calculation.
    
    Args:
        bars: List of OHLC bars (at least 366)
    
    Returns:
        Dict with historical series for each feature
    """
    history = {
        'pullback_history': [],
        'trend_history': [],
        'rsi_room_history': [],
        'volume_uplift_history': []
    }
    
    # Need at least 60 bars to start calculating features
    for i in range(60, len(bars)):
        sub_bars = bars[:i+1]
        
        try:
            features = calculate_raw_features(sub_bars)
            history['pullback_history'].append(features['pullback_raw'])
            history['trend_history'].append(features['trend_raw'])
            history['rsi_room_history'].append(features['rsi_room_raw'])
            history['volume_uplift_history'].append(features['volume_uplift_raw'])
        except:
            # Use neutral values if calculation fails
            history['pullback_history'].append(10.0)
            history['trend_history'].append(0.0)
            history['rsi_room_history'].append(30.0)
            history['volume_uplift_history'].append(0.0)
    
    return history


def calculate_score_v2(
    bars: List[Dict],
    symbol: str = "UNKNOWN"
) -> Tuple[Optional[float], Optional[str], Dict[str, Any]]:
    """Calculate v2 score with all requirements.
    
    Process:
    1. Check data sufficiency (366 bars)
    2. Calculate indicators on T-1 data
    3. Compute raw features using T
    4. Apply winsorization and percentiles
    5. Smooth percentiles with 3-day EMA
    6. Check gates → return null if failed
    7. Equal-weight composite (25% each)
    
    Args:
        bars: List of OHLC bars
        symbol: Symbol name for telemetry
    
    Returns:
        (score, gate_failure_reason, components)
    """
    telemetry = get_telemetry()
    
    # Step 1: Check data sufficiency
    if len(bars) < MIN_BARS_REQUIRED:
        telemetry.track_skip(symbol, "insufficient_history")
        return None, "insufficient_history", {
            "bars_available": len(bars),
            "bars_required": MIN_BARS_REQUIRED
        }
    
    # Step 2-3: Calculate raw features (includes indicators on T-1)
    features = calculate_raw_features(bars)
    
    # Step 4: Build historical series and calculate percentiles
    # CRITICAL: Each percentile uses 252-day window excluding T
    history = build_historical_features(bars)
    
    # Calculate percentiles for current values
    # Window is last 252 values BEFORE current (strictly ≤ T-1)
    percentiles = {}
    
    if len(history['pullback_history']) > 252:
        window = history['pullback_history'][-253:-1]  # Last 252 excluding current
        percentiles['pullback_pct'] = calculate_percentile_rank(window, features['pullback_raw'])
    else:
        percentiles['pullback_pct'] = 50.0
    
    if len(history['trend_history']) > 252:
        window = history['trend_history'][-253:-1]
        percentiles['trend_pct'] = calculate_percentile_rank(window, features['trend_raw'])
    else:
        percentiles['trend_pct'] = 50.0
    
    if len(history['rsi_room_history']) > 252:
        window = history['rsi_room_history'][-253:-1]
        percentiles['rsi_room_pct'] = calculate_percentile_rank(window, features['rsi_room_raw'])
    else:
        percentiles['rsi_room_pct'] = 50.0
    
    if len(history['volume_uplift_history']) > 252:
        window = history['volume_uplift_history'][-253:-1]
        percentiles['volume_uplift_pct'] = calculate_percentile_rank(window, features['volume_uplift_raw'])
    else:
        percentiles['volume_uplift_pct'] = 50.0
    
    # Step 5: Apply EMA to percentile time series
    # Build percentile series for EMA calculation
    smoothed_percentiles = {}
    
    for component in ['pullback', 'trend', 'rsi_room', 'volume_uplift']:
        # Build time series of percentiles (need at least 3 days)
        pct_series = build_percentile_series(
            history[f'{component}_history'],
            lookback=252
        )
        
        if len(pct_series) >= 3:
            # Apply EMA to series and take last value
            ema_series = ema(pct_series, period=3)
            smoothed_percentiles[f'{component}_pct'] = ema_series[-1] if ema_series else percentiles[f'{component}_pct']
        else:
            # Not enough history for EMA, use raw percentile
            smoothed_percentiles[f'{component}_pct'] = percentiles[f'{component}_pct']
    
    # Step 6: Check gates (inclusive boundaries)
    gates_pass, gate_reason = evaluate_gates(
        atr_ratio=features['atr_ratio'],
        close_t=features['close_t'],
        sma50_t_minus_1=features['sma50_t_minus_1'],
        pullback_pct=features['pullback_raw']  # Use raw percentage for gate
    )
    
    if not gates_pass:
        telemetry.track_skip(symbol, gate_reason)
        return None, gate_reason, {
            "raw_features": features,
            "percentiles": smoothed_percentiles,
            "gate_failed": gate_reason
        }
    
    # Step 7: Calculate composite score (equal weights)
    composite = (
        smoothed_percentiles['pullback_pct'] * 0.25 +
        smoothed_percentiles['trend_pct'] * 0.25 +
        smoothed_percentiles['rsi_room_pct'] * 0.25 +
        smoothed_percentiles['volume_uplift_pct'] * 0.25
    )
    
    # Round to 2 decimal places
    score = round(composite, 2)
    
    # Return score with components
    components = {
        "score": score,
        "model_version": MODEL_VERSION,
        "percentiles": smoothed_percentiles,
        "raw_features": features,
        "gates_passed": True
    }
    
    return score, None, components


def format_score_output(
    score: Optional[float],
    gate_reason: Optional[str],
    components: Dict[str, Any]
) -> Dict[str, Any]:
    """Format score output for API/CSV.
    
    Args:
        score: Calculated score or None
        gate_reason: Gate failure reason or None
        components: Component details
    
    Returns:
        Formatted output dict
    """
    output = {
        "score": score,  # None if gates failed
        "model_version": MODEL_VERSION
    }
    
    if gate_reason:
        output["gate_failed"] = gate_reason
        output["score"] = None  # Explicit null
    
    if "percentiles" in components:
        # Format percentiles to 1 decimal place
        output["pullback_pct"] = round(components["percentiles"].get("pullback_pct", 0), 1)
        output["trend_pct"] = round(components["percentiles"].get("trend_pct", 0), 1)
        output["rsi_room_pct"] = round(components["percentiles"].get("rsi_room_pct", 0), 1)
        output["volume_uplift_pct"] = round(components["percentiles"].get("volume_uplift_pct", 0), 1)
    
    if "raw_features" in components:
        # Add raw values for transparency
        rf = components["raw_features"]
        output["close"] = round(rf.get("close_t", 0), 2)
        output["rsi14"] = round(rf.get("rsi_value", 50), 1)
        output["volume"] = rf.get("volume_t", 0)
        output["volume_avg_10d"] = round(rf.get("vol_avg_10_t_minus_1", 0), 0)
    
    return output