#!/usr/bin/env python3
"""Close a specific paper trading position."""

import os
import sys
import urllib.request
import json

# Load credentials from .env
with open('.env') as f:
    for line in f:
        if '=' in line and not line.startswith('#'):
            key, value = line.strip().split('=', 1)
            os.environ[key] = value

api_key = os.environ.get('ALPACA_API_KEY')
api_secret = os.environ.get('ALPACA_API_SECRET')

def close_position(symbol):
    """Close a position for the given symbol."""
    url = f'https://paper-api.alpaca.markets/v2/positions/{symbol}'
    
    req = urllib.request.Request(url, method='DELETE', headers={
        'APCA-API-KEY-ID': api_key,
        'APCA-API-SECRET-KEY': api_secret
    })
    
    try:
        response = urllib.request.urlopen(req)
        data = json.loads(response.read())
        print(f"Successfully closed position for {symbol}")
        print(f"Order ID: {data.get('id', 'N/A')}")
        return True
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print(f"No position found for {symbol}")
        else:
            print(f"Error closing position: {e}")
            print(e.read().decode())
        return False

# Close AMD position
print("Closing AMD paper position...")
print("="*50)

if close_position('AMD'):
    print("\n✓ AMD position closed successfully!")
    print("You can now run the paper scan to find new candidates.")
else:
    print("\n✗ Failed to close AMD position")