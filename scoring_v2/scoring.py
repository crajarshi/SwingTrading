"""Main scoring orchestrator for v2 implementation."""

import math
import numpy as np
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
from .gates import evaluate_gates, validate_score_range, validate_dollar_volume
from .telemetry import get_telemetry
from .market_regime import market_regime_detector, get_regime_adjusted_weights, should_trade_in_regime

# Model version
MODEL_VERSION = "score_v2.1.0"  # Updated with optimized weights based on backtest results

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
    dollar_volume_t = indicators['dollar_volume_t']
    dollar_volume_avg = indicators['dollar_volume_avg']
    volume_avg = indicators['vol_avg_10_t_minus_1']  # 10-day volume average
    rsi_raw = indicators['rsi_raw']
    atr_raw = indicators['atr_raw']
    
    # Calculate raw features
    # Pullback: (1 - Close(T) / High20(T-1)) × 100
    pullback_raw = (1 - close_t / high20_t_minus_1) * 100 if high20_t_minus_1 > 0 else 0
    pullback_raw = max(0, min(100, pullback_raw))  # Clamp [0, 100]
    
    # Trend with quality metrics
    from .indicators import calculate_trend_quality, sma
    
    # Get SMA50 history for trend quality (last 20 days)
    sma50_history = []
    for i in range(max(50, len(bars)-20), len(bars)):
        sma50_history.append(sma([b['c'] for b in bars[:i]], 50))
    
    trend_quality = calculate_trend_quality(sma50_history, period=20)
    
    # Combine position, slope, and R²
    trend_position = ((close_t / sma50_t_minus_1) - 1) * 100 if sma50_t_minus_1 > 0 else 0
    trend_composite = (
        trend_position * 0.6 +  # 60% weight to position
        trend_quality['slope'] * 20 * 0.3 +  # 30% to slope (scaled)
        trend_quality['r_squared'] * 100 * 0.1  # 10% to R²
    )
    trend_raw = max(-50, min(100, trend_composite))  # Clamp [-50, 100]
    
    # RSI raw value (for percentile calculation, not room)
    rsi_raw_value = rsi_raw
    
    # Enhanced volume analysis
    # 1. Base dollar volume uplift: ln(DollarVolume(T) / DollarVolumeAvg(T-1))
    if dollar_volume_avg > 0 and dollar_volume_t > 0:
        base_volume_uplift = math.log(dollar_volume_t / dollar_volume_avg)
    else:
        base_volume_uplift = 0

    # 2. Volume momentum (3-day trend)
    volume_momentum = 0
    if len(bars) >= 5:
        recent_volumes = [bars[i]['v'] for i in range(-3, 0)]
        older_volumes = [bars[i]['v'] for i in range(-6, -3)]

        recent_avg = np.mean(recent_volumes)
        older_avg = np.mean(older_volumes)

        if older_avg > 0:
            volume_momentum = math.log(recent_avg / older_avg)

    # 3. Institutional flow indicator (large volume days in last 10 days)
    institutional_flow = 0
    if len(bars) >= 10:
        large_volume_days = 0
        for i in range(-10, 0):
            if bars[i]['v'] > volume_avg * 1.5:  # 50% above average
                large_volume_days += 1
        institutional_flow = (large_volume_days / 10) * 2 - 1  # Scale to -1 to +1

    # 4. Volume-price relationship (accumulation vs distribution)
    volume_price_relationship = 0
    if len(bars) >= 5:
        up_volume = 0
        down_volume = 0
        for i in range(-5, 0):
            if i > -len(bars):
                price_change = bars[i]['c'] - bars[i-1]['c'] if i > -len(bars) else 0
                if price_change > 0:
                    up_volume += bars[i]['v']
                elif price_change < 0:
                    down_volume += bars[i]['v']

        total_volume = up_volume + down_volume
        if total_volume > 0:
            volume_price_relationship = (up_volume / total_volume - 0.5) * 2  # Scale to -1 to +1

    # Composite volume score (weighted combination)
    dollar_volume_uplift_raw = (
        base_volume_uplift * 0.5 +           # Base uplift (50%)
        volume_momentum * 0.25 +             # Momentum (25%)
        institutional_flow * 0.15 +          # Institutional interest (15%)
        volume_price_relationship * 0.10     # Accumulation/distribution (10%)
    )
    
    # ATR ratio for gates
    atr_ratio = atr_raw / close_t if close_t > 0 else 0
    
    return {
        'pullback_raw': pullback_raw,
        'trend_raw': trend_raw,
        'rsi_raw_value': rsi_raw_value,  # Changed from rsi_room_raw
        'dollar_volume_uplift_raw': dollar_volume_uplift_raw,  # Changed from volume_uplift_raw
        'atr_ratio': atr_ratio,
        'close_t': close_t,
        'sma50_t_minus_1': sma50_t_minus_1,
        'rsi_value': rsi_raw,
        'atr_value': atr_raw,
        'dollar_volume_t': dollar_volume_t,
        'dollar_volume_avg': dollar_volume_avg,
        'trend_slope': trend_quality['slope'],
        'trend_r2': trend_quality['r_squared']
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
        'rsi_history': [],  # Changed from rsi_room_history
        'dollar_volume_uplift_history': []  # Changed from volume_uplift_history
    }
    
    # Need at least 60 bars to start calculating features
    for i in range(60, len(bars)):
        sub_bars = bars[:i+1]
        
        try:
            features = calculate_raw_features(sub_bars)
            history['pullback_history'].append(features['pullback_raw'])
            history['trend_history'].append(features['trend_raw'])
            history['rsi_history'].append(features['rsi_raw_value'])  # Store actual RSI
            history['dollar_volume_uplift_history'].append(features['dollar_volume_uplift_raw'])
        except:
            # Use neutral values if calculation fails
            history['pullback_history'].append(10.0)
            history['trend_history'].append(0.0)
            history['rsi_history'].append(50.0)  # Neutral RSI
            history['dollar_volume_uplift_history'].append(0.0)
    
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
    
    # Check dollar volume filter ($20M minimum)
    if features.get('dollar_volume_t', 0) < 20_000_000:
        telemetry.track_skip(symbol, "insufficient_liquidity")
        return None, "insufficient_liquidity", {
            "dollar_volume": features.get('dollar_volume_t', 0),
            "required": 20_000_000
        }
    
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
    
    if len(history['rsi_history']) > 252:
        window = history['rsi_history'][-253:-1]
        # RSI percentile: higher RSI = higher percentile (direct, not inverted)
        percentiles['rsi_pct'] = calculate_percentile_rank(window, features['rsi_raw_value'])
    else:
        percentiles['rsi_pct'] = 50.0
    
    if len(history['dollar_volume_uplift_history']) > 252:
        window = history['dollar_volume_uplift_history'][-253:-1]
        percentiles['dollar_volume_uplift_pct'] = calculate_percentile_rank(window, features['dollar_volume_uplift_raw'])
    else:
        percentiles['dollar_volume_uplift_pct'] = 50.0
    
    # Step 5: Apply EMA to percentile time series
    # Build percentile series for EMA calculation
    smoothed_percentiles = {}
    
    for component in ['pullback', 'trend', 'rsi', 'dollar_volume_uplift']:
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
    
    # Step 7: Get market regime and adjust weights accordingly
    try:
        market_regime = market_regime_detector.get_market_regime()

        # Check if we should trade in current regime
        should_trade, regime_reason = should_trade_in_regime(market_regime)
        if not should_trade and regime_reason == "extreme_volatility":
            telemetry.track_skip(symbol, regime_reason)
            return None, regime_reason, {
                "raw_features": features,
                "percentiles": smoothed_percentiles,
                "market_regime": market_regime,
                "gate_failed": regime_reason
            }

        # Base weights optimized from backtest results
        base_weights = {
            'pullback': 0.35,    # Most predictive
            'volume': 0.30,      # Strong signal
            'trend': 0.20,       # Less predictive at extremes
            'rsi': 0.15          # Supportive but not primary
        }

        # Adjust weights based on market regime
        adjusted_weights = get_regime_adjusted_weights(base_weights, market_regime)

        # Calculate composite score with regime-adjusted weights
        composite = (
            smoothed_percentiles['pullback_pct'] * adjusted_weights['pullback'] +
            smoothed_percentiles['dollar_volume_uplift_pct'] * adjusted_weights['volume'] +
            smoothed_percentiles['trend_pct'] * adjusted_weights['trend'] +
            smoothed_percentiles['rsi_pct'] * adjusted_weights['rsi']
        )

    except Exception as e:
        # Fallback to base weights if regime detection fails
        print(f"Warning: Market regime detection failed for {symbol}: {e}")
        market_regime = {'trend_regime': 'neutral', 'volatility_regime': 'medium'}
        adjusted_weights = {'pullback': 0.35, 'volume': 0.30, 'trend': 0.20, 'rsi': 0.15}

        composite = (
            smoothed_percentiles['pullback_pct'] * 0.35 +
            smoothed_percentiles['dollar_volume_uplift_pct'] * 0.30 +
            smoothed_percentiles['trend_pct'] * 0.20 +
            smoothed_percentiles['rsi_pct'] * 0.15
        )
    
    # Round to 2 decimal places
    score = round(composite, 2)

    # Step 8: Additional validations based on backtest results
    # Check dollar volume liquidity
    dollar_volume_pass, volume_reason = validate_dollar_volume(features['dollar_volume_t'])
    if not dollar_volume_pass:
        telemetry.track_skip(symbol, volume_reason)
        return None, volume_reason, {
            "raw_features": features,
            "percentiles": smoothed_percentiles,
            "score": score,
            "gate_failed": volume_reason
        }

    # Check score range (avoid overfitted high scores)
    score_range_pass, score_reason = validate_score_range(score)
    if not score_range_pass:
        telemetry.track_skip(symbol, score_reason)
        return None, score_reason, {
            "raw_features": features,
            "percentiles": smoothed_percentiles,
            "score": score,
            "gate_failed": score_reason
        }

    # Return score with components
    components = {
        "score": score,
        "model_version": MODEL_VERSION,
        "percentiles": smoothed_percentiles,
        "raw_features": features,
        "gates_passed": True,
        "market_regime": market_regime,
        "adjusted_weights": adjusted_weights
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
        # Format percentiles to 1 decimal place (new P0 keys)
        pullback_pct = round(components["percentiles"].get("pullback_pct", 0), 1)
        trend_pct = round(components["percentiles"].get("trend_pct", 0), 1)
        rsi_pct = round(components["percentiles"].get("rsi_pct", 0), 1)
        dollar_volume_uplift_pct = round(components["percentiles"].get("dollar_volume_uplift_pct", 0), 1)

        output["pullback_pct"] = pullback_pct
        output["trend_pct"] = trend_pct
        output["rsi_pct"] = rsi_pct
        output["dollar_volume_uplift_pct"] = dollar_volume_uplift_pct

        # Backward-compatible aliases for existing UI/server code
        output["rsi_room_pct"] = rsi_pct
        output["volume_uplift_pct"] = dollar_volume_uplift_pct
    
    if "raw_features" in components:
        # Add raw values for transparency
        rf = components["raw_features"]
        output["close"] = round(rf.get("close_t", 0), 2)
        output["rsi14"] = round(rf.get("rsi_value", 50), 1)
        output["volume"] = rf.get("volume_t", 0)
        output["volume_avg_10d"] = round(rf.get("vol_avg_10_t_minus_1", 0), 0)
    
    return output
