"""Position management for exits and risk control.

Handles time-based exits, earnings guards, and emergency closures.
"""

import logging
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def close_positions_by_age(
    adapter,
    max_days: int,
    as_of: date
) -> Dict:
    """Close positions older than specified number of days.
    
    Args:
        adapter: Broker adapter instance
        max_days: Maximum holding period in days
        as_of: Current date
        
    Returns:
        Summary of closed positions
    """
    summary = {
        'closed': [],
        'skipped': [],
        'errors': [],
        'as_of': as_of.isoformat()
    }
    
    # Get all open positions
    positions = adapter.get_positions()
    
    for position in positions:
        symbol = position['symbol']
        qty = int(position['qty'])
        side = position['side']
        
        # Parse entry time
        # Alpaca doesn't directly provide entry time, need to check activities
        # For now, we'll use a workaround with order history
        # In production, you'd track this in your state management
        
        # Get recent orders for this symbol
        orders = adapter.list_orders(status='all')
        entry_order = None
        
        for order in orders:
            if (order['symbol'] == symbol and 
                order['side'] == 'buy' and 
                order['status'] == 'filled'):
                entry_order = order
                break
        
        if not entry_order:
            logger.warning(f"Could not find entry order for {symbol}")
            summary['skipped'].append({
                'symbol': symbol,
                'reason': 'no_entry_found'
            })
            continue
        
        # Calculate age
        filled_at = datetime.fromisoformat(entry_order['filled_at'].replace('Z', '+00:00'))
        position_age = (datetime.now(filled_at.tzinfo) - filled_at).days
        
        if position_age >= max_days:
            logger.info(f"Closing {symbol} - aged {position_age} days (max={max_days})")
            
            try:
                # Place market sell order
                order = adapter.submit_bracket_order(
                    symbol=symbol,
                    qty=abs(qty),
                    side='sell' if side == 'long' else 'buy',
                    entry_type='market',
                    time_in_force='day',
                    limit_price=None,
                    stop_loss=0,  # Not used for market order
                    take_profit=0,  # Not used for market order
                    client_order_id=f"time_exit_{symbol}_{as_of}",
                    open_only=False
                )
                
                summary['closed'].append({
                    'symbol': symbol,
                    'qty': qty,
                    'age_days': position_age,
                    'order_id': order.get('id')
                })
                
            except Exception as e:
                logger.error(f"Failed to close {symbol}: {e}")
                summary['errors'].append({
                    'symbol': symbol,
                    'error': str(e)
                })
    
    logger.info(f"Age-based exits: {len(summary['closed'])} closed, "
               f"{len(summary['skipped'])} skipped")
    
    return summary


def close_positions_with_earnings(
    adapter,
    earnings_map: Dict[str, date],
    pre_days: int,
    as_of: date
) -> Dict:
    """Close positions with upcoming earnings.
    
    Args:
        adapter: Broker adapter instance
        earnings_map: Dict mapping symbols to earnings dates
        pre_days: Days before earnings to exit
        as_of: Current date
        
    Returns:
        Summary of closed positions
    """
    summary = {
        'closed': [],
        'skipped': [],
        'errors': [],
        'as_of': as_of.isoformat()
    }
    
    if not earnings_map:
        logger.info("No earnings data available")
        return summary
    
    # Get all open positions
    positions = adapter.get_positions()
    
    for position in positions:
        symbol = position['symbol']
        qty = int(position['qty'])
        side = position['side']
        
        # Check for upcoming earnings
        if symbol in earnings_map:
            earnings_date = earnings_map[symbol]
            if isinstance(earnings_date, str):
                earnings_date = datetime.fromisoformat(earnings_date).date()
            
            days_until_earnings = (earnings_date - as_of).days
            
            if 0 <= days_until_earnings <= pre_days:
                logger.info(f"Closing {symbol} - earnings in {days_until_earnings} days")
                
                try:
                    # Place market sell order
                    order = adapter.submit_bracket_order(
                        symbol=symbol,
                        qty=abs(qty),
                        side='sell' if side == 'long' else 'buy',
                        entry_type='market',
                        time_in_force='day',
                        limit_price=None,
                        stop_loss=0,
                        take_profit=0,
                        client_order_id=f"earnings_exit_{symbol}_{as_of}",
                        open_only=False
                    )
                    
                    summary['closed'].append({
                        'symbol': symbol,
                        'qty': qty,
                        'earnings_date': earnings_date.isoformat(),
                        'days_until': days_until_earnings,
                        'order_id': order.get('id')
                    })
                    
                except Exception as e:
                    logger.error(f"Failed to close {symbol}: {e}")
                    summary['errors'].append({
                        'symbol': symbol,
                        'error': str(e)
                    })
        else:
            summary['skipped'].append({
                'symbol': symbol,
                'reason': 'no_earnings_data'
            })
    
    logger.info(f"Earnings exits: {len(summary['closed'])} closed, "
               f"{len(summary['skipped'])} skipped")
    
    return summary


