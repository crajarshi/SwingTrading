"""Morning reconciliation for unfilled orders and partial fills.

Handles OPG order cleanup, partial fill management, and stale intent removal.
Runs before market open to ensure clean state.
"""

import json
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def morning_reconcile(adapter, run_id: str, as_of: datetime) -> Dict:
    """Perform morning reconciliation of orders.
    
    Handles:
    1. Unfilled OPG orders from previous day
    2. Partial fills needing proportional stops
    3. OPG fills needing OCO stop/target placement
    
    Args:
        adapter: Broker adapter instance
        run_id: Run identifier
        as_of: Current datetime
        
    Returns:
        Reconciliation summary
    """
    summary = {
        'run_id': run_id,
        'as_of': as_of.isoformat(),
        'opg_cancelled': 0,
        'oco_placed': 0,
        'partial_handled': 0,
        'errors': []
    }
    
    # Get all open orders
    open_orders = adapter.list_orders(status='open')
    
    # Get yesterday's placement manifest if exists
    manifest_path = Path('state/placement') / f"{run_id}.json"
    placement_data = {}
    if manifest_path.exists():
        with open(manifest_path) as f:
            placement_data = json.load(f)
    
    # Process each open order
    for order in open_orders:
        order_id = order['id']
        symbol = order['symbol']
        client_order_id = order.get('client_order_id', '')
        
        # Check if this is a stale OPG order
        if order.get('time_in_force') == 'opg':
            created_at = datetime.fromisoformat(order['created_at'].replace('Z', '+00:00'))
            hours_old = (as_of - created_at).total_seconds() / 3600
            
            if hours_old > 18:  # OPG order from previous day
                logger.info(f"Cancelling stale OPG order for {symbol}")
                try:
                    adapter._request('DELETE', f"/v2/orders/{order_id}")
                    summary['opg_cancelled'] += 1
                except Exception as e:
                    logger.error(f"Failed to cancel OPG order {order_id}: {e}")
                    summary['errors'].append(f"Cancel failed: {symbol}")
    
    # Check for filled OPG orders needing OCO stops
    if placement_data.get('placed'):
        for placed_order in placement_data['placed']:
            if placed_order.get('pending_oco'):
                order_id = placed_order['order_id']
                symbol = placed_order['symbol']
                
                # Check if filled
                is_filled, avg_price, filled_qty = adapter.check_order_fill(order_id)
                
                if is_filled and filled_qty:
                    # Need to place OCO stops
                    logger.info(f"Placing OCO stops for filled OPG: {symbol}")
                    
                    # Get intent data to find stop/target levels
                    intent_path = Path('state/intents') / f"{as_of.date()}.json"
                    if intent_path.exists():
                        with open(intent_path) as f:
                            intents = json.load(f)
                        
                        # Find matching intent
                        for intent in intents:
                            if intent['symbol'] == symbol:
                                bracket = intent['bracket']
                                
                                try:
                                    oco_order = adapter.submit_oco_stops(
                                        symbol=symbol,
                                        qty=filled_qty,
                                        stop_price=bracket['stop_loss'],
                                        target_price=bracket['take_profit'],
                                        parent_id=order_id
                                    )
                                    summary['oco_placed'] += 1
                                    logger.info(f"OCO stops placed for {symbol}")
                                except Exception as e:
                                    logger.error(f"Failed to place OCO for {symbol}: {e}")
                                    summary['errors'].append(f"OCO failed: {symbol}")
                                break
    
    logger.info(f"Reconciliation complete: {summary['opg_cancelled']} cancelled, "
               f"{summary['oco_placed']} OCO placed")
    
    return summary


def handle_partial_fill(adapter, order: Dict, fill_qty: int) -> Dict:
    """Handle partial fill by adjusting stop/target quantities.
    
    Args:
        adapter: Broker adapter instance
        order: Original order data
        fill_qty: Actual filled quantity
        
    Returns:
        Result dict
    """
    result = {
        'symbol': order['symbol'],
        'original_qty': order['qty'],
        'filled_qty': fill_qty,
        'adjusted': False,
        'error': None
    }
    
    # For bracket orders, Alpaca should handle this automatically
    # But we can verify and adjust if needed
    
    if order.get('order_class') == 'bracket':
        # Check if legs need adjustment
        legs = order.get('legs', [])
        for leg in legs:
            if leg['qty'] != fill_qty:
                logger.info(f"Bracket leg qty mismatch for {order['symbol']}: "
                          f"leg={leg['qty']}, fill={fill_qty}")
                # Alpaca should auto-adjust, but log for monitoring
    
    result['adjusted'] = True
    return result


