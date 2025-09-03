#!/usr/bin/env python3
"""CLI commands for paper trading operations.

Three main modes:
- scan: Run scanner and generate intents (16:10 ET)
- place: Place orders from intents (09:28 ET)
- report: Generate EOD report (16:20 ET)

Additional commands:
- reconcile: Morning reconciliation (09:25 ET)
- positions: Show current positions
- close-all: Emergency close all positions
"""

import os
import sys
import json
import yaml
import logging
import pandas as pd
from pathlib import Path
from datetime import date, datetime, timedelta
from typing import Dict, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from broker import AlpacaAdapter, get_session_times, is_market_open
from trading import (
    build_order_intents,
    serialize_intents,
    place_orders,
    write_orders_log,
    morning_reconcile,
    close_positions_by_age,
    emergency_close_all
)
from reporting import generate_eod_report
from scoring_v2 import calculate_score_v2

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_config(config_file: str = "config.yaml") -> Dict:
    """Load configuration from YAML file."""
    config_path = Path(config_file)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_file}")
    
    with open(config_path) as f:
        return yaml.safe_load(f)


def load_credentials() -> tuple[str, str]:
    """Load Alpaca credentials from environment."""
    # Try loading from .env file
    env_file = Path('.env')
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                if '=' in line and not line.startswith('#'):
                    key, value = line.strip().split('=', 1)
                    os.environ[key] = value
    
    api_key = os.environ.get('ALPACA_API_KEY')
    api_secret = os.environ.get('ALPACA_API_SECRET')
    
    if not api_key or not api_secret:
        raise ValueError("Missing Alpaca credentials. Set ALPACA_API_KEY and ALPACA_API_SECRET")
    
    return api_key, api_secret


def get_adapter(config: Dict) -> AlpacaAdapter:
    """Create Alpaca adapter instance."""
    api_key, api_secret = load_credentials()
    paper_config = config['paper_trading']
    
    return AlpacaAdapter(
        api_key=api_key,
        api_secret=api_secret,
        base_url=paper_config['paper_base_url'],
        account_id_alias=paper_config.get('account_id_alias', 'default')
    )