def emergency_close_all(adapter, reason: str) -> Dict:
    """Close all open positions immediately.
    
    Args:
        adapter: Broker adapter instance
        reason: Reason for emergency closure
        
    Returns:
        Summary of closed positions
    """
    summary = {
        'closed': [],
        'errors': [],
        'reason': reason,
        'timestamp': datetime.now().isoformat()
    }
    
    logger.warning(f"EMERGENCY CLOSE ALL: {reason}")
    
    # Cancel all open orders first
    cancelled = adapter.cancel_open_orders()
    summary['orders_cancelled'] = cancelled
    
    # Get all positions
    positions = adapter.get_positions()
    
    for position in positions:
        symbol = position['symbol']
        qty = int(position['qty'])
        side = position['side']
        
        try:
            # Place market order to close
            order = adapter.submit_bracket_order(
                symbol=symbol,
                qty=abs(qty),
                side='sell' if side == 'long' else 'buy',
                entry_type='market',
                time_in_force='day',
                limit_price=None,
                stop_loss=0,
                take_profit=0,
                client_order_id=f"emergency_{symbol}_{datetime.now().timestamp()}",
                open_only=False
            )
            
            summary['closed'].append({
                'symbol': symbol,
                'qty': qty,
                'order_id': order.get('id')
            })
            
            logger.info(f"Emergency closed {symbol} ({qty} shares)")
            
        except Exception as e:
            logger.error(f"Failed to emergency close {symbol}: {e}")
            summary['errors'].append({
                'symbol': symbol,
                'qty': qty,
                'error': str(e)
            })
    
    logger.warning(f"Emergency closure complete: {len(summary['closed'])} positions closed, "
                  f"{len(summary['errors'])} errors")
    
    return summary


def get_position_ages(adapter) -> Dict[str, int]:
    """Get age in days for all open positions.
    
    Args:
        adapter: Broker adapter instance
        
    Returns:
        Dict mapping symbol to age in days
    """
    ages = {}
    positions = adapter.get_positions()
    
    # This is a simplified version - in production you'd track entry dates
    # in your state management system
    for position in positions:
        symbol = position['symbol']
        # Default to 0 if we can't determine age
        ages[symbol] = 0
    
    return ages


def should_reduce_position(
    symbol: str,
    position_size: int,
    current_price: float,
    entry_price: float,
    atr: float,
    profit_target_mult: float = 2.0
) -> tuple[bool, int]:
    """Determine if position should be partially reduced.
    
    Args:
        symbol: Stock symbol
        position_size: Current position size
        current_price: Current market price
        entry_price: Entry price
        atr: Average True Range
        profit_target_mult: Profit level to start reducing (in ATR multiples)
        
    Returns:
        Tuple of (should_reduce, shares_to_sell)
    """
    # Calculate profit in ATR terms
    profit = current_price - entry_price
    profit_in_atr = profit / atr if atr > 0 else 0
    
    # Start reducing at 2x ATR profit
    if profit_in_atr >= profit_target_mult:
        # Sell 1/3 of position
        shares_to_sell = max(1, position_size // 3)
        return True, shares_to_sell
    
    return False, 0


def manage_position_risk(
    adapter,
    symbol: str,
    config: Dict
) -> Dict:
    """Comprehensive position risk management.
    
    Args:
        adapter: Broker adapter instance
        symbol: Stock symbol
        config: Risk configuration
        
    Returns:
        Management action taken
    """
    result = {
        'symbol': symbol,
        'action': 'none',
        'details': {}
    }
    
    # Get position
    position = adapter.get_position(symbol)
    if not position:
        result['action'] = 'no_position'
        return result
    
    qty = int(position['qty'])
    avg_cost = float(position['avg_entry_price'])
    current_price = float(position['current_price'])
    unrealized_pl = float(position['unrealized_pl'])
    
    # Check stop loss
    stop_mult = config.get('stop_atr_mult', 1.5)
    # Would need ATR data here - simplified for now
    
    # Check time exit
    # Would need entry date tracking - simplified for now
    
    # Check profit taking
    if unrealized_pl > 0:
        profit_pct = (unrealized_pl / (avg_cost * qty)) * 100
        if profit_pct > 10:  # Take profits above 10%
            result['action'] = 'profit_take'
            result['details'] = {
                'profit_pct': profit_pct,
                'unrealized_pl': unrealized_pl
            }
    
    return result