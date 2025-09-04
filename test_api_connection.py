#!/usr/bin/env python3
"""Test Alpaca API connection for backtesting."""

import os
import requests
from datetime import datetime, timedelta
from pathlib import Path

# Load environment variables from .env file
def load_env_file():
    """Load environment variables from .env file."""
    env_file = Path('.env')
    if env_file.exists():
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key] = value
        print("✓ Loaded .env file")
    else:
        print("✗ No .env file found")

def test_alpaca_connection():
    """Test connection to Alpaca API."""
    load_env_file()
    
    # Get credentials
    api_key = os.getenv('ALPACA_API_KEY')
    api_secret = os.getenv('ALPACA_API_SECRET')
    
    print(f"API Key: {api_key[:8]}..." if api_key else "API Key: Not found")
    print(f"API Secret: {api_secret[:8]}..." if api_secret else "API Secret: Not found")
    
    if not api_key or not api_secret:
        print("✗ Missing Alpaca credentials")
        return False
    
    # Test API call
    try:
        # Simple test - get account info
        url = "https://paper-api.alpaca.markets/v2/account"
        headers = {
            'APCA-API-KEY-ID': api_key,
            'APCA-API-SECRET-KEY': api_secret
        }
        
        print("Testing account API...")
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            account = response.json()
            print(f"✓ Account API works - Equity: ${account.get('equity', 'unknown')}")
        else:
            print(f"✗ Account API failed: {response.status_code}")
            print(f"Response: {response.text}")
        
        # Test historical data API
        print("\nTesting historical data API...")
        symbol = "AAPL"
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        
        data_url = f"https://data.alpaca.markets/v2/stocks/{symbol}/bars"
        params = {
            'start': start_date,
            'end': end_date,
            'timeframe': '1Day',
            'feed': 'iex',
            'limit': 100
        }
        
        data_response = requests.get(data_url, params=params, headers=headers)
        
        if data_response.status_code == 200:
            data = data_response.json()
            bars = data.get('bars', [])
            print(f"✓ Historical data API works - Got {len(bars)} bars for {symbol}")
            
            if bars:
                latest = bars[-1]
                print(f"  Latest bar: {latest['t']} - Close: ${latest['c']}")
                return True
            else:
                print("✗ No historical data returned")
                return False
        else:
            print(f"✗ Historical data API failed: {data_response.status_code}")
            print(f"Response: {data_response.text}")
            return False
            
    except Exception as e:
        print(f"✗ API test failed: {e}")
        return False

if __name__ == "__main__":
    print("Testing Alpaca API Connection")
    print("=" * 30)
    
    success = test_alpaca_connection()
    
    if success:
        print("\n✓ API connection successful! Ready for backtesting.")
    else:
        print("\n✗ API connection failed. Check credentials and try again.")
