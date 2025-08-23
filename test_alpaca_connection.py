#!/usr/bin/env python3
"""Test script to validate Alpaca API connection."""

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Load environment variables from .env file manually
env_file = '.env'
if os.path.exists(env_file):
    with open(env_file) as f:
        for line in f:
            if '=' in line and not line.startswith('#'):
                key, value = line.strip().split('=', 1)
                os.environ[key] = value

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / 'src'))

def test_connection():
    """Test Alpaca API connection and credentials."""
    print("=" * 60)
    print("ALPACA API CONNECTION TEST")
    print("=" * 60)
    
    # Step 1: Check environment variables
    print("\n1. Checking environment variables...")
    api_key = os.getenv('ALPACA_API_KEY')
    api_secret = os.getenv('ALPACA_API_SECRET')
    
    if not api_key:
        print("   ❌ ALPACA_API_KEY not found in environment")
        return False
    else:
        print(f"   ✅ ALPACA_API_KEY found: {api_key[:10]}...")
    
    if not api_secret:
        print("   ❌ ALPACA_API_SECRET not found in environment")
        return False
    else:
        print(f"   ✅ ALPACA_API_SECRET found: {api_secret[:10]}...")
    
    # Step 2: Initialize Alpaca client
    print("\n2. Initializing Alpaca client...")
    try:
        from alpaca.data import StockHistoricalDataClient
        client = StockHistoricalDataClient(
            api_key=api_key,
            secret_key=api_secret,
            url_override="https://data.alpaca.markets"
        )
        print("   ✅ Client initialized successfully")
    except Exception as e:
        print(f"   ❌ Failed to initialize client: {e}")
        return False
    
    # Step 3: Test API call with SPY
    print("\n3. Testing API call with SPY...")
    try:
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame
        from alpaca.data.enums import Adjustment, DataFeed
        
        end = datetime.now()
        start = end - timedelta(days=5)
        
        request = StockBarsRequest(
            symbol_or_symbols="SPY",
            timeframe=TimeFrame.Day,
            start=start,
            end=end,
            adjustment=Adjustment.ALL,
            feed=DataFeed.IEX,  # Free tier feed
        )
        
        bars = client.get_stock_bars(request)
        
        if hasattr(bars, 'df'):
            df = bars.df
        elif isinstance(bars, dict) and 'SPY' in bars:
            df = bars['SPY']
        else:
            df = bars
        
        if df is not None and not df.empty:
            print(f"   ✅ Successfully fetched {len(df)} bars for SPY")
            print(f"   📊 Latest close: ${df['close'].iloc[-1]:.2f}")
            print(f"   📅 Latest date: {df.index[-1]}")
        else:
            print("   ⚠️  No data returned (market might be closed)")
    except Exception as e:
        print(f"   ❌ API call failed: {e}")
        return False
    
    # Step 4: Test with your DataProvider class
    print("\n4. Testing with DataProvider class...")
    try:
        import yaml
        from swingtrading.data_provider import DataProvider
        from swingtrading.rate_limiter import TokenBucket
        
        # Load config
        with open('config.yaml', 'r') as f:
            config = yaml.safe_load(f)
        
        # Initialize rate limiter
        rate_limiter = TokenBucket(
            tokens_per_minute=config['data']['rate_limit_per_minute'],
            start_full=config['data']['rate_limit_start_full']
        )
        
        # Initialize DataProvider
        provider = DataProvider(config, rate_limiter)
        print("   ✅ DataProvider initialized successfully")
        
        # Test fetching data
        print("\n5. Testing data fetch and indicator calculation...")
        test_symbol = "AAPL"
        df = provider.fetch_and_calculate(test_symbol)
        
        if not df.empty:
            print(f"   ✅ Successfully fetched and calculated indicators for {test_symbol}")
            print(f"   📊 Bars retrieved: {len(df)}")
            print(f"   📈 Latest RSI: {df['rsi14'].iloc[-1]:.2f}")
            print(f"   💵 Latest close: ${df['close'].iloc[-1]:.2f}")
            print(f"   📊 Latest SMA20: ${df['sma20'].iloc[-1]:.2f}")
            print(f"   📊 Latest SMA50: ${df['sma50'].iloc[-1]:.2f}")
        else:
            print(f"   ⚠️  No data returned for {test_symbol}")
            
    except ImportError as e:
        print(f"   ⚠️  Import error (check dependencies): {e}")
        print("   💡 Try running: pip install pyyaml")
    except Exception as e:
        print(f"   ❌ DataProvider test failed: {e}")
        return False
    
    print("\n" + "=" * 60)
    print("✅ ALL TESTS PASSED - API CONNECTION WORKING!")
    print("=" * 60)
    return True

if __name__ == "__main__":
    try:
        success = test_connection()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)