def run_scanner(config: Dict) -> pd.DataFrame:
    """Run the scoring scanner on configured universe.
    
    Args:
        config: Configuration dict
        
    Returns:
        DataFrame with scan results
    """
    # Load universe
    universe_file = config['scanner'].get('universe_file', 'sp500_tickers.txt')
    with open(universe_file) as f:
        all_tickers = [line.strip() for line in f if line.strip()]
    
    # For paper trading, limit to most liquid stocks for faster scanning
    # Focus on top 100 most traded stocks
    high_volume_stocks = [
        'SPY', 'QQQ', 'AAPL', 'MSFT', 'NVDA', 'AMZN', 'META', 'TSLA', 'GOOGL', 'GOOG',
        'AMD', 'AVGO', 'COST', 'PEP', 'NFLX', 'ADBE', 'CSCO', 'INTC', 'TMUS', 'CMCSA',
        'TXN', 'AMGN', 'HON', 'QCOM', 'SBUX', 'INTU', 'ISRG', 'MDLZ', 'GILD', 'ADI',
        'VRTX', 'REGN', 'BKNG', 'PDD', 'AMAT', 'PANW', 'ADP', 'MU', 'LRCX', 'KLAC',
        'SNPS', 'CDNS', 'MELI', 'ASML', 'ABNB', 'CHTR', 'MAR', 'MRVL', 'ORLY', 'FTNT',
        'JPM', 'BAC', 'WFC', 'GS', 'MS', 'C', 'USB', 'PNC', 'TFC', 'COF',
        'V', 'MA', 'AXP', 'PYPL', 'SQ', 'COIN', 'DIS', 'NFLX', 'CMCSA', 'T',
        'UNH', 'JNJ', 'PFE', 'ABBV', 'LLY', 'TMO', 'ABT', 'DHR', 'BMY', 'AMGN',
        'XOM', 'CVX', 'COP', 'SLB', 'EOG', 'PXD', 'MPC', 'VLO', 'PSX', 'OXY',
        'BA', 'CAT', 'DE', 'GE', 'HON', 'LMT', 'RTX', 'UPS', 'UNP', 'FDX'
    ]
    
    # Use only stocks that exist in both lists
    tickers = [t for t in high_volume_stocks if t in all_tickers][:100]
    
    logger.info(f"Scanning {len(tickers)} high-volume symbols for faster results...")
    
    # Get historical data and score each symbol
    results = []
    adapter = get_adapter(config)
    
    for symbol in tickers:  # Scan all symbols
        try:
            # Get historical data
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=550)).strftime('%Y-%m-%d')
            
            bars = adapter.get_bars(symbol, start_date, end_date)
            
            if bars and len(bars) >= 250:
                # Calculate score using scoring_v2
                score, gate_reason, components = calculate_score_v2(bars, symbol)
                
                # Include all stocks with valid scores (even if low)
                if score is not None and score >= 0:  # Valid score
                    # Extract latest values
                    latest_bar = bars[-1]
                    
                    results.append({
                        'symbol': symbol,
                        'score': score,
                        'close': float(latest_bar['c']),
                        'volume': int(latest_bar['v']),
                        'atr20': components.get('raw_features', {}).get('atr_value', 0),
                        'rsi14': components.get('raw_features', {}).get('rsi_value', 0),
                        'sma50': components.get('raw_features', {}).get('sma50_t_minus_1'),
                        'gate_reason': gate_reason
                    })
                    
                    # Log all scores to see what we're getting
                    if score >= 30:
                        logger.info(f"{symbol}: score={score:.1f} ✓ MEETS THRESHOLD")
                    else:
                        logger.debug(f"{symbol}: score={score:.1f}")
            
        except Exception as e:
            logger.error(f"Error scanning {symbol}: {e}")
    
    # Log summary of scan results
    if results:
        scores = [r['score'] for r in results]
        high_scores = [s for s in scores if s >= 45]
        logger.info(f"Scan complete: {len(results)} stocks scored")
        logger.info(f"Score distribution: min={min(scores):.1f}, max={max(scores):.1f}, avg={sum(scores)/len(scores):.1f}")
        logger.info(f"Stocks meeting threshold (>=45): {len(high_scores)}")
    
    # Convert to DataFrame
    df = pd.DataFrame(results)
    
    # Sort by score
    if not df.empty:
        df = df.sort_values('score', ascending=False)
    
    logger.info(f"Scan complete: {len(df)} qualified symbols")
    
    return df


