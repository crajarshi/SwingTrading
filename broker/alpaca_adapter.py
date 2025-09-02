"""Alpaca paper trading API adapter.

Provides idempotent wrapper over Alpaca REST API with OPG support detection.
All operations are paper-only, never touches live account.
"""

import os
import json
import time
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import urllib.request
import urllib.error
import urllib.parse
from .market_calendar import NYSE_TZ

logger = logging.getLogger(__name__)


class AlpacaAdapter:
    """Thin wrapper over Alpaca paper trading REST API."""
    
    def __init__(self, api_key: str, api_secret: str, base_url: str, account_id_alias: str = "default") -> None:
        """Initialize Alpaca adapter.
        
        Args:
            api_key: Alpaca API key
            api_secret: Alpaca API secret
            base_url: Paper trading base URL (must be paper endpoint)
            account_id_alias: Account identifier for multi-account support
        """
        # Validate paper endpoint
        if "paper" not in base_url:
            raise ValueError(f"Safety check: base_url must be paper endpoint, got: {base_url}")
        
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url.rstrip('/')
        self.account_id_alias = account_id_alias
        
        # Headers for all requests
        self.headers = {
            'APCA-API-KEY-ID': api_key,
            'APCA-API-SECRET-KEY': api_secret,
            'Content-Type': 'application/json'
        }
        
        # Feature detection cache
        self._supports_opg_bracket = None
        
        logger.info(f"Initialized Alpaca adapter for {account_id_alias} at {base_url}")
    
    def _request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Dict:
        """Make HTTP request to Alpaca API.
        
        Args:
            method: HTTP method (GET, POST, DELETE, etc.)
            endpoint: API endpoint path
            data: Optional request body
        
        Returns:
            Response data as dict
        """
        url = f"{self.base_url}{endpoint}"
        
        # Prepare request
        req_data = json.dumps(data).encode('utf-8') if data else None
        req = urllib.request.Request(
            url,
            data=req_data,
            headers=self.headers,
            method=method
        )
        
        try:
            response = urllib.request.urlopen(req)
            response_text = response.read().decode('utf-8')
            return json.loads(response_text) if response_text else {}
            
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8') if e.fp else ""
            logger.error(f"Alpaca API error {e.code}: {error_body}")
            
            # Parse error for better handling
            try:
                error_data = json.loads(error_body)
                raise ValueError(f"Alpaca API error: {error_data.get('message', error_body)}")
            except json.JSONDecodeError:
                raise ValueError(f"Alpaca API error {e.code}: {error_body}")
                
        except Exception as e:
            logger.error(f"Request failed: {e}")
            raise
    
    def get_account(self) -> Dict:
        """Get account information including equity and buying power."""
        return self._request('GET', '/v2/account')
    
    def get_clock(self) -> Dict:
        """Get current market clock status."""
        return self._request('GET', '/v2/clock')
    
    def get_positions(self) -> List[Dict]:
        """Get all open positions."""
        return self._request('GET', '/v2/positions')
    
    def get_position(self, symbol: str) -> Optional[Dict]:
        """Get position for specific symbol.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Position data or None if not found
        """
        try:
            return self._request('GET', f'/v2/positions/{symbol}')
        except ValueError as e:
            if "not found" in str(e).lower():
                return None
            raise
    
    def list_orders(self, status: str = "open") -> List[Dict]:
        """List orders with given status.
        
        Args:
            status: Order status filter (open, closed, all)
            
        Returns:
            List of orders
        """
        params = {'status': status, 'limit': 100}  # Max allowed by Alpaca
        query = urllib.parse.urlencode(params)
        return self._request('GET', f'/v2/orders?{query}')
    
    def get_order(self, order_id: str) -> Dict:
        """Get specific order by ID."""
        return self._request('GET', f'/v2/orders/{order_id}')
    
    def get_order_by_client_id(self, client_order_id: str) -> Optional[Dict]:
        """Get order by client order ID.
        
        Args:
            client_order_id: Client-specified order ID
            
        Returns:
            Order data or None if not found
        """
        params = {'client_order_id': client_order_id}
        query = urllib.parse.urlencode(params)
        orders = self._request('GET', f'/v2/orders?{query}')
        
        if orders and len(orders) > 0:
            return orders[0]
        return None
    
    def cancel_open_orders(self, symbol: Optional[str] = None) -> int:
        """Cancel open orders, optionally filtered by symbol.
        
        Args:
            symbol: Optional symbol to filter cancellations
            
        Returns:
            Number of orders cancelled
        """
        open_orders = self.list_orders(status="open")
        cancelled = 0
        
        for order in open_orders:
            if symbol and order.get('symbol') != symbol:
                continue
            try:
                self._request('DELETE', f"/v2/orders/{order['id']}")
                cancelled += 1
                logger.info(f"Cancelled order {order['id']} for {order.get('symbol')}")
            except Exception as e:
                logger.error(f"Failed to cancel order {order['id']}: {e}")
        
        return cancelled
    
    def get_activities(self, start_iso: str, end_iso: str) -> List[Dict]:
        """Get account activities (fills) for date range.
        
        Args:
            start_iso: Start date in ISO format
            end_iso: End date in ISO format
            
        Returns:
            List of activities
        """
        params = {
            'activity_types': 'FILL',
            'after': start_iso,
            'until': end_iso,
            'page_size': 100  # Max allowed by Alpaca
        }
        query = urllib.parse.urlencode(params)
        return self._request('GET', f'/v2/account/activities?{query}')
    
    def supports_opg_bracket(self) -> bool:
        """Check if broker supports OPG orders with brackets.
        
        Returns:
            True if OPG+bracket supported, False otherwise
        """
        if self._supports_opg_bracket is not None:
            return self._supports_opg_bracket
        
        # Alpaca generally doesn't support brackets with OPG
        # This is a known limitation - OPG orders can't have attached stops
        self._supports_opg_bracket = False
        logger.info("OPG+bracket detection: Not supported on Alpaca")
        
        return self._supports_opg_bracket
    
    def submit_bracket_order(
        self,
        symbol: str,
        qty: int,
        side: str,
        entry_type: str,
        time_in_force: str,
        limit_price: Optional[float],
        stop_loss: float,
        take_profit: float,
        client_order_id: str,
        open_only: bool = False
    ) -> Dict:
        """Submit a bracket order with entry, stop loss, and take profit.
        
        Args:
            symbol: Stock symbol
            qty: Number of shares
            side: "buy" or "sell"
            entry_type: "market" or "limit"
            time_in_force: "day", "opg", "gtc"
            limit_price: Limit price for entry (if entry_type="limit")
            stop_loss: Stop loss price
            take_profit: Take profit price
            client_order_id: Unique client order ID for idempotency
            open_only: If True, use OPG time in force
            
        Returns:
            Order response data
        """
        # Check for existing order with same client_order_id
        existing = self.get_order_by_client_id(client_order_id)
        if existing:
            logger.info(f"Order already exists with client_order_id: {client_order_id}")
            return existing
        
        # Build order request
        order_data = {
            'symbol': symbol,
            'qty': str(qty),
            'side': side,
            'type': entry_type,
            'time_in_force': 'opg' if open_only else time_in_force,
            'client_order_id': client_order_id
        }
        
        # Add limit price if needed
        if entry_type == 'limit' and limit_price:
            order_data['limit_price'] = str(limit_price)
        
        # Add bracket legs if not OPG (OPG doesn't support brackets)
        if not open_only and time_in_force != 'opg':
            order_data['order_class'] = 'bracket'
            order_data['stop_loss'] = {'stop_price': str(stop_loss)}
            order_data['take_profit'] = {'limit_price': str(take_profit)}
        
        logger.info(f"Submitting {side} order for {qty} {symbol} @ {entry_type} "
                   f"{'(OPG)' if open_only else f'with bracket [{stop_loss:.2f}, {take_profit:.2f}]'}")
        
        return self._request('POST', '/v2/orders', order_data)
    
    def submit_opg_entry(
        self,
        symbol: str,
        qty: int,
        limit_price: float,
        client_order_id: str
    ) -> Dict:
        """Submit an OPG (at-the-open) limit order.
        
        Args:
            symbol: Stock symbol
            qty: Number of shares
            limit_price: Limit price with buffer
            client_order_id: Unique client order ID
            
        Returns:
            Order response data
        """
        # Check for existing order
        existing = self.get_order_by_client_id(client_order_id)
        if existing:
            logger.info(f"OPG order already exists: {client_order_id}")
            return existing
        
        order_data = {
            'symbol': symbol,
            'qty': str(qty),
            'side': 'buy',
            'type': 'limit',
            'time_in_force': 'opg',
            'limit_price': str(limit_price),
            'client_order_id': client_order_id
        }
        
        logger.info(f"Submitting OPG order for {qty} {symbol} @ {limit_price:.2f}")
        return self._request('POST', '/v2/orders', order_data)
    
    def submit_oco_stops(
        self,
        symbol: str,
        qty: int,
        stop_price: float,
        target_price: float,
        parent_id: str
    ) -> Dict:
        """Submit OCO (one-cancels-other) stop and target orders.
        
        Used after OPG fill when brackets aren't supported with OPG.
        
        Args:
            symbol: Stock symbol
            qty: Number of shares (should match filled qty)
            stop_price: Stop loss price
            target_price: Take profit price
            parent_id: Parent order ID for reference
            
        Returns:
            OCO order response
        """
        # Create OCO order
        order_data = {
            'symbol': symbol,
            'qty': str(qty),
            'side': 'sell',
            'type': 'limit',
            'time_in_force': 'gtc',
            'order_class': 'oco',
            'limit_price': str(target_price),
            'stop_loss': {
                'stop_price': str(stop_price),
                'limit_price': str(stop_price * 0.995)  # Small buffer for stop limit
            },
            'client_order_id': f"{parent_id}_oco"
        }
        
        logger.info(f"Submitting OCO stops for {qty} {symbol}: "
                   f"stop={stop_price:.2f}, target={target_price:.2f}")
        
        return self._request('POST', '/v2/orders', order_data)
    
    def get_latest_quote(self, symbol: str) -> Dict:
        """Get latest quote for a symbol.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Quote data with bid/ask/last
        """
        endpoint = f"/v2/stocks/{symbol}/quotes/latest"
        return self._request('GET', endpoint)
    
    def get_bars(self, symbol: str, start: str, end: str, timeframe: str = "1Day") -> List[Dict]:
        """Get historical bars for a symbol.
        
        Args:
            symbol: Stock symbol
            start: Start date (YYYY-MM-DD)
            end: End date (YYYY-MM-DD)
            timeframe: Bar timeframe
            
        Returns:
            List of OHLCV bars
        """
        # Use data API endpoint for market data
        data_url = "https://data.alpaca.markets"
        params = {
            'start': start,
            'end': end,
            'timeframe': timeframe,
            'feed': 'iex',
            'adjustment': 'all'
        }
        query = urllib.parse.urlencode(params)
        
        # Make request to data API
        url = f"{data_url}/v2/stocks/{symbol}/bars?{query}"
        req = urllib.request.Request(url, headers=self.headers)
        
        try:
            response = urllib.request.urlopen(req)
            response_text = response.read().decode('utf-8')
            data = json.loads(response_text) if response_text else {}
            return data.get('bars', [])
        except Exception as e:
            logger.error(f"Error fetching bars for {symbol}: {e}")
            return []
    
    def check_order_fill(self, order_id: str) -> Tuple[bool, Optional[float], Optional[int]]:
        """Check if an order has been filled.
        
        Args:
            order_id: Order ID to check
            
        Returns:
            Tuple of (is_filled, avg_price, filled_qty)
        """
        try:
            order = self.get_order(order_id)
            
            if order.get('status') == 'filled':
                return True, float(order.get('filled_avg_price', 0)), int(order.get('filled_qty', 0))
            elif order.get('status') == 'partially_filled':
                return False, float(order.get('filled_avg_price', 0)), int(order.get('filled_qty', 0))
            else:
                return False, None, None
                
        except Exception as e:
            logger.error(f"Error checking order fill: {e}")
            return False, None, None