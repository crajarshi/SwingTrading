"""Technical indicators with Wilder's smoothing and T-1 exclusion."""

import math
import numpy as np
from scipy import stats
from typing import List, Dict, Optional, Tuple


def wilder_rsi(prices: List[float], period: int = 14) -> float:
    """Calculate Wilder's smoothed RSI on prices[:-1].
    
    CRITICAL: Uses data up to T-1 only (excludes current bar).
    
    Args:
        prices: Price series (will use all except last value)
        period: RSI period (default 14)
    
    Returns:
        RSI value (0-100)
    """
    if len(prices) < period + 2:  # Need at least period + 1 for T-1 exclusion
        return 50.0  # Neutral default
    
    # EXCLUDE current bar (T) - use only up to T-1
    working_prices = prices[:-1]
    
    if len(working_prices) < period + 1:
        return 50.0
    
    # Calculate price changes
    deltas = [working_prices[i] - working_prices[i-1] 
              for i in range(1, len(working_prices))]
    
    # Separate gains and losses
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]
    
    # Initial averages (SMA for first period)
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    
    # Wilder's smoothing for remaining values
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    return rsi


def wilder_atr(bars: List[Dict], period: int = 14) -> float:
    """Calculate Wilder's smoothed ATR on bars[:-1].
    
    CRITICAL: Uses data up to T-1 only (excludes current bar).
    
    Args:
        bars: List of OHLC bars with keys 'h', 'l', 'c'
        period: ATR period (default 14)
    
    Returns:
        ATR value
    """
    if len(bars) < period + 2:  # Need at least period + 1 for T-1 exclusion
        return 0.0
    
    # EXCLUDE current bar (T) - use only up to T-1
    working_bars = bars[:-1]
    
    if len(working_bars) < period + 1:
        return 0.0
    
    # Calculate True Range for each bar
    true_ranges = []
    for i in range(1, len(working_bars)):
        high = working_bars[i]['h']
        low = working_bars[i]['l']
        prev_close = working_bars[i-1]['c']
        
        # True Range = max(H-L, |H-Cprev|, |L-Cprev|)
        tr = max(
            high - low,
            abs(high - prev_close),
            abs(low - prev_close)
        )
        true_ranges.append(tr)
    
    if len(true_ranges) < period:
        return 0.0
    
    # Initial ATR (SMA for first period)
    atr = sum(true_ranges[:period]) / period
    
    # Wilder's smoothing for remaining values
    for i in range(period, len(true_ranges)):
        atr = (atr * (period - 1) + true_ranges[i]) / period
    
    return atr


def ema(values: List[float], period: int = 3) -> List[float]:
    """Calculate Exponential Moving Average.
    
    Args:
        values: Series of values
        period: EMA period (default 3)
    
    Returns:
        List of EMA values
    """
    if not values or len(values) < period:
        return values.copy() if values else []
    
    alpha = 2.0 / (period + 1)
    ema_values = []
    
    # Start with SMA for initial value
    ema_current = sum(values[:period]) / period
    ema_values.extend([ema_current] * period)
    
    # Calculate EMA for remaining values
    for i in range(period, len(values)):
        ema_current = values[i] * alpha + ema_current * (1 - alpha)
        ema_values.append(ema_current)
    
    return ema_values


def sma(values: List[float], period: int) -> float:
    """Simple Moving Average of last 'period' values.
    
    Args:
        values: Series of values
        period: SMA period
    
    Returns:
        SMA value
    """
    if len(values) < period:
        return sum(values) / len(values) if values else 0.0
    return sum(values[-period:]) / period


def calculate_dollar_volume(price: float, volume: float) -> float:
    """Calculate dollar volume (price * volume).
    
    Args:
        price: Stock price
        volume: Share volume
    
    Returns:
        Dollar volume
    """
    return price * volume


def calculate_trend_quality(sma_values: List[float], period: int = 20) -> Dict[str, float]:
    """Calculate trend slope and R² over specified period.
    
    Args:
        sma_values: List of SMA values
        period: Period for regression (default 20)
    
    Returns:
        Dict with 'slope' (normalized %) and 'r_squared' (0-1)
    """
    if len(sma_values) < period or period < 2:
        return {'slope': 0.0, 'r_squared': 0.0}
    
    # Use last 'period' values
    y = np.array(sma_values[-period:])
    x = np.arange(len(y))
    
    # Handle edge cases
    if np.std(y) == 0:  # No variation
        return {'slope': 0.0, 'r_squared': 0.0}
    
    try:
        # Linear regression
        slope, intercept, r_value, p_value, std_err = stats.linregress(x, y)
        
        # Normalize slope as % change per day
        avg_price = np.mean(y)
        slope_pct = (slope / avg_price) * 100 if avg_price > 0 else 0
        
        return {
            'slope': slope_pct,  # % per day
            'r_squared': r_value ** 2  # 0-1, higher = more consistent
        }
    except:
        return {'slope': 0.0, 'r_squared': 0.0}


def calculate_indicators_t_minus_1(bars: List[Dict]) -> Dict[str, float]:
    """Calculate all indicators using data up to T-1.
    
    CRITICAL: All rolling calculations exclude current bar.
    
    Args:
        bars: List of OHLC bars (at least 366)
    
    Returns:
        Dictionary of indicator values
    """
    if len(bars) < 366:
        raise ValueError(f"Insufficient bars: {len(bars)} < 366")
    
    # Extract price series
    closes = [bar['c'] for bar in bars]
    highs = [bar['h'] for bar in bars]
    volumes = [bar['v'] for bar in bars]
    
    # All calculations on T-1 data
    # SMA50 excluding current bar
    sma50_t_minus_1 = sma(closes[:-1], 50)
    
    # High20 excluding current bar
    high20_t_minus_1 = max(highs[-21:-1]) if len(highs) > 20 else highs[-2]
    
    # Volume average (10-day) SHIFTED - excludes today
    # VolAvg10(T-1) = mean(volumes[T-11:T-1])
    vol_avg_10_t_minus_1 = sum(volumes[-11:-1]) / 10 if len(volumes) >= 11 else volumes[-2]
    
    # RSI and ATR using Wilder's smoothing (already exclude T in function)
    rsi_raw = wilder_rsi(closes, 14)
    atr_raw = wilder_atr(bars, 14)
    
    # Calculate dollar volume metrics
    dollar_volume_t = calculate_dollar_volume(closes[-1], volumes[-1])
    
    # 10-day average dollar volume (T-11 to T-1)
    dollar_volumes_hist = [calculate_dollar_volume(bars[i]['c'], bars[i]['v']) 
                           for i in range(max(0, len(bars)-11), len(bars)-1)]
    dollar_volume_avg = sum(dollar_volumes_hist) / len(dollar_volumes_hist) if dollar_volumes_hist else dollar_volume_t
    
    return {
        'sma50_t_minus_1': sma50_t_minus_1,
        'high20_t_minus_1': high20_t_minus_1,
        'vol_avg_10_t_minus_1': vol_avg_10_t_minus_1,
        'rsi_raw': rsi_raw,
        'atr_raw': atr_raw,
        'close_t': closes[-1],
        'volume_t': volumes[-1],
        'dollar_volume_t': dollar_volume_t,
        'dollar_volume_avg': dollar_volume_avg
    }