def cmd_scan(
    config_file: str,
    overrides: Optional[Dict],
    out_dir: str,
    dry_run: bool = False
) -> Dict:
    """Run scanner and generate order intents.
    
    Args:
        config_file: Path to config file
        overrides: Optional config overrides
        out_dir: Output directory for artifacts
        dry_run: If True, don't save files
        
    Returns:
        Summary dict
    """
    logger.info("=== SCAN MODE ===")
    
    # Load config
    config = load_config(config_file)
    if overrides:
        # Merge overrides
        for key, value in overrides.items():
            if '.' in key:
                # Nested key like 'entry.min_score'
                parts = key.split('.')
                target = config
                for part in parts[:-1]:
                    target = target.setdefault(part, {})
                target[parts[-1]] = value
            else:
                config[key] = value
    
    # Check if paper trading enabled
    if not config['paper_trading'].get('enabled', True):
        logger.warning("Paper trading is disabled in config")
        return {'status': 'disabled'}
    
    # Run scanner
    scan_df = run_scanner(config)
    
    if scan_df.empty:
        logger.warning("No candidates found")
        return {'status': 'no_candidates'}
    
    # Get account info
    adapter = get_adapter(config)
    account = adapter.get_account()
    equity = float(account['equity'])
    positions = adapter.get_positions()
    
    logger.info(f"Account equity: ${equity:,.2f}")
    logger.info(f"Open positions: {len(positions)}")
    
    # Build order intents
    intents, summary = build_order_intents(
        scan_df=scan_df,
        config=config['paper_trading'],
        account_equity=equity,
        open_positions=positions,
        as_of=date.today()
    )
    
    # Save artifacts
    if not dry_run:
        # Save scan results
        scan_path = Path(out_dir) / 'scan_results.csv'
        scan_path.parent.mkdir(parents=True, exist_ok=True)
        scan_df.to_csv(scan_path, index=False)
        
        # Save intents
        intent_path = Path('state/intents') / f"{date.today()}.json"
        serialize_intents(intents, intent_path)
        
        # Save manifest
        manifest_path = Path('state/manifest') / f"{summary['run_id']}.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        with open(manifest_path, 'w') as f:
            json.dump({
                'run_id': summary['run_id'],
                'summary': summary,
                'intents': intents,
                'timestamp': datetime.now().isoformat()
            }, f, indent=2, default=str)
        
        logger.info(f"Saved {len(intents)} intents to {intent_path}")
    
    # Print summary
    print("\n" + "="*50)
    print(f"SCAN SUMMARY - {date.today()}")
    print("="*50)
    print(f"Candidates scanned: {summary['candidates']}")
    print(f"Filtered (score >= {config['paper_trading']['entry']['min_score']}): {summary['filtered']}")
    print(f"Selected for trading: {summary['selected']}")
    
    if intents:
        print("\nOrder Intents:")
        for intent in intents[:10]:  # Show first 10
            price = intent['entry'].get('limit_price')
            if price is None:
                price_str = "market"
            else:
                price_str = f"${price:.2f}"
            print(f"  {intent['symbol']:6s} - {intent['qty']:4d} shares @ {price_str} "
                  f"(score={intent['meta']['score']:.1f})")
    
    return {
        'status': 'success',
        'run_id': summary['run_id'],
        'intents': intents,  # Return actual intents not just count
        'intent_count': len(intents),
        'paths': {
            'scan': str(scan_path) if not dry_run else None,
            'intents': str(intent_path) if not dry_run else None
        }
    }


def cmd_place(
    config_file: str,
    run_id: Optional[str],
    dry_run: bool = False
) -> Dict:
    """Place orders from saved intents.
    
    Args:
        config_file: Path to config file
        run_id: Specific run ID (or use latest)
        dry_run: If True, simulate placement
        
    Returns:
        Placement summary
    """
    logger.info("=== PLACE MODE ===")
    
    # Load config
    config = load_config(config_file)
    
    # Find intents
    if run_id:
        manifest_path = Path('state/manifest') / f"{run_id}.json"
    else:
        # Use today's intents
        intent_path = Path('state/intents') / f"{date.today()}.json"
        if not intent_path.exists():
            logger.error(f"No intents found for {date.today()}")
            return {'status': 'no_intents'}
        
        with open(intent_path) as f:
            intents = json.load(f)
        run_id = intents[0]['run_id'] if intents else f"{date.today()}_scan"
    
    # Load intents
    if 'intents' in locals():
        pass  # Already loaded
    elif manifest_path.exists():
        with open(manifest_path) as f:
            manifest = json.load(f)
            intents = manifest['intents']
    else:
        logger.error(f"Manifest not found: {manifest_path}")
        return {'status': 'manifest_not_found'}
    
    if not intents:
        logger.info("No intents to place")
        return {'status': 'no_intents'}
    
    # Get adapter
    adapter = get_adapter(config)
    
    # Place orders
    placement_summary = place_orders(
        adapter=adapter,
        intents=intents,
        run_id=run_id,
        dry_run=dry_run
    )
    
    # Save placement summary
    if not dry_run:
        placement_path = Path('state/placement') / f"{run_id}.json"
        placement_path.parent.mkdir(parents=True, exist_ok=True)
        with open(placement_path, 'w') as f:
            json.dump(placement_summary, f, indent=2, default=str)
        
        # Log orders
        log_path = Path('state/orders_log.jsonl')
        log_entries = []
        for placed in placement_summary['placed']:
            log_entries.append({
                'run_id': run_id,
                'action': 'placed',
                **placed
            })
        if log_entries:
            write_orders_log(log_entries, log_path)
    
    # Print summary
    print("\n" + "="*50)
    print(f"PLACEMENT SUMMARY - {run_id}")
    print("="*50)
    print(f"Orders placed: {len(placement_summary['placed'])}")
    print(f"Orders skipped: {len(placement_summary['skipped'])}")
    print(f"Errors: {len(placement_summary['errors'])}")
    
    if placement_summary['placed']:
        print("\nPlaced Orders:")
        for order in placement_summary['placed'][:10]:
            print(f"  {order['symbol']} - Order ID: {order.get('order_id', 'N/A')}")
    
    if placement_summary['errors']:
        print("\nErrors:")
        for error in placement_summary['errors']:
            print(f"  {error['symbol']}: {error['error']}")
    
    return placement_summary


