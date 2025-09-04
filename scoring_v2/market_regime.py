"""Market regime detection for improved scoring context."""

import numpy as np
import pandas as pd
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta
import requests
import os


class MarketRegimeDetector:
    """Detects market regime to adjust scoring behavior."""
    
    def __init__(self):
        """Initialize market regime detector."""
        self.cache = {}
        self.cache_expiry = {}
        
    def get_market_regime(self, current_date: str = None) -> Dict[str, any]:
        """Get current market regime indicators.
        
        Args:
            current_date: Date to analyze (defaults to today)
            
        Returns:
            Dict with regime indicators
        """
        if current_date is None:
            current_date = datetime.now().strftime('%Y-%m-%d')
            
        # Check cache first
        cache_key = f"regime_{current_date}"
        if (cache_key in self.cache and 
            cache_key in self.cache_expiry and 
            datetime.now() < self.cache_expiry[cache_key]):
            return self.cache[cache_key]
        
        # Calculate regime indicators
        regime = self._calculate_regime_indicators(current_date)
        
        # Cache for 1 hour
        self.cache[cache_key] = regime
        self.cache_expiry[cache_key] = datetime.now() + timedelta(hours=1)
        
        return regime
    
    def _calculate_regime_indicators(self, current_date: str) -> Dict[str, any]:
        """Calculate market regime indicators."""
        try:
            # Get SPY data for trend regime
            spy_data = self._get_market_data('SPY', current_date, days=200)
            vix_data = self._get_market_data('VIX', current_date, days=50)
            
            regime = {
                'trend_regime': 'neutral',
                'volatility_regime': 'medium',
                'market_strength': 0.5,
                'risk_on': True,
                'confidence': 0.5
            }
            
            if spy_data and len(spy_data) >= 50:
                regime.update(self._analyze_trend_regime(spy_data))
            
            if vix_data and len(vix_data) >= 20:
                regime.update(self._analyze_volatility_regime(vix_data))
            
            # Overall market assessment
            regime['risk_on'] = (
                regime['trend_regime'] in ['bull', 'neutral'] and 
                regime['volatility_regime'] in ['low', 'medium']
            )
            
            return regime
            
        except Exception as e:
            print(f"Warning: Market regime detection failed: {e}")
            return {
                'trend_regime': 'neutral',
                'volatility_regime': 'medium', 
                'market_strength': 0.5,
                'risk_on': True,
                'confidence': 0.0
            }
    
    def _analyze_trend_regime(self, spy_data: list) -> Dict[str, any]:
        """Analyze SPY trend regime."""
        closes = [bar['c'] for bar in spy_data]
        
        # Calculate moving averages
        sma_50 = np.mean(closes[-50:])
        sma_200 = np.mean(closes[-200:]) if len(closes) >= 200 else sma_50
        current_price = closes[-1]
        
        # Trend strength
        trend_strength = (current_price - sma_200) / sma_200 if sma_200 > 0 else 0
        
        # Determine regime
        if current_price > sma_50 > sma_200 and trend_strength > 0.05:
            trend_regime = 'bull'
            market_strength = min(0.8, 0.5 + trend_strength * 2)
        elif current_price < sma_50 < sma_200 and trend_strength < -0.05:
            trend_regime = 'bear'
            market_strength = max(0.2, 0.5 + trend_strength * 2)
        else:
            trend_regime = 'neutral'
            market_strength = 0.5
        
        return {
            'trend_regime': trend_regime,
            'market_strength': market_strength,
            'spy_vs_sma50': (current_price - sma_50) / sma_50 if sma_50 > 0 else 0,
            'spy_vs_sma200': trend_strength
        }
    
    def _analyze_volatility_regime(self, vix_data: list) -> Dict[str, any]:
        """Analyze VIX volatility regime."""
        vix_closes = [bar['c'] for bar in vix_data]
        current_vix = vix_closes[-1]
        avg_vix = np.mean(vix_closes[-20:])  # 20-day average
        
        # Volatility regime thresholds
        if current_vix < 15:
            vol_regime = 'low'
        elif current_vix < 25:
            vol_regime = 'medium'
        elif current_vix < 35:
            vol_regime = 'high'
        else:
            vol_regime = 'extreme'
        
        return {
            'volatility_regime': vol_regime,
            'vix_current': current_vix,
            'vix_20d_avg': avg_vix,
            'vix_percentile': self._calculate_vix_percentile(vix_closes, current_vix)
        }
    
    def _calculate_vix_percentile(self, vix_history: list, current_vix: float) -> float:
        """Calculate VIX percentile rank."""
        if len(vix_history) < 10:
            return 0.5
            
        sorted_vix = sorted(vix_history)
        rank = sum(1 for v in sorted_vix if v <= current_vix)
        return rank / len(sorted_vix)
    
    def _get_market_data(self, symbol: str, end_date: str, days: int = 50) -> Optional[list]:
        """Get market data for regime analysis."""
        try:
            # Load environment variables
            api_key = os.getenv('ALPACA_API_KEY')
            api_secret = os.getenv('ALPACA_API_SECRET')
            
            if not api_key or not api_secret:
                return None
            
            # Calculate start date
            end_dt = datetime.strptime(end_date, '%Y-%m-%d')
            start_dt = end_dt - timedelta(days=days + 10)  # Extra buffer
            start_date = start_dt.strftime('%Y-%m-%d')
            
            # API call
            url = f"https://data.alpaca.markets/v2/stocks/{symbol}/bars"
            params = {
                'start': start_date,
                'end': end_date,
                'timeframe': '1Day',
                'feed': 'iex',
                'limit': days + 10
            }
            
            headers = {
                'APCA-API-KEY-ID': api_key,
                'APCA-API-SECRET-KEY': api_secret
            }
            
            response = requests.get(url, params=params, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                return data.get('bars', [])
            else:
                return None
                
        except Exception as e:
            print(f"Warning: Failed to get {symbol} data: {e}")
            return None


def get_regime_adjusted_weights(base_weights: Dict[str, float], 
                              regime: Dict[str, any]) -> Dict[str, float]:
    """Adjust scoring weights based on market regime.
    
    Args:
        base_weights: Base component weights
        regime: Market regime indicators
        
    Returns:
        Adjusted weights
    """
    adjusted = base_weights.copy()
    
    # In bear markets, emphasize trend and volume more
    if regime['trend_regime'] == 'bear':
        adjusted['trend'] = min(0.35, base_weights['trend'] * 1.5)
        adjusted['volume'] = min(0.40, base_weights['volume'] * 1.2)
        adjusted['pullback'] = max(0.15, base_weights['pullback'] * 0.8)
        adjusted['rsi'] = max(0.10, base_weights['rsi'] * 0.8)
    
    # In high volatility, emphasize pullback and RSI
    elif regime['volatility_regime'] in ['high', 'extreme']:
        adjusted['pullback'] = min(0.45, base_weights['pullback'] * 1.3)
        adjusted['rsi'] = min(0.25, base_weights['rsi'] * 1.5)
        adjusted['trend'] = max(0.15, base_weights['trend'] * 0.8)
        adjusted['volume'] = max(0.15, base_weights['volume'] * 0.8)
    
    # Normalize to sum to 1.0
    total = sum(adjusted.values())
    if total > 0:
        adjusted = {k: v / total for k, v in adjusted.items()}
    
    return adjusted


def should_trade_in_regime(regime: Dict[str, any]) -> Tuple[bool, str]:
    """Determine if we should trade in current market regime.
    
    Args:
        regime: Market regime indicators
        
    Returns:
        (should_trade, reason)
    """
    # Don't trade in extreme volatility
    if regime['volatility_regime'] == 'extreme':
        return False, "extreme_volatility"
    
    # Be cautious in bear markets with high volatility
    if (regime['trend_regime'] == 'bear' and 
        regime['volatility_regime'] == 'high'):
        return False, "bear_high_vol"
    
    # Reduce activity in bear markets
    if regime['trend_regime'] == 'bear':
        # Only trade highest quality setups
        return True, "bear_selective"
    
    return True, "normal_trading"


# Global instance for easy access
market_regime_detector = MarketRegimeDetector()
