"""Historical data management for backtesting."""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import requests
import os
import json
from pathlib import Path
import time


class HistoricalDataManager:
    """Manages historical data for backtesting."""
    
    def __init__(self, cache_dir: str = "backtest_cache"):
        """Initialize data manager with cache directory."""
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        
        # Alpaca credentials (try multiple naming conventions)
        self.alpaca_key = (os.getenv('ALPACA_API_KEY') or
                          os.getenv('ALPACA_KEY') or
                          os.getenv('APCA_API_KEY_ID'))
        self.alpaca_secret = (os.getenv('ALPACA_API_SECRET') or
                             os.getenv('ALPACA_SECRET') or
                             os.getenv('APCA_API_SECRET_KEY'))
        
        if not self.alpaca_key or not self.alpaca_secret:
            print("Warning: Alpaca credentials not found. Using cache only.")
    
    def get_historical_bars(self, symbol: str, end_date: str, days: int = 550) -> Optional[List[Dict]]:
        """Get historical OHLCV bars for a symbol up to end_date.
        
        Args:
            symbol: Stock symbol
            end_date: End date in YYYY-MM-DD format
            days: Number of days to fetch
            
        Returns:
            List of OHLCV bars or None
        """
        # Check cache first
        cache_key = f"{symbol}_{end_date}_{days}"
        cached_data = self._get_from_cache(cache_key)
        if cached_data:
            return cached_data
        
        # Fetch from API
        bars = self._fetch_from_alpaca(symbol, end_date, days)
        if bars:
            self._save_to_cache(cache_key, bars)
        
        return bars
    
    def get_daily_data(self, symbol: str, date: str) -> Optional[Dict]:
        """Get single day's OHLCV data for a symbol.
        
        Args:
            symbol: Stock symbol
            date: Date in YYYY-MM-DD format
            
        Returns:
            Dict with OHLCV data or None
        """
        # For backtesting, we need the full historical series
        # This is a simplified implementation
        bars = self.get_historical_bars(symbol, date, days=30)
        if not bars:
            return None
            
        # Find the bar for the specific date
        target_date = datetime.strptime(date, '%Y-%m-%d').date()
        
        for bar in reversed(bars):  # Start from most recent
            bar_date = datetime.fromisoformat(bar['t'].replace('Z', '+00:00')).date()
            if bar_date <= target_date:
                return {
                    'open': bar['o'],
                    'high': bar['h'], 
                    'low': bar['l'],
                    'close': bar['c'],
                    'volume': bar['v'],
                    'date': bar_date.isoformat()
                }
        
        return None
    
    def _get_from_cache(self, cache_key: str) -> Optional[List[Dict]]:
        """Get data from cache."""
        cache_file = self.cache_dir / f"{cache_key}.json"
        
        if cache_file.exists():
            try:
                with open(cache_file, 'r') as f:
                    data = json.load(f)
                    
                # Check if cache is still valid (24 hours)
                cache_time = datetime.fromisoformat(data['timestamp'])
                if datetime.now() - cache_time < timedelta(hours=24):
                    return data['bars']
            except Exception as e:
                print(f"Cache read error for {cache_key}: {e}")
        
        return None
    
    def _save_to_cache(self, cache_key: str, bars: List[Dict]):
        """Save data to cache."""
        cache_file = self.cache_dir / f"{cache_key}.json"
        
        try:
            cache_data = {
                'timestamp': datetime.now().isoformat(),
                'bars': bars
            }
            
            with open(cache_file, 'w') as f:
                json.dump(cache_data, f)
        except Exception as e:
            print(f"Cache write error for {cache_key}: {e}")
    
    def _fetch_from_alpaca(self, symbol: str, end_date: str, days: int) -> Optional[List[Dict]]:
        """Fetch historical data from Alpaca API."""
        if not self.alpaca_key or not self.alpaca_secret:
            return None
        
        try:
            # Calculate start date
            end_dt = datetime.strptime(end_date, '%Y-%m-%d')
            start_dt = end_dt - timedelta(days=days)
            start_date = start_dt.strftime('%Y-%m-%d')
            
            url = f"https://data.alpaca.markets/v2/stocks/{symbol}/bars"
            params = {
                'start': start_date,
                'end': end_date,
                'timeframe': '1Day',
                'feed': 'iex',
                'limit': 10000
            }
            
            headers = {
                'APCA-API-KEY-ID': self.alpaca_key,
                'APCA-API-SECRET-KEY': self.alpaca_secret,
                'Content-Type': 'application/json'
            }
            
            print(f"Fetching {symbol} from {start_date} to {end_date}")
            response = requests.get(url, params=params, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                bars = data.get('bars', [])
                
                if bars:
                    print(f"✓ Got {len(bars)} bars for {symbol}")
                    return bars
                else:
                    print(f"✗ No bars returned for {symbol}")
                    return None
            else:
                print(f"✗ API error for {symbol}: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"✗ Error fetching {symbol}: {e}")
            return None
    
    def preload_universe_data(self, symbols: List[str], start_date: str, end_date: str, days: int = 550):
        """Preload data for entire universe to improve backtest speed.
        
        Args:
            symbols: List of symbols to preload
            start_date: Start date for backtest
            end_date: End date for backtest  
            days: Days of history needed per symbol
        """
        print(f"Preloading data for {len(symbols)} symbols...")

        successful_loads = 0
        failed_loads = 0

        for i, symbol in enumerate(symbols):
            # Progress reporting - less frequent for large datasets
            if len(symbols) > 50:
                if i % 25 == 0 or i == len(symbols) - 1:
                    progress = (i + 1) / len(symbols) * 100
                    print(f"Preloading progress: {i+1}/{len(symbols)} ({progress:.1f}%) - "
                          f"✓{successful_loads} ✗{failed_loads}")
            else:
                print(f"Preloading {symbol} ({i+1}/{len(symbols)})")

            # Preload data for end_date (most recent needed)
            bars = self.get_historical_bars(symbol, end_date, days)

            if bars and len(bars) > 100:  # Minimum viable data
                successful_loads += 1
            else:
                failed_loads += 1
                if len(symbols) <= 50:  # Only show individual failures for small datasets
                    print(f"  ⚠️ {symbol}: Insufficient data ({len(bars) if bars else 0} bars)")

            # Add small delay to avoid rate limits
            time.sleep(0.05 if len(symbols) > 100 else 0.1)

        print(f"✓ Data preloading complete: {successful_loads} successful, {failed_loads} failed")

        if failed_loads > len(symbols) * 0.1:  # More than 10% failures
            print(f"⚠️ Warning: {failed_loads}/{len(symbols)} symbols failed to load sufficient data")
            print("This may impact backtest results. Consider checking API limits or data availability.")


def get_historical_universe_data(symbols: List[str], start_date: str, end_date: str) -> Dict[str, pd.DataFrame]:
    """Get historical data for entire universe.
    
    Args:
        symbols: List of symbols
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
        
    Returns:
        Dict mapping symbol to DataFrame with OHLCV data
    """
    data_manager = HistoricalDataManager()
    universe_data = {}
    
    for symbol in symbols:
        bars = data_manager.get_historical_bars(symbol, end_date, days=550)
        if bars:
            # Convert to DataFrame
            df = pd.DataFrame(bars)
            df['date'] = pd.to_datetime(df['t']).dt.date
            df = df.set_index('date')
            df = df[['o', 'h', 'l', 'c', 'v']].rename(columns={
                'o': 'open', 'h': 'high', 'l': 'low', 'c': 'close', 'v': 'volume'
            })
            universe_data[symbol] = df
    
    return universe_data