def cmd_report(
    config_file: str,
    target_date: Optional[str]
) -> Dict:
    """Generate EOD report.
    
    Args:
        config_file: Path to config file
        target_date: Date to report on (YYYY-MM-DD)
        
    Returns:
        Report paths
    """
    logger.info("=== REPORT MODE ===")
    
    # Load config
    config = load_config(config_file)
    
    # Parse date
    if target_date:
        report_date = datetime.strptime(target_date, '%Y-%m-%d').date()
    else:
        report_date = date.today()
    
    # Get adapter
    adapter = get_adapter(config)
    
    # Generate report
    report_config = config['paper_trading']['reporting']
    report_result = generate_eod_report(adapter, report_date, report_config)
    
    # Print summary
    metrics = report_result['metrics']
    
    print("\n" + "="*50)
    print(f"END-OF-DAY REPORT - {report_date}")
    print("="*50)
    print(f"Starting Equity:  ${metrics['starting_equity']:>12,.2f}")
    print(f"Ending Equity:    ${metrics['ending_equity']:>12,.2f}")
    print(f"Daily P/L:        ${metrics['daily_pl']:>+12,.2f} ({metrics['daily_pl_pct']:+.2f}%)")
    print(f"Realized P/L:     ${metrics['pnl_realized']:>+12,.2f}")
    
    if metrics.get('pnl_unrealized'):
        print(f"Unrealized P/L:   ${metrics['pnl_unrealized']:>+12,.2f}")
    
    print(f"\nNew Entries: {metrics['new_entries']}")
    print(f"Exits: {metrics['exits']}")
    print(f"Open Positions: {metrics['position_count']}")
    print(f"Exposure: {metrics['exposure_pct']:.1f}%")
    
    print(f"\nReports saved to: {Path(report_result['markdown']).parent}")
    
    return report_result


def cmd_reconcile(config_file: str) -> Dict:
    """Run morning reconciliation."""
    logger.info("=== RECONCILE MODE ===")
    
    config = load_config(config_file)
    adapter = get_adapter(config)
    
    # Get today's run ID
    run_id = f"{date.today()}_scan"
    
    # Run reconciliation
    result = morning_reconcile(adapter, run_id, datetime.now())
    
    print("\n" + "="*50)
    print("RECONCILIATION SUMMARY")
    print("="*50)
    print(f"OPG orders cancelled: {result['opg_cancelled']}")
    print(f"OCO stops placed: {result['oco_placed']}")
    print(f"Partial fills handled: {result['partial_handled']}")
    
    if result['errors']:
        print(f"\nErrors: {len(result['errors'])}")
        for error in result['errors']:
            print(f"  - {error}")
    
    return result


