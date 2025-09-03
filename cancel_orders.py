#!/usr/bin/env python3
"""Cancel open orders and close positions."""

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
base_url = 'https://paper-api.alpaca.markets'

def make_request(method, endpoint, data=None):
    """Make API request to Alpaca."""
    url = f'{base_url}{endpoint}'
    
    req_data = json.dumps(data).encode('utf-8') if data else None
    headers = {
        'APCA-API-KEY-ID': api_key,
        'APCA-API-SECRET-KEY': api_secret
    }
    if data:
        headers['Content-Type'] = 'application/json'
    
    req = urllib.request.Request(url, data=req_data, method=method, headers=headers)
    
    try:
        response = urllib.request.urlopen(req)
        content = response.read()
        return json.loads(content) if content else {}
    except urllib.error.HTTPError as e:
        error_data = e.read().decode()
        print(f"API Error: {error_data}")
        raise

# Step 1: Get open orders
print("Checking for open orders...")
orders = make_request('GET', '/v2/orders?status=open')

if orders:
    print(f"Found {len(orders)} open order(s)")
    for order in orders:
        if order['symbol'] == 'AMD':
            print(f"  - {order['symbol']}: {order['side']} {order['qty']} @ {order['order_type']}")
            print(f"    Order ID: {order['id']}")
            
            # Cancel the order
            print(f"    Canceling order...")
            try:
                make_request('DELETE', f"/v2/orders/{order['id']}")
                print(f"    ✓ Order canceled")
            except:
                print(f"    ✗ Failed to cancel")
else:
    print("No open orders found")

print("\n" + "="*50)

# Step 2: Now try to close the position
print("Attempting to close AMD position...")
try:
    result = make_request('DELETE', '/v2/positions/AMD')
    print("✓ AMD position closed successfully!")
    if result:
        print(f"  Order ID: {result.get('id', 'N/A')}")
except Exception as e:
    print(f"✗ Failed to close position: {e}")

print("\n" + "="*50)

# Step 3: Verify positions
print("Current positions:")
positions = make_request('GET', '/v2/positions')
if positions:
    for pos in positions:
        print(f"  - {pos['symbol']}: {pos['qty']} shares @ ${pos['avg_entry_price']}")
else:
    print("  No positions (account is flat)")