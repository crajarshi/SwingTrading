# Paper Trading System

## Overview

Complete paper trading system integrated with your SwingTrading scanner. Runs daily to:
1. **Scan** (16:10 ET): Generate candidates using scoring_v2
2. **Place** (09:28 ET): Submit paper orders with bracket stops
3. **Report** (16:20 ET): Generate EOD P&L and position reports

## Quick Start

```bash
# Test the system
python test_paper_trading.py

# Run daily workflow
python cli/paper.py scan      # After market close
python cli/paper.py place     # Before market open
python cli/paper.py report    # End of day
```

## Key Features Implemented

### ✅ P0 Requirements (Complete)

1. **Market Hours + Timezone**
   - All operations locked to America/New_York
   - Holiday/early close handling built-in
   - Automatic schedule adjustments

2. **Bracket + OPG Constraints**
   - Primary: OPG with bracket (if supported)
   - Fallback: OPG then OCO after fill
   - Final fallback: DAY bracket order

3. **Sizing & Guardrails**
   - Risk-based sizing (0.5% risk per trade)
   - Min price $2, min notional $200
   - Max position 10% of equity
   - Integer share rounding

4. **State & Reconciliation**
   - Run manifests persisted
   - Morning reconciliation at 09:25 ET
   - Idempotent order placement

5. **Reporting Math**
   - Starting equity from yesterday's snapshot
   - Realized P&L from fills
   - Top 5 contributors ranked
   - Zero-trade day handling

## Directory Structure

```
SwingTrading/
├── config.yaml              # Configuration (edit this!)
├── broker/                  # Alpaca integration
│   ├── alpaca_adapter.py   # Paper API wrapper
│   └── market_calendar.py  # NYSE schedule
├── trading/                 # Trading logic
│   ├── paper_engine.py     # Intent generation
│   ├── executor.py         # Order placement
│   ├── reconciliation.py   # Morning cleanup
│   └── position_manager.py # Exit management
├── reporting/               # EOD reports
│   └── eod_report.py       # P&L and metrics
├── cli/                     # Command interface
│   └── paper.py            # CLI commands
├── state/                   # Runtime data (git-ignored)
│   ├── intents/            # Daily order intents
│   ├── manifest/           # Run tracking
│   └── equity_snapshots/   # Daily equity
└── reports/                 # Daily reports (git-ignored)
    └── YYYY-MM-DD/
        ├── eod_report.md   # Markdown report
        ├── eod_trades.csv  # Trade details
        └── eod_summary.json # Metrics JSON
```

## Configuration

Edit `config.yaml`:

```yaml
paper_trading:
  enabled: true
  entry:
    max_symbols: 10        # Max new positions
    min_score: 65         # Score threshold
  sizing:
    risk_per_trade_pct: 0.5   # Risk per trade
    min_notional: 200         # Min position size
  risk:
    stop_atr_mult: 1.5        # Stop = entry - 1.5*ATR
    target_atr_mult: 3.0      # Target = entry + 3*ATR
    time_exit_days: 10        # Max holding period
```

## Daily Commands

### 1. Scan (16:10 ET)
```bash
python cli/paper.py scan
# Or with options:
python cli/paper.py scan --dry-run  # Test without saving
```

### 2. Reconcile (09:25 ET)
```bash
python cli/paper.py reconcile  # Clean up stale orders
```

### 3. Place Orders (09:28 ET)
```bash
python cli/paper.py place
# Or with specific run:
python cli/paper.py place --run-id 2025-01-15_scan
```

### 4. Generate Report (16:20 ET)
```bash
python cli/paper.py report
# Or for specific date:
python cli/paper.py report --date 2025-01-15
```

### 5. View Positions
```bash
python cli/paper.py positions
```

### 6. Emergency Close
```bash
python cli/paper.py close-all --reason "Market emergency"
```

## Scheduling (cron/Task Scheduler)

```bash
# Add to crontab (adjust paths):
10 16 * * 1-5 cd /path/to/SwingTrading && python cli/paper.py scan
25 09 * * 1-5 cd /path/to/SwingTrading && python cli/paper.py reconcile
28 09 * * 1-5 cd /path/to/SwingTrading && python cli/paper.py place
20 16 * * 1-5 cd /path/to/SwingTrading && python cli/paper.py report
```

## Sample Output

### Scan Output
```
SCAN SUMMARY - 2025-01-15
==================================================
Candidates scanned: 500
Filtered (score >= 65): 42
Selected for trading: 10

Order Intents:
  AAPL   -  123 shares @ $150.23 (score=78.5)
  MSFT   -   87 shares @ $420.15 (score=75.2)
  ...
```

### Report Output
```
END-OF-DAY REPORT - 2025-01-15
==================================================
Starting Equity:  $   100,000.00
Ending Equity:    $   100,850.00
Daily P/L:        $     +850.00 (+0.85%)
Realized P/L:     $     +700.00
Unrealized P/L:   $     +150.00

New Entries: 5
Exits: 3
Open Positions: 7
Exposure: 68.5%
```

## Testing

```bash
# Basic functionality test
python test_paper_trading.py

# Dry run (no orders placed)
python cli/paper.py scan --dry-run
python cli/paper.py place --dry-run
```

## Acceptance Checklist

- [x] America/New_York timezone locked everywhere
- [x] Holiday/half-day handling implemented
- [x] OPG+bracket fallback cascade working
- [x] Sizing guards prevent invalid orders
- [x] Reconciliation handles unfilled/partial orders
- [x] Reports render for zero-trade days
- [x] Idempotent order placement via client_order_id
- [x] No secrets in logs or reports
- [x] Paper endpoint only (safety check)

## Important Notes

1. **Paper Account Only**: System validates paper endpoint URL
2. **No Intraday Monitoring**: Set-and-forget bracket orders
3. **Deterministic Scoring**: Uses your existing scoring_v2
4. **Idempotent**: Safe to re-run commands
5. **Timezone Aware**: All times in America/New_York

## Troubleshooting

### Missing Credentials
```bash
# Add to .env file:
ALPACA_API_KEY=your_paper_key
ALPACA_API_SECRET=your_paper_secret
```

### No Candidates Found
- Check `min_score` in config.yaml
- Verify market data access
- Check scoring_v2 is working

### Orders Not Filling
- OPG orders may not fill if price gaps
- Check bracket levels are reasonable
- Verify paper account has buying power

## Next Steps (P1 Enhancements)

- [ ] Earnings calendar integration
- [ ] IV percentile filtering
- [ ] Equity curve in reports
- [ ] Slack/email notifications
- [ ] Web dashboard

## Support

For issues or questions about the paper trading system:
1. Check `paper_trading.log` for errors
2. Verify config.yaml settings
3. Run test_paper_trading.py for diagnostics

---

*Paper trading system v1.0 - Integrated with SwingTrading scoring_v2*