def cmd_positions(config_file: str) -> Dict:
    """Show current positions."""
    logger.info("=== POSITIONS ===")
    
    config = load_config(config_file)
    adapter = get_adapter(config)
    
    positions = adapter.get_positions()
    account = adapter.get_account()
    
    print("\n" + "="*50)
    print("CURRENT POSITIONS")
    print("="*50)
    print(f"Account Equity: ${float(account['equity']):,.2f}")
    print(f"Cash: ${float(account['cash']):,.2f}")
    print(f"Positions: {len(positions)}")
    
    if positions:
        print("\n{:<8} {:>6} {:>10} {:>10} {:>12} {:>8}".format(
            "Symbol", "Qty", "Avg Cost", "Current", "Unreal P/L", "P/L %"
        ))
        print("-" * 65)
        
        total_unrealized = 0
        for pos in positions:
            symbol = pos['symbol']
            qty = int(pos['qty'])
            avg_cost = float(pos['avg_entry_price'])
            current = float(pos['current_price'])
            unrealized = float(pos['unrealized_pl'])
            pct = (unrealized / (avg_cost * abs(qty))) * 100 if qty != 0 else 0
            
            total_unrealized += unrealized
            
            print(f"{symbol:<8} {qty:>6} ${avg_cost:>9.2f} ${current:>9.2f} "
                  f"${unrealized:>+11.2f} {pct:>+7.2f}%")
        
        print("-" * 65)
        print(f"{'TOTAL':<8} {'':<6} {'':<10} {'':<10} ${total_unrealized:>+11.2f}")
    
    # Return actual positions data for API usage
    return {
        'positions': positions,
        'account': {
            'equity': float(account['equity']),
            'cash': float(account['cash'])
        },
        'count': len(positions)
    }


def cmd_close_all(config_file: str, reason: str = "Manual close") -> Dict:
    """Emergency close all positions."""
    logger.info("=== EMERGENCY CLOSE ALL ===")
    
    confirm = input("Are you sure you want to close ALL positions? (yes/no): ")
    if confirm.lower() != 'yes':
        print("Aborted")
        return {'status': 'aborted'}
    
    config = load_config(config_file)
    adapter = get_adapter(config)
    
    result = emergency_close_all(adapter, reason)
    
    print("\n" + "="*50)
    print("EMERGENCY CLOSE RESULTS")
    print("="*50)
    print(f"Positions closed: {len(result['closed'])}")
    print(f"Orders cancelled: {result.get('orders_cancelled', 0)}")
    print(f"Errors: {len(result['errors'])}")
    
    return result


def main():
    """Main CLI entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Paper Trading CLI")
    parser.add_argument('--config', default='config.yaml', help='Config file path')
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Scan command
    scan_parser = subparsers.add_parser('scan', help='Run scanner and generate intents')
    scan_parser.add_argument('--out-dir', default='state', help='Output directory')
    scan_parser.add_argument('--dry-run', action='store_true', help='Simulate without saving')
    
    # Place command
    place_parser = subparsers.add_parser('place', help='Place orders from intents')
    place_parser.add_argument('--run-id', help='Specific run ID')
    place_parser.add_argument('--dry-run', action='store_true', help='Simulate placement')
    
    # Report command
    report_parser = subparsers.add_parser('report', help='Generate EOD report')
    report_parser.add_argument('--date', help='Report date (YYYY-MM-DD)')
    
    # Reconcile command
    subparsers.add_parser('reconcile', help='Run morning reconciliation')
    
    # Positions command
    subparsers.add_parser('positions', help='Show current positions')
    
    # Close-all command
    close_parser = subparsers.add_parser('close-all', help='Emergency close all positions')
    close_parser.add_argument('--reason', default='Manual close', help='Reason for closing')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    try:
        if args.command == 'scan':
            cmd_scan(args.config, None, args.out_dir, args.dry_run)
        elif args.command == 'place':
            cmd_place(args.config, args.run_id, args.dry_run)
        elif args.command == 'report':
            cmd_report(args.config, args.date)
        elif args.command == 'reconcile':
            cmd_reconcile(args.config)
        elif args.command == 'positions':
            cmd_positions(args.config)
        elif args.command == 'close-all':
            cmd_close_all(args.config, args.reason)
            
    except Exception as e:
        logger.error(f"Command failed: {e}")
        raise


if __name__ == '__main__':
    main()