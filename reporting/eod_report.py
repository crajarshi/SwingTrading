"""End-of-day reporting for paper trading system.

Generates daily reports with P&L, positions, and performance metrics.
"""

import json
import csv
import logging
from pathlib import Path
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def load_yesterday_equity(date: datetime) -> float:
    """Load previous day's ending equity from snapshot.
    
    Args:
        date: Current date
        
    Returns:
        Yesterday's ending equity (0 if not found)
    """
    # Look for previous trading day's snapshot
    snapshot_dir = Path('state/equity_snapshots')
    
    # Try previous days (handle weekends/holidays)
    for days_back in range(1, 5):
        check_date = date - timedelta(days=days_back)
        snapshot_path = snapshot_dir / f"{check_date.date()}.json"
        
        if snapshot_path.exists():
            with open(snapshot_path) as f:
                data = json.load(f)
                return data.get('ending_equity', 0)
    
    # No previous snapshot found
    logger.warning("No previous equity snapshot found")
    return 0


def persist_equity_snapshot(adapter, date: datetime) -> float:
    """Save current equity snapshot for future reference.
    
    Args:
        adapter: Broker adapter instance
        date: Current date
        
    Returns:
        Current equity value
    """
    account = adapter.get_account()
    equity = float(account.get('equity', 0))
    
    # Create snapshot
    snapshot = {
        'date': date.date().isoformat(),
        'ending_equity': equity,
        'cash': float(account.get('cash', 0)),
        'buying_power': float(account.get('buying_power', 0)),
        'timestamp': datetime.now().isoformat()
    }
    
    # Save to file
    snapshot_dir = Path('state/equity_snapshots')
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    
    snapshot_path = snapshot_dir / f"{date.date()}.json"
    with open(snapshot_path, 'w') as f:
        json.dump(snapshot, f, indent=2)
    
    logger.info(f"Saved equity snapshot: ${equity:,.2f}")
    
    return equity


def collect_day_data(
    adapter,
    target_date: date,
    include_unrealized: bool
) -> Dict:
    """Collect all data for the trading day.
    
    Args:
        adapter: Broker adapter instance
        target_date: Date to report on
        include_unrealized: Whether to include unrealized P&L
        
    Returns:
        Day data snapshot
    """
    # Get account info
    account = adapter.get_account()
    
    # Get positions
    positions = adapter.get_positions()
    
    # Process positions
    position_data = []
    total_unrealized = 0
    
    for pos in positions:
        symbol = pos['symbol']
        qty = int(pos['qty'])
        avg_entry = float(pos['avg_entry_price'])
        market_value = float(pos['market_value'])
        current_price = float(pos['current_price'])
        unrealized_pl = float(pos['unrealized_pl'])
        unrealized_pct = (unrealized_pl / (avg_entry * abs(qty))) * 100 if qty != 0 else 0
        
        position_data.append({
            'symbol': symbol,
            'qty': qty,
            'avg_entry': avg_entry,
            'market_price': current_price,
            'market_value': market_value,
            'unrealized_pl': unrealized_pl,
            'unrealized_pct': unrealized_pct
        })
        
        total_unrealized += unrealized_pl
    
    # Get activities (fills) for the day
    start_iso = f"{target_date}T00:00:00Z"
    end_iso = f"{target_date}T23:59:59Z"
    activities = adapter.get_activities(start_iso, end_iso)
    
    # Process fills
    fills = []
    realized_pl = 0
    
    for activity in activities:
        if activity.get('activity_type') == 'FILL':
            symbol = activity['symbol']
            qty = int(activity['qty'])
            price = float(activity['price'])
            side = activity['side']
            
            fills.append({
                'symbol': symbol,
                'side': side,
                'qty': qty,
                'price': price,
                'timestamp': activity['transaction_time']
            })
            
            # Calculate realized P&L (simplified - would need entry tracking)
            if side == 'sell':
                # This is a simplification - real P&L needs entry price tracking
                # For now, we'll use activity P&L if provided
                if 'pl' in activity:
                    realized_pl += float(activity['pl'])
    
    # Get starting equity
    starting_equity = load_yesterday_equity(datetime.combine(target_date, datetime.min.time()))
    if starting_equity == 0:
        # First day - use current equity minus today's P&L
        starting_equity = float(account['equity']) - realized_pl - total_unrealized
    
    return {
        'date': target_date.isoformat(),
        'starting_equity': starting_equity,
        'ending_equity': float(account['equity']),
        'cash': float(account['cash']),
        'positions': position_data,
        'fills': fills,
        'activities': activities,
        'realized_pl': realized_pl,
        'unrealized_pl': total_unrealized if include_unrealized else 0
    }


