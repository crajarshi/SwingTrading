#!/usr/bin/env python3
"""Test script for paper trading functionality.

Tests basic imports and configurations without making actual trades.
"""

import sys
import yaml
from pathlib import Path
from datetime import datetime, date

# Test imports
print("Testing imports...")
try:
    from broker import AlpacaAdapter, get_next_session, is_market_open
    print("✓ Broker modules imported")
except ImportError as e:
    print(f"✗ Failed to import broker modules: {e}")
    sys.exit(1)

try:
    from trading import (
        generate_run_id,
        filter_candidates,
        compute_position_size,
        construct_entry_leg,
        construct_bracket_levels
    )
    print("✓ Trading modules imported")
except ImportError as e:
    print(f"✗ Failed to import trading modules: {e}")
    sys.exit(1)

try:
    from reporting import collect_day_data, compute_eod_metrics
    print("✓ Reporting modules imported")
except ImportError as e:
    print(f"✗ Failed to import reporting modules: {e}")
    sys.exit(1)

# Test configuration
print("\nTesting configuration...")
config_path = Path('config.yaml')
if config_path.exists():
    with open(config_path) as f:
        config = yaml.safe_load(f)
    print(f"✓ Config loaded: paper_trading.enabled = {config['paper_trading']['enabled']}")
else:
    print("✗ config.yaml not found")
    sys.exit(1)

# Test market calendar
print("\nTesting market calendar...")
from broker.market_calendar import get_session_times, is_holiday

today = date.today()
session = get_session_times(datetime.now())
print(f"✓ Today's session: open={session['open']}, close={session['close']}, "
      f"half_day={session['is_half_day']}, holiday={session['is_holiday']}")

# Test next trading session
next_session = get_next_session(datetime.now())
if next_session:
    print(f"✓ Next trading session: {next_session}")

# Test sizing calculations
print("\nTesting position sizing...")
from trading.paper_engine import compute_safe_position_size

test_size = compute_safe_position_size(
    equity=100000,
    price=150,
    atr=3.5,
    stop_mult=1.5,
    risk_pct=0.5,
    min_notional=200,
    max_pos_pct=0.10
)
print(f"✓ Test position size: {test_size} shares")

# Test bracket calculations
stop_loss, take_profit = construct_bracket_levels(
    entry_price=150,
    atr=3.5,
    stop_mult=1.5,
    target_mult=3.0
)
print(f"✓ Bracket levels: stop=${stop_loss:.2f}, target=${take_profit:.2f}")

# Test entry leg construction
entry_leg = construct_entry_leg(
    style="open",
    ref_price=150,
    buffer_bps=15
)
print(f"✓ Entry leg: type={entry_leg['type']}, tif={entry_leg['time_in_force']}, "
      f"limit=${entry_leg.get('limit_price', 'N/A')}")

# Test run ID generation
run_id = generate_run_id(date.today())
print(f"✓ Generated run ID: {run_id}")

# Test directory structure
print("\nChecking directory structure...")
dirs_to_check = ['broker', 'trading', 'reporting', 'cli', 'state', 'reports']
for dir_name in dirs_to_check:
    dir_path = Path(dir_name)
    if dir_path.exists():
        print(f"✓ Directory exists: {dir_name}/")
    else:
        print(f"✗ Directory missing: {dir_name}/")

# Test credentials (without exposing them)
print("\nChecking credentials...")
import os

env_file = Path('.env')
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            if '=' in line and not line.startswith('#'):
                key, value = line.strip().split('=', 1)
                os.environ[key] = value

if os.environ.get('ALPACA_API_KEY') and os.environ.get('ALPACA_API_SECRET'):
    print("✓ Alpaca credentials found in environment")
else:
    print("✗ Alpaca credentials not found - set ALPACA_API_KEY and ALPACA_API_SECRET")

print("\n" + "="*50)
print("PAPER TRADING SYSTEM TEST COMPLETE")
print("="*50)
print("\nTo run the paper trading system:")
print("  Scan:      python -m cli.paper scan")
print("  Place:     python -m cli.paper place")
print("  Report:    python -m cli.paper report")
print("  Positions: python -m cli.paper positions")
print("\nOr use the standalone script:")
print("  python cli/paper.py --help")