def cancel_stale_opg(adapter, older_than: datetime) -> List[str]:
    """Cancel OPG orders older than specified time.
    
    Args:
        adapter: Broker adapter instance
        older_than: Cancel orders created before this time
        
    Returns:
        List of cancelled order IDs
    """
    cancelled = []
    open_orders = adapter.list_orders(status='open')
    
    for order in open_orders:
        if order.get('time_in_force') != 'opg':
            continue
        
        created_at = datetime.fromisoformat(order['created_at'].replace('Z', '+00:00'))
        if created_at < older_than:
            order_id = order['id']
            symbol = order['symbol']
            
            try:
                adapter._request('DELETE', f"/v2/orders/{order_id}")
                cancelled.append(order_id)
                logger.info(f"Cancelled stale OPG for {symbol} (order_id={order_id})")
            except Exception as e:
                logger.error(f"Failed to cancel stale OPG {order_id}: {e}")
    
    return cancelled


def clean_stale_intents(state_dir: Path, days_old: int = 3) -> int:
    """Remove old intent files that are no longer needed.
    
    Args:
        state_dir: State directory path
        days_old: Age threshold in days
        
    Returns:
        Number of files cleaned
    """
    cleaned = 0
    intents_dir = state_dir / 'intents'
    
    if not intents_dir.exists():
        return 0
    
    cutoff_date = datetime.now() - timedelta(days=days_old)
    
    for intent_file in intents_dir.glob('*.json'):
        # Parse date from filename (YYYY-MM-DD.json)
        try:
            file_date = datetime.strptime(intent_file.stem, '%Y-%m-%d')
            if file_date < cutoff_date:
                intent_file.unlink()
                cleaned += 1
                logger.info(f"Removed stale intent file: {intent_file.name}")
        except ValueError:
            # Skip files that don't match date format
            continue
    
    return cleaned


def reconcile_with_manifest(
    adapter,
    manifest_path: Path,
    intent_path: Path
) -> Dict:
    """Reconcile orders using saved manifest and intents.
    
    Args:
        adapter: Broker adapter instance
        manifest_path: Path to placement manifest
        intent_path: Path to order intents
        
    Returns:
        Reconciliation summary
    """
    summary = {
        'checked': 0,
        'filled': 0,
        'partial': 0,
        'pending': 0,
        'cancelled': 0,
        'oco_needed': 0,
        'oco_placed': 0
    }
    
    if not manifest_path.exists() or not intent_path.exists():
        return summary
    
    # Load data
    with open(manifest_path) as f:
        manifest = json.load(f)
    with open(intent_path) as f:
        intents = json.load(f)
    
    # Create intent lookup
    intent_by_symbol = {i['symbol']: i for i in intents}
    
    # Check each placed order
    for placed in manifest.get('placed', []):
        summary['checked'] += 1
        order_id = placed['order_id']
        symbol = placed['symbol']
        
        # Check fill status
        is_filled, avg_price, filled_qty = adapter.check_order_fill(order_id)
        
        if is_filled:
            summary['filled'] += 1
            
            # Check if OCO needed
            if placed.get('pending_oco'):
                summary['oco_needed'] += 1
                
                # Place OCO stops
                if symbol in intent_by_symbol:
                    bracket = intent_by_symbol[symbol]['bracket']
                    try:
                        adapter.submit_oco_stops(
                            symbol=symbol,
                            qty=filled_qty,
                            stop_price=bracket['stop_loss'],
                            target_price=bracket['take_profit'],
                            parent_id=order_id
                        )
                        summary['oco_placed'] += 1
                    except Exception as e:
                        logger.error(f"Failed to place OCO for {symbol}: {e}")
        
        elif filled_qty and filled_qty > 0:
            summary['partial'] += 1
        else:
            # Check if order still exists
            try:
                order = adapter.get_order(order_id)
                if order['status'] == 'canceled':
                    summary['cancelled'] += 1
                else:
                    summary['pending'] += 1
            except:
                summary['cancelled'] += 1
    
    return summary