def calculate_daily_pnl(starting: float, ending: float, realized: float) -> Dict:
    """Calculate daily P&L metrics.
    
    Args:
        starting: Starting equity
        ending: Ending equity
        realized: Realized P&L
        
    Returns:
        P&L metrics
    """
    daily_pl = ending - starting
    daily_pl_pct = (daily_pl / starting * 100) if starting > 0 else 0
    
    return {
        'daily_pl': daily_pl,
        'daily_pl_pct': daily_pl_pct,
        'realized_pl': realized,
        'unrealized_change': daily_pl - realized
    }


def compute_eod_metrics(snapshot: Dict) -> Dict:
    """Compute end-of-day performance metrics.
    
    Args:
        snapshot: Day data snapshot
        
    Returns:
        EOD metrics dict
    """
    # Basic metrics
    metrics = {
        'date': snapshot['date'],
        'starting_equity': snapshot['starting_equity'],
        'ending_equity': snapshot['ending_equity'],
        'cash': snapshot['cash'],
        'pnl_realized': snapshot['realized_pl'],
        'pnl_unrealized': snapshot.get('unrealized_pl', 0)
    }
    
    # Calculate daily P&L
    pnl_data = calculate_daily_pnl(
        snapshot['starting_equity'],
        snapshot['ending_equity'],
        snapshot['realized_pl']
    )
    metrics.update(pnl_data)
    
    # Count trades
    buys = sum(1 for f in snapshot['fills'] if f['side'] == 'buy')
    sells = sum(1 for f in snapshot['fills'] if f['side'] == 'sell')
    metrics['new_entries'] = buys
    metrics['exits'] = sells
    
    # Calculate win rate (simplified)
    if sells > 0:
        # Would need proper entry/exit matching
        metrics['win_rate'] = 0  # Placeholder
        metrics['avg_win'] = 0
        metrics['avg_loss'] = 0
        metrics['payoff_ratio'] = 0
    else:
        metrics['win_rate'] = 0
        metrics['avg_win'] = 0
        metrics['avg_loss'] = 0
        metrics['payoff_ratio'] = 0
    
    # Portfolio metrics
    total_value = sum(p['market_value'] for p in snapshot['positions'])
    metrics['exposure_pct'] = (total_value / snapshot['ending_equity'] * 100) if snapshot['ending_equity'] > 0 else 0
    metrics['position_count'] = len(snapshot['positions'])
    
    # Turnover (simplified)
    trade_volume = sum(f['qty'] * f['price'] for f in snapshot['fills'])
    metrics['turnover'] = trade_volume / snapshot['ending_equity'] if snapshot['ending_equity'] > 0 else 0
    
    return metrics


def build_top_contributors(
    snapshot: Dict,
    n: int,
    include_unrealized: bool
) -> List[Dict]:
    """Build list of top P&L contributors.
    
    Args:
        snapshot: Day data snapshot
        n: Number of top contributors
        include_unrealized: Whether to include unrealized P&L
        
    Returns:
        List of top contributors
    """
    contributors = []
    
    # Add realized P&L from closed positions
    # This is simplified - would need proper tracking
    for fill in snapshot['fills']:
        if fill['side'] == 'sell':
            # Estimate P&L (would need entry price)
            contributors.append({
                'symbol': fill['symbol'],
                'pnl': 0,  # Would calculate from entry/exit
                'direction': 'long',
                'type': 'realized'
            })
    
    # Add unrealized P&L from open positions
    if include_unrealized:
        for pos in snapshot['positions']:
            if pos['unrealized_pl'] != 0:
                contributors.append({
                    'symbol': pos['symbol'],
                    'pnl': pos['unrealized_pl'],
                    'direction': 'long',
                    'type': 'unrealized'
                })
    
    # Sort by absolute P&L and take top N
    contributors.sort(key=lambda x: abs(x['pnl']), reverse=True)
    
    return contributors[:n]


def render_markdown_report(
    metrics: Dict,
    snapshot: Dict,
    out_dir: Path
) -> Path:
    """Generate markdown report file.
    
    Args:
        metrics: EOD metrics
        snapshot: Day data snapshot
        out_dir: Output directory
        
    Returns:
        Path to report file
    """
    # Ensure directory exists
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # Build report content
    lines = [
        "# End-of-Day Trading Report",
        f"**Date:** {metrics['date']}",
        "",
        "## Equity & P/L Summary",
        "",
        f"- **Starting Equity:** ${metrics['starting_equity']:,.2f}",
        f"- **Ending Equity:** ${metrics['ending_equity']:,.2f}",
        f"- **Daily P/L:** ${metrics['daily_pl']:+,.2f} ({metrics['daily_pl_pct']:+.2f}%)",
        f"- **Realized P/L:** ${metrics['pnl_realized']:+,.2f}",
    ]
    
    if metrics.get('pnl_unrealized'):
        lines.append(f"- **Unrealized P/L:** ${metrics['pnl_unrealized']:+,.2f}")
    
    lines.extend([
        "",
        "## Trading Activity",
        "",
        f"- **New Entries:** {metrics['new_entries']}",
        f"- **Exits:** {metrics['exits']}",
        f"- **Open Positions:** {metrics['position_count']}",
        f"- **Portfolio Exposure:** {metrics['exposure_pct']:.1f}%",
        ""
    ])
    
    # Add positions table if any
    if snapshot['positions']:
        lines.extend([
            "## Open Positions",
            "",
            "| Symbol | Qty | Avg Entry | Current | Unrealized P/L | Unrealized % |",
            "|--------|-----|-----------|---------|----------------|--------------|"
        ])
        
        for pos in snapshot['positions']:
            lines.append(
                f"| {pos['symbol']} | {pos['qty']} | "
                f"${pos['avg_entry']:.2f} | ${pos['market_price']:.2f} | "
                f"${pos['unrealized_pl']:+.2f} | {pos['unrealized_pct']:+.2f}% |"
            )
        lines.append("")
    
    # Add trades table if any
    if snapshot['fills']:
        lines.extend([
            "## Today's Trades",
            "",
            "| Time | Symbol | Side | Qty | Price |",
            "|------|--------|------|-----|-------|"
        ])
        
        for fill in snapshot['fills']:
            time_str = fill['timestamp'].split('T')[1][:8] if 'T' in fill['timestamp'] else fill['timestamp']
            lines.append(
                f"| {time_str} | {fill['symbol']} | {fill['side'].upper()} | "
                f"{fill['qty']} | ${fill['price']:.2f} |"
            )
        lines.append("")
    
    # Add top contributors
    contributors = build_top_contributors(snapshot, 5, metrics.get('pnl_unrealized', 0) != 0)
    if contributors:
        lines.extend([
            "## Top 5 Contributors",
            "",
            "| Symbol | P/L | Type |",
            "|--------|-----|------|"
        ])
        
        for contrib in contributors:
            lines.append(
                f"| {contrib['symbol']} | ${contrib['pnl']:+.2f} | {contrib['type']} |"
            )
        lines.append("")
    
    # Add footer
    lines.extend([
        "---",
        f"*Report generated at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ET*",
        "",
        "*Note: Paper trading account - not real money*"
    ])
    
    # Write file
    report_path = out_dir / "eod_report.md"
    with open(report_path, 'w') as f:
        f.write('\n'.join(lines))
    
    logger.info(f"Generated markdown report: {report_path}")
    
    return report_path


def write_trades_csv(snapshot: Dict, out_dir: Path) -> Path:
    """Write trades to CSV file.
    
    Args:
        snapshot: Day data snapshot
        out_dir: Output directory
        
    Returns:
        Path to CSV file
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "eod_trades.csv"
    
    with open(csv_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'date', 'symbol', 'side', 'qty', 'price', 'timestamp'
        ])
        writer.writeheader()
        
        for fill in snapshot['fills']:
            writer.writerow({
                'date': snapshot['date'],
                'symbol': fill['symbol'],
                'side': fill['side'],
                'qty': fill['qty'],
                'price': fill['price'],
                'timestamp': fill['timestamp']
            })
    
    logger.info(f"Wrote trades CSV: {csv_path}")
    
    return csv_path


def write_summary_json(metrics: Dict, out_dir: Path) -> Path:
    """Write summary metrics to JSON file.
    
    Args:
        metrics: EOD metrics
        out_dir: Output directory
        
    Returns:
        Path to JSON file
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "eod_summary.json"
    
    with open(json_path, 'w') as f:
        json.dump(metrics, f, indent=2, default=str)
    
    logger.info(f"Wrote summary JSON: {json_path}")
    
    return json_path


def generate_eod_report(
    adapter,
    target_date: date,
    config: Dict
) -> Dict:
    """Generate complete EOD report.
    
    Args:
        adapter: Broker adapter instance
        target_date: Date to report on
        config: Reporting configuration
        
    Returns:
        Paths to generated report files
    """
    # Collect data
    include_unrealized = config.get('include_unrealized', True)
    snapshot = collect_day_data(adapter, target_date, include_unrealized)
    
    # Compute metrics
    metrics = compute_eod_metrics(snapshot)
    
    # Persist equity snapshot
    persist_equity_snapshot(adapter, datetime.combine(target_date, datetime.min.time()))
    
    # Generate reports
    out_dir = Path(config.get('out_dir', 'reports')) / target_date.isoformat()
    
    md_path = render_markdown_report(metrics, snapshot, out_dir)
    csv_path = write_trades_csv(snapshot, out_dir)
    json_path = write_summary_json(metrics, out_dir)
    
    return {
        'markdown': str(md_path),
        'csv': str(csv_path),
        'json': str(json_path),
        'metrics': metrics
    }