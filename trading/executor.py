"""Order executor with idempotent placement and fallback strategies.

Handles the actual placement of orders via the broker adapter,
with support for OPG→OCO→DAY fallback cascade.
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def ensure_not_already_placed(adapter, client_order_id: str) -> bool:
    """Check if order with client_order_id already exists.
    
    Args:
        adapter: Broker adapter instance
        client_order_id: Client order ID to check
        
    Returns:
        True if safe to place (no existing order), False if already exists
    """
    try:
        existing = adapter.get_order_by_client_id(client_order_id)
        if existing:
            logger.info(f"Order already placed: {client_order_id} "
                       f"(status={existing.get('status')})")
            return False
        return True
    except Exception as e:
        logger.error(f"Error checking existing order: {e}")
        # Err on the side of caution - don't place if we can't check
        return False


def place_with_fallback(adapter, intent: Dict, fallback_strategy: str) -> Dict:
    """Place order with fallback strategy based on broker capabilities.
    
    Strategies:
    - 'opg_bracket': Try OPG with bracket (rarely supported)
    - 'opg_then_oco': Place OPG, then add OCO stops after fill
    - 'day_bracket': Regular day bracket order
    
    Args:
        adapter: Broker adapter instance
        intent: Order intent dict
        fallback_strategy: Strategy to use
        
    Returns:
        Placement result dict
    """
    symbol = intent['symbol']
    qty = intent['qty']
    entry = intent['entry']
    bracket = intent['bracket']
    client_order_id = intent['client_order_id']
    
    result = {
        'symbol': symbol,
        'client_order_id': client_order_id,
        'strategy_used': fallback_strategy,
        'success': False,
        'order_id': None,
        'error': None
    }
    
    try:
        if fallback_strategy == 'opg_bracket':
            # Try OPG with bracket (usually not supported)
            logger.info(f"Attempting OPG+bracket for {symbol}")
            order = adapter.submit_bracket_order(
                symbol=symbol,
                qty=qty,
                side='buy',
                entry_type=entry['type'],
                time_in_force='opg',
                limit_price=entry.get('limit_price'),
                stop_loss=bracket['stop_loss'],
                take_profit=bracket['take_profit'],
                client_order_id=client_order_id,
                open_only=True
            )
            result['success'] = True
            result['order_id'] = order.get('id')
            
        elif fallback_strategy == 'opg_then_oco':
            # Place OPG entry only (OCO stops added after fill in reconciliation)
            logger.info(f"Placing OPG entry for {symbol} (OCO stops pending fill)")
            
            if entry['type'] == 'limit':
                order = adapter.submit_opg_entry(
                    symbol=symbol,
                    qty=qty,
                    limit_price=entry['limit_price'],
                    client_order_id=client_order_id
                )
            else:
                # Market-on-open
                order = adapter.submit_bracket_order(
                    symbol=symbol,
                    qty=qty,
                    side='buy',
                    entry_type='market',
                    time_in_force='opg',
                    limit_price=None,
                    stop_loss=bracket['stop_loss'],  # Will be ignored
                    take_profit=bracket['take_profit'],  # Will be ignored
                    client_order_id=client_order_id,
                    open_only=True
                )
            
            result['success'] = True
            result['order_id'] = order.get('id')
            result['pending_oco'] = True  # Flag for reconciliation
            
        else:  # 'day_bracket' or default
            # Regular day bracket order
            logger.info(f"Placing day bracket for {symbol}")
            order = adapter.submit_bracket_order(
                symbol=symbol,
                qty=qty,
                side='buy',
                entry_type=entry['type'],
                time_in_force='day',
                limit_price=entry.get('limit_price'),
                stop_loss=bracket['stop_loss'],
                take_profit=bracket['take_profit'],
                client_order_id=client_order_id,
                open_only=False
            )
            result['success'] = True
            result['order_id'] = order.get('id')
            
    except Exception as e:
        logger.error(f"Failed to place order for {symbol}: {e}")
        result['error'] = str(e)
    
    return result


def place_orders(
    adapter,
    intents: List[Dict],
    run_id: str,
    dry_run: bool = False
) -> Dict:
    """Place multiple orders from intents.
    
    Args:
        adapter: Broker adapter instance
        intents: List of order intents
        run_id: Run identifier
        dry_run: If True, simulate without placing
        
    Returns:
        Placement summary dict
    """
    summary = {
        'run_id': run_id,
        'placed': [],
        'skipped': [],
        'errors': [],
        'dry_run': dry_run
    }
    
    if dry_run:
        logger.info(f"DRY RUN: Would place {len(intents)} orders")
        for intent in intents:
            summary['placed'].append({
                'symbol': intent['symbol'],
                'qty': intent['qty'],
                'client_order_id': intent['client_order_id'],
                'dry_run': True
            })
        return summary
    
    # Determine fallback strategy based on order type
    # Check if any orders are market orders (not OPG)
    has_market_orders = any(intent['entry'].get('open_only') == False for intent in intents)
    
    if has_market_orders:
        # Use day bracket for market orders
        fallback_strategy = 'day_bracket'
    elif adapter.supports_opg_bracket():
        fallback_strategy = 'opg_bracket'
    else:
        # Default to OPG then OCO for Alpaca
        fallback_strategy = 'opg_then_oco'
    
    logger.info(f"Placing {len(intents)} orders with strategy: {fallback_strategy}")
    
    for intent in intents:
        client_order_id = intent['client_order_id']
        
        # Check if already placed (idempotency)
        if not ensure_not_already_placed(adapter, client_order_id):
            summary['skipped'].append({
                'symbol': intent['symbol'],
                'reason': 'duplicate',
                'client_order_id': client_order_id
            })
            continue
        
        # Place with fallback
        result = place_with_fallback(adapter, intent, fallback_strategy)
        
        if result['success']:
            summary['placed'].append({
                'symbol': result['symbol'],
                'order_id': result['order_id'],
                'client_order_id': result['client_order_id'],
                'strategy': result['strategy_used'],
                'pending_oco': result.get('pending_oco', False)
            })
        else:
            summary['errors'].append({
                'symbol': result['symbol'],
                'error': result['error'],
                'client_order_id': result['client_order_id']
            })
    
    logger.info(f"Placement complete: {len(summary['placed'])} placed, "
               f"{len(summary['skipped'])} skipped, {len(summary['errors'])} errors")
    
    return summary


def write_orders_log(entries: List[Dict], log_path: Path) -> Path:
    """Append order entries to log file (JSONL format).
    
    Args:
        entries: List of order entries to log
        log_path: Path to log file
        
    Returns:
        Path to log file
    """
    # Ensure directory exists
    log_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Append each entry as a JSON line
    with open(log_path, 'a') as f:
        for entry in entries:
            # Add timestamp
            entry['logged_at'] = datetime.now().isoformat()
            f.write(json.dumps(entry, default=str) + '\n')
    
    logger.info(f"Logged {len(entries)} entries to {log_path}")
    
    return log_path