#!/usr/bin/env python3
"""SwingTrading Server with Scoring v2 Implementation."""

import http.server
import socketserver
import json
import uuid
import threading
import time
import os
import sys
import urllib.request
import urllib.error
from urllib.parse import urlparse
from datetime import datetime, timedelta, date

# Import scoring v2 modules
from scoring_v2 import calculate_score_v2, MODEL_VERSION
from scoring_v2.cache import DataCache
from scoring_v2.telemetry import get_telemetry, reset_telemetry
from scoring_v2.scoring import format_score_output

# Import paper trading modules
from cli.paper import (
    cmd_scan as paper_scan,
    cmd_place as paper_place,
    cmd_positions as paper_positions,
    cmd_report as paper_report,
    load_config as paper_load_config,
    get_adapter as paper_get_adapter,
)

# Load Alpaca credentials from .env
env_file = '.env'
if os.path.exists(env_file):
    with open(env_file) as f:
        for line in f:
            if '=' in line and not line.startswith('#'):
                key, value = line.strip().split('=', 1)
                os.environ[key] = value

ALPACA_KEY = os.environ.get('ALPACA_API_KEY')
ALPACA_SECRET = os.environ.get('ALPACA_API_SECRET')

# Initialize cache
data_cache = DataCache()

def get_historical_data_with_cache(symbol, days=550):
    """Get historical OHLCV data from Alpaca with caching.
    
    Args:
        symbol: Stock symbol
        days: Number of days to fetch (need 366+ for v2)
    
    Returns:
        List of bars or None
    """
    telemetry = get_telemetry()
    end_date = datetime.now().strftime('%Y-%m-%d')
    
    # Check cache first
    cached_data = data_cache.get(symbol, end_date, days)
    if cached_data:
        telemetry.track_cache_hit(symbol, True)
        return cached_data
    
    telemetry.track_cache_hit(symbol, False)
    
    # Fetch from API
    try:
        start_time = time.time()
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        
        url = f"https://data.alpaca.markets/v2/stocks/{symbol}/bars?start={start_date}&end={end_date}&timeframe=1Day&feed=iex&adjustment=all"
        
        print(f"Fetching {days} days for {symbol} (v2 requires 366+)", file=sys.stderr)
        
        if not ALPACA_KEY or not ALPACA_SECRET:
            print(f"ERROR: Missing Alpaca credentials for {symbol}", file=sys.stderr)
            return None
            
        req = urllib.request.Request(url, headers={
            'APCA-API-KEY-ID': ALPACA_KEY,
            'APCA-API-SECRET-KEY': ALPACA_SECRET
        })
        response = urllib.request.urlopen(req)
        response_text = response.read()
        data = json.loads(response_text)
        
        duration_ms = (time.time() - start_time) * 1000
        telemetry.track_api_call(symbol, duration_ms)
        
        if 'bars' in data and data['bars']:
            bar_count = len(data['bars'])
            print(f"Got {bar_count} bars for {symbol}", file=sys.stderr)
            
            # Cache the data
            data_cache.set(symbol, end_date, days, data['bars'])
            
            return data['bars']
        else:
            print(f"No bars data in response for {symbol}", file=sys.stderr)
            return None
            
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8') if e.fp else ""
        print(f"ERROR fetching data for {symbol}: HTTP {e.code} - {error_body}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"ERROR fetching data for {symbol}: {e}", file=sys.stderr)
        return None

def determine_action_v2(score, rsi, preset='balanced'):
    """Determine trading action based on v2 score and preset.
    
    Args:
        score: v2 score (0-100) or None if gates failed
        rsi: RSI value
        preset: Trading preset
    
    Returns:
        Action string (BUY/WATCH/AVOID)
    """
    if score is None:
        return 'AVOID'
    
    # Preset thresholds
    presets = {
        "conservative": {"min_score": 60, "watch_score": 45},
        "balanced": {"min_score": 45, "watch_score": 30},
        "aggressive": {"min_score": 30, "watch_score": 20}
    }
    
    settings = presets.get(preset, presets['balanced'])
    
    # Never buy extremely overbought
    if rsi > 75:
        return 'AVOID'
    
    # Apply thresholds
    if score >= settings['min_score']:
        return 'BUY'
    elif score >= settings['watch_score']:
        return 'WATCH'
    else:
        return 'AVOID'

# Store active scans
active_scans = {}
# Store active paper trading scans
active_paper_scans = {}

# v2 Knowledge base
KNOWLEDGE = {
    "what_is_swing": {
        "title": "What is Swing Trading?",
        "content": """Swing trading captures 2-10 day price movements:
• Buy pullbacks in uptrends
• Target 5-8% gains per trade  
• Use ATR-based stops (1.5x ATR)
• Hold maximum 10 trading days
• Risk 2% of portfolio per trade

The v2 system identifies high-probability setups using percentile rankings."""
    },
    "understanding_scores": {
        "title": "Understanding v2 Scores",
        "content": """Scores rank setups using historical percentiles (0-100):

Score 60-100: STRONG BUY
• Top 40th percentile historically
• All gates passed
• Use 8-10% position size

Score 40-60: MODERATE BUY
• Above average setup
• Standard 5-7% position

Score 20-40: WATCH
• Below average, monitor
• Small 3-5% position

NULL/AVOID:
• Failed setup gates
• Insufficient history
• No position"""
    },
    "scoring_v2": {
        "title": "How v2 Scoring Works",
        "content": """The v2 score (0-100) measures how good a swing trade setup is:

HOW IT'S CALCULATED:
1. We track 4 key factors for each stock:
   • Pullback: How far stock pulled back from recent high
   • Trend: How strong the uptrend is (vs 50-day average)
   • RSI Room: How much room to rise before overbought
   • Volume: Today's volume vs 10-day average

2. Each factor gets a percentile score (0-100):
   • Compares today to the last 252 trading days
   • 90th percentile = better than 90% of days
   • 10th percentile = worse than 90% of days

3. Final score = average of all 4 percentiles
   • Each component has equal 25% weight
   • Higher score = better historical setup

SETUP GATES (must pass all):
• Volatility: ATR must be 0.5%-8% of price
• Trend: Stock must be above 50-day moving average  
• Pullback: Must be 5%-20% below 20-day high

If any gate fails, score = N/A (avoid trading)

WHAT SCORES MEAN:
• 60-100: Exceptional setup (top 40%)
• 40-60: Good setup (above average)
• 20-40: Weak setup (below average)
• 0-20: Poor setup (bottom 20%)
• N/A: Failed gates (don't trade)"""
    },
    "presets": {
        "conservative": {"min_score": 60, "position_size": "3-5%"},
        "balanced": {"min_score": 45, "position_size": "5-8%"},
        "aggressive": {"min_score": 30, "position_size": "8-12%"}
    },
    "rsi_explained": {
        "title": "Understanding RSI",
        "content": """RSI (Relative Strength Index) measures momentum:

RSI RANGES:
• Under 30 = Oversold (potential bounce)
• 30-40 = Getting oversold
• 40-60 = Neutral zone
• 60-70 = Getting overbought
• Over 70 = Overbought (potential pullback)

HOW V2 USES RSI:
• We calculate "RSI Room" = 70 - Current RSI
• More room = stock can rise before hitting overbought
• Example: RSI 40 = 30 points of room (good)
• Example: RSI 65 = 5 points of room (limited)

This becomes one of the 4 components in your score."""
    },
    "how_to_trade": {
        "title": "How to Execute a Trade",
        "content": """Step-by-step trading process:

1. SCAN & SELECT
   • Run scanner with your preset
   • Look for BUY signals with good scores
   • Check the entry price shown

2. PLACE YOUR ORDER
   • Use a "Buy Stop" order at entry price
   • This triggers when price moves up
   • Avoids catching falling knives

3. SET RISK MANAGEMENT
   • Immediately set stop loss (shown in table)
   • Place limit sell at Target 1
   • Never trade without stops

4. MANAGE THE POSITION
   • When Target 1 hits, sell half
   • Move stop to breakeven
   • Let rest ride to Target 2
   • Exit if stop hit or 10 days pass

POSITION SIZING:
• Conservative: 3-5% of portfolio
• Balanced: 5-8% of portfolio
• Aggressive: 8-12% of portfolio"""
    },
    "risk_management": {
        "title": "Risk Management Rules",
        "content": """Critical rules to protect your capital:

GOLDEN RULES:
1. Always use stop losses (no exceptions)
2. Never risk more than 2% on one trade
3. Maximum 3-5 positions at once
4. Keep 30-50% cash for opportunities
5. Stop trading if down 5% in a month

POSITION SIZING EXAMPLE:
• Account: $10,000
• Position size: $800 (8%)
• Stop loss: 3% below entry
• Maximum risk: $24 (0.24% of account)

V2 RISK FEATURES:
• ATR-based stops (adapts to volatility)
• 1.5x ATR stop loss
• 2-3x ATR profit targets
• Gates prevent bad setups
• Percentiles show historical context

Remember: Small losses, big wins = success"""
    },
    "scoring_system": {
        "title": "Scoring System Details",
        "content": """Deep dive into v2 scoring mechanics:

PERCENTILE RANKING:
• Each stock compared to its own history
• 252 trading days = 1 year baseline
• Removes market/sector bias
• Self-adjusting to volatility changes

THE 4 COMPONENTS:

1. PULLBACK (25% weight)
   • Measures: Distance from 20-day high
   • Good: 5-15% pullback
   • Bad: <5% (no discount) or >20% (falling knife)

2. TREND (25% weight)
   • Measures: Position vs 50-day MA
   • Good: 5-15% above MA
   • Bad: Below MA or too extended

3. RSI PERCENTILE (25% weight)
   • Measures: Symbol-relative RSI percentile
   • Good: RSI in 30-70 percentile range
   • Bad: Extreme percentiles (overbought/oversold)

4. DOLLAR VOLUME (25% weight)
   • Measures: Today's dollar volume vs 10-day average
   • Filters: Minimum $20M daily liquidity
   • Good: 1.5-3x average
   • Bad: Below average (no interest)

GATES PREVENT DISASTERS:
• Too volatile or illiquid = blocked
• Downtrend = blocked
• No pullback or too much = blocked"""
    }
}

class WorkingHandlerV2(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory="web", **kwargs)
    
    def do_GET(self):
        parsed = urlparse(self.path)
        
        if parsed.path == '/api/config':
            self.send_json({
                'status': 'ok',
                'alpaca_connected': bool(ALPACA_KEY),
                'model_version': MODEL_VERSION,
                'cache_hit_rate': data_cache.get_hit_rate()
            })
        
        elif parsed.path == '/api/knowledge':
            self.send_json(KNOWLEDGE)
        
        elif parsed.path.startswith('/api/scan/'):
            # Handle both /api/scan/{run_id}/status and /api/scan/{run_id}
            path_parts = parsed.path.split('/')
            if len(path_parts) >= 4:
                run_id = path_parts[3]
                if run_id in active_scans:
                    scan_data = active_scans[run_id].copy()
                    # Format for enhanced UI compatibility
                    if scan_data.get('state') == 'done':
                        scan_data['state'] = 'complete'
                        # Ensure candidates are properly formatted
                        if 'results' in scan_data:
                            scan_data['candidates'] = scan_data['results']
                    self.send_json(scan_data)
                else:
                    self.send_error(404)
            else:
                self.send_error(404)
        
        elif parsed.path.startswith('/api/scan/') and '/results' in parsed.path:
            run_id = parsed.path.split('/')[3]
            if run_id in active_scans and active_scans[run_id]['state'] == 'done':
                self.send_json({'results': active_scans[run_id]['results']})
            else:
                self.send_error(404)
        
        elif parsed.path == '/api/telemetry':
            self.send_json(get_telemetry().get_summary())
            
        elif parsed.path == '/api/paper/positions':
            # Get current paper trading positions
            try:
                result = paper_positions('config.yaml')
                if result:
                    self.send_json({'positions': result.get('positions', [])})
                else:
                    self.send_json({'positions': []})
            except Exception as e:
                self.send_json({'error': str(e)})
                
        elif parsed.path.startswith('/api/paper/scan/') and '/status' in parsed.path:
            # Get paper scan status
            run_id = parsed.path.split('/')[4]
            if run_id in active_paper_scans:
                self.send_json(active_paper_scans[run_id])
            else:
                self.send_error(404)
        
        elif parsed.path.startswith('/api/analyze/'):
            # Detailed stock analysis for trust building
            symbol = parsed.path.split('/')[-1].upper()

            try:
                # Get historical data
                bars = get_historical_data_with_cache(symbol, days=550)

                if bars and len(bars) >= 366:
                    # Calculate detailed analysis
                    score, gate_reason, components = calculate_score_v2(bars, symbol)
                    breakdown = get_score_breakdown(bars, symbol, score, components)
                    confidence = calculate_confidence_level(score, components)
                    risk_assessment = get_risk_assessment(bars, symbol)
                    trading_levels = calculate_trading_levels(bars, symbol, score, components)

                    # Get additional insights
                    insights = get_stock_insights(bars, symbol, score)

                    analysis = {
                        'symbol': symbol,
                        'score': score,
                        'gate_reason': gate_reason,
                        'breakdown': breakdown,
                        'confidence': confidence,
                        'risk_assessment': risk_assessment,
                        'trading_levels': trading_levels,
                        'insights': insights,
                        'timestamp': time.time()
                    }

                    self.send_json(analysis)
                else:
                    self.send_json({'error': f'Insufficient data for {symbol}'})

            except Exception as e:
                self.send_json({'error': f'Analysis failed for {symbol}: {str(e)}'})

        else:
            super().do_GET()
    
    def do_POST(self):
        if self.path == '/api/scan':
            # Parse request body
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            request_data = json.loads(post_data)
            
            run_id = str(uuid.uuid4())
            active_scans[run_id] = {
                'run_id': run_id,
                'state': 'running',
                'progress': {'done': 0, 'total': 10},
                'results': [],
                'universe': request_data.get('universe', 'sp500'),
                'custom_tickers': request_data.get('tickers', None),
                'preset': request_data.get('preset', 'balanced'),
                'model_version': MODEL_VERSION
            }
            
            # Reset telemetry for new scan
            reset_telemetry()
            
            threading.Thread(target=self.run_scan_v2, args=(run_id,)).start()
            self.send_json({'run_id': run_id, 'model_version': MODEL_VERSION})
            
        elif self.path == '/api/paper/scan':
            # Run paper trading scan
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            
            run_id = str(uuid.uuid4())
            active_paper_scans[run_id] = {
                'state': 'running',
                'progress': {'done': 0, 'total': 1},
                'results': None
            }
            
            # Run paper scan in background thread
            threading.Thread(target=self.run_paper_scan, args=(run_id,)).start()
            self.send_json({'run_id': run_id})
            
        elif self.path == '/api/paper/place':
            # Place paper trading orders
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            request_data = json.loads(post_data)
            
            try:
                # Get the run_id from request if provided
                run_id = request_data.get('run_id')
                
                # Call paper place command
                result = paper_place('config.yaml', run_id, dry_run=False)
                
                # Return placed orders information
                if result and 'orders' in result:
                    self.send_json({'orders': result['orders'], 'count': len(result['orders'])})
                else:
                    self.send_json({'orders': [], 'count': 0})
                    
            except Exception as e:
                self.send_json({'error': str(e)})
                
        elif self.path == '/api/paper/report':
            # Generate EOD report
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            
            try:
                # Call paper report command - it now returns a dict
                result = paper_report('config.yaml', None)
                
                if result and 'metrics' in result:
                    # Extract key metrics for display
                    metrics = result.get('metrics', {})
                    summary = {
                        'date': str(metrics.get('date', date.today())),
                        'total_pl': metrics.get('daily_pl', 0),
                        'open_positions': metrics.get('position_count', 0),
                        'closed_today': metrics.get('exits', 0),
                        'account_value': metrics.get('ending_equity', 0),
                        'starting_equity': metrics.get('starting_equity', 0),
                        'realized_pl': metrics.get('realized_pl', 0)
                    }
                    self.send_json({
                        'summary': summary,
                        'report_path': result.get('markdown', ''),
                        'metrics': metrics
                    })
                else:
                    self.send_json({'error': 'Report generation failed - no metrics returned'})
                    
            except Exception as e:
                print(f"Error generating EOD report: {e}", file=sys.stderr)
                self.send_json({'error': str(e)})
                
        elif self.path == '/api/paper/place-custom':
            # Place custom paper orders sent from the UI
            content_length = int(self.headers.get('Content-Length', 0) or 0)
            post_data = self.rfile.read(content_length) if content_length > 0 else b'{}'
            
            try:
                request_data = json.loads(post_data)
            except Exception:
                self.send_json({'error': 'Invalid JSON body'})
                return
            
            orders = request_data.get('orders', [])
            if not isinstance(orders, list) or not orders:
                self.send_json({'error': 'No orders provided'})
                return
            
            try:
                # Reuse CLI helpers to get configured adapter
                config = paper_load_config('config.yaml')
                adapter = paper_get_adapter(config)
            except Exception as e:
                self.send_json({'error': f'Broker setup failed: {e}'})
                return
            
            placed = []
            errors = []
            for o in orders:
                try:
                    symbol = o.get('symbol')
                    side = (o.get('side') or 'buy').lower()
                    qty = int(o.get('qty') or 0)
                    entry_price = o.get('entry_price', None)
                    stop_loss = o.get('stop_loss', None)
                    take_profit = o.get('take_profit', None)
                    
                    if not symbol or qty <= 0 or stop_loss is None or take_profit is None:
                        raise ValueError('Missing required fields (symbol, qty, stop_loss, take_profit)')
                    
                    # Determine entry type and limit
                    entry_type = 'market'
                    limit_price = None
                    if isinstance(entry_price, (int, float)) and entry_price > 0:
                        entry_type = 'limit'
                        limit_price = float(entry_price)
                    elif isinstance(entry_price, str) and entry_price.lower() != 'market':
                        # If a string other than 'market' provided, try to parse
                        try:
                            val = float(entry_price)
                            if val > 0:
                                entry_type = 'limit'
                                limit_price = val
                        except Exception:
                            pass
                    
                    client_order_id = f"manual:{datetime.now().strftime('%Y%m%d%H%M%S')}:{symbol}:{uuid.uuid4().hex[:6]}"
                    
                    # Submit as day bracket order
                    resp = adapter.submit_bracket_order(
                        symbol=symbol,
                        qty=qty,
                        side=side,
                        entry_type=entry_type,
                        time_in_force='day',
                        limit_price=limit_price,
                        stop_loss=float(stop_loss),
                        take_profit=float(take_profit),
                        client_order_id=client_order_id,
                        open_only=False
                    )
                    placed.append({
                        'symbol': symbol,
                        'qty': qty,
                        'side': side,
                        'entry_type': entry_type,
                        'limit_price': limit_price,
                        'stop_loss': float(stop_loss),
                        'take_profit': float(take_profit),
                        'order_id': resp.get('id'),
                        'client_order_id': client_order_id
                    })
                except Exception as e:
                    errors.append({'symbol': o.get('symbol'), 'error': str(e)})
            
            self.send_json({'placed': placed, 'errors': errors})

        else:
            self.send_error(404)
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', '*')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.end_headers()
    
    def send_json(self, data):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
    
    def run_scan_v2(self, run_id):
        """Run scan with v2 scoring system."""
        telemetry = get_telemetry()
        
        print(f"Starting v2 scan with model {MODEL_VERSION}", file=sys.stderr)
        print(f"Cache initialized, current hit rate: {data_cache.get_hit_rate():.1%}", file=sys.stderr)
        
        # Determine which tickers to scan
        if active_scans[run_id].get('custom_tickers'):
            all_tickers = active_scans[run_id]['custom_tickers']
        else:
            # Load S&P 500 tickers
            try:
                with open('sp500_tickers.txt', 'r') as f:
                    all_tickers = [line.strip() for line in f if line.strip()]
            except:
                # Fallback to sample list
                all_tickers = ['SPY', 'QQQ', 'AAPL', 'MSFT', 'GOOGL', 'AMZN', 
                              'NVDA', 'META', 'TSLA', 'JPM', 'V', 'JNJ', 'WMT', 
                              'PG', 'MA', 'UNH', 'HD', 'DIS', 'BAC', 'XOM']
        
        # Process each ticker with v2 scoring
        stocks_with_scores = []
        active_scans[run_id]['progress']['total'] = len(all_tickers)
        
        for i, ticker in enumerate(all_tickers):
            start_time = time.time()
            
            try:
                # Get historical data (need 366+ bars for v2)
                bars = get_historical_data_with_cache(ticker, days=550)
                
                if bars and len(bars) >= 366:
                    # Calculate v2 score
                    score, gate_reason, components = calculate_score_v2(bars, ticker)
                    
                    # Format output
                    output = format_score_output(score, gate_reason, components)
                    
                    # Determine action
                    preset = active_scans[run_id].get('preset', 'balanced')
                    rsi = output.get('rsi14', 50)
                    action = determine_action_v2(score, rsi, preset)
                    
                    # Add detailed breakdown for trust building
                    breakdown = get_score_breakdown(bars, ticker, score, components)

                    # Debug confidence calculation
                    confidence = calculate_confidence_level(score, components)
                    print(f"DEBUG: {ticker} - Score: {score}, Components: {bool(components)}, Confidence: {confidence}")

                    stocks_with_scores.append({
                        'symbol': ticker,
                        'score': score,  # None if gates failed
                        'confidence': confidence,  # Add confidence to scan results
                        'gate_reason': gate_reason,
                        'action': action,
                        'output': output,
                        'breakdown': breakdown,
                        'confidence': confidence,
                        'risk_assessment': get_risk_assessment(bars, ticker)
                    })
                    
                elif bars:
                    # Insufficient history
                    telemetry.track_skip(ticker, "insufficient_history")
                    stocks_with_scores.append({
                        'symbol': ticker,
                        'score': None,
                        'gate_reason': 'insufficient_history',
                        'action': 'AVOID',
                        'output': {
                            'bars_available': len(bars),
                            'bars_required': 366
                        }
                    })
                else:
                    # No data available
                    telemetry.track_skip(ticker, "no_data")
                    stocks_with_scores.append({
                        'symbol': ticker,
                        'score': None,
                        'gate_reason': 'no_data',
                        'action': 'AVOID',
                        'output': {}
                    })
                    
            except Exception as e:
                print(f"Error processing {ticker}: {e}", file=sys.stderr)
                telemetry.track_skip(ticker, "error")
                stocks_with_scores.append({
                    'symbol': ticker,
                    'score': None,
                    'gate_reason': 'error',
                    'action': 'AVOID',
                    'output': {'error': str(e)}
                })
            
            # Track compute time
            compute_ms = (time.time() - start_time) * 1000
            telemetry.track_compute_time(ticker, compute_ms)
            
            # Update progress
            active_scans[run_id]['progress']['done'] = i + 1
            
            # Small delay to avoid rate limiting
            if i % 10 == 9:
                time.sleep(0.5)
        
        # Sort by score (None values last)
        stocks_with_scores.sort(
            key=lambda x: (x['score'] is None, -x['score'] if x['score'] else 0)
        )
        
        print(f"\nScan complete. {telemetry.log_summary()}", file=sys.stderr)
        
        # Format results for UI
        results = []
        for stock_data in stocks_with_scores:
            output = stock_data['output']
            score = stock_data['score']
            
            # Calculate entry and targets based on action using ATR
            if 'close' in output:
                close = output['close']
                action = stock_data['action']
                atr = output.get('atr_value', 0)
                
                # Use ATR-based targets if available, fallback to percentage
                if action == 'BUY' and atr > 0:
                    entry = close * 1.002  # Slight above market
                    stop = close - (1.5 * atr)  # 1.5x ATR stop
                    target1 = close + (2.0 * atr)  # 2x ATR target
                    target2 = close + (3.0 * atr)  # 3x ATR target
                elif action == 'BUY':
                    # Fallback to percentage-based
                    entry = close * 1.002
                    stop = close * 0.97
                    target1 = close * 1.05
                    target2 = close * 1.08
                elif action == 'WATCH' and atr > 0:
                    entry = close * 0.99
                    stop = entry - (1.5 * atr)
                    target1 = entry + (2.0 * atr)
                    target2 = entry + (3.0 * atr)
                elif action == 'WATCH':
                    # Fallback to percentage-based
                    entry = close * 0.99
                    stop = entry * 0.97
                    target1 = entry * 1.03
                    target2 = entry * 1.05
                else:
                    entry = stop = target1 = target2 = None
            else:
                close = entry = stop = target1 = target2 = None
            
            result_data = {
                'symbol': stock_data['symbol'],
                'close': round(close, 2) if close else None,
                'score': round(score, 1) if score is not None else None,  # Explicit None
                'confidence': stock_data.get('confidence', 'Unknown'),  # Add confidence from scan data
                'rsi14': round(output.get('rsi14', 50), 1),
                'action': stock_data['action'],
                'entry_price': round(entry, 2) if entry else None,
                'stop_loss': round(stop, 2) if stop else None,
                'target_1': round(target1, 2) if target1 else None,
                'target_2': round(target2, 2) if target2 else None,
                'volume': output.get('volume', 0),
                'model_version': MODEL_VERSION
            }
            
            # Always add score components for display (aligned with P0 keys)
            result_data['score_components'] = {
                'pullback': round(output.get('pullback_pct', 0), 1) if 'pullback_pct' in output else None,
                'trend': round(output.get('trend_pct', 0), 1) if 'trend_pct' in output else None,
                'rsi': round(output.get('rsi_pct', 0), 1) if 'rsi_pct' in output else None,
                'dollar_volume': round(output.get('dollar_volume_uplift_pct', 0), 1) if 'dollar_volume_uplift_pct' in output else None,
                'gates_passed': stock_data['gate_reason'] is None
            }
            
            # Add gate failure reason if applicable
            if stock_data['gate_reason']:
                result_data['gate_failed'] = stock_data['gate_reason']
                # Provide human-readable reason
                reasons = {
                    'insufficient_history': 'Not enough data (needs 250+ days)',
                    'gate_atr_ratio': 'Volatility outside 0.5%-8% range',
                    'gate_trend_filter': 'Below 50-day moving average',
                    'gate_pullback_band': 'Pullback outside 5%-20% range'
                }
                result_data['gate_message'] = reasons.get(stock_data['gate_reason'], stock_data['gate_reason'])
            
            results.append(result_data)
        
        # Store final results with telemetry
        active_scans[run_id]['state'] = 'done'
        active_scans[run_id]['results'] = results
        telemetry_summary = get_telemetry().get_summary()
        active_scans[run_id]['telemetry'] = telemetry_summary

        # Print detailed skip reasons for debugging
        print(f"\n=== DETAILED SKIP ANALYSIS ===", file=sys.stderr)
        skip_reasons = telemetry_summary.get('skipped_reasons', {})
        for reason, count in skip_reasons.items():
            print(f"{reason}: {count} stocks", file=sys.stderr)
        print(f"Total candidates found: {len(results)}", file=sys.stderr)
    
    def run_paper_scan(self, run_id):
        """Run paper trading scan in background."""
        try:
            print(f"Starting paper trading scan {run_id}", file=sys.stderr)
            
            # Update progress to show scan is starting
            active_paper_scans[run_id]['progress'] = {'done': 0, 'total': 100}
            active_paper_scans[run_id]['state'] = 'running'
            active_paper_scans[run_id]['status_message'] = 'Initializing scan...'
            
            # Step 1: Initialize scan (simulate progress)
            for i in range(1, 20):
                active_paper_scans[run_id]['progress']['done'] = i
                time.sleep(0.05)
            
            active_paper_scans[run_id]['status_message'] = 'Scanning S&P 500 stocks...'
            active_paper_scans[run_id]['progress']['done'] = 20
            
            # Run the paper scan command
            result = paper_scan('config.yaml', None, 'state', False)
            
            # Step 2: Processing results
            active_paper_scans[run_id]['progress']['done'] = 90
            active_paper_scans[run_id]['status_message'] = 'Processing results...'
            
            # Update scan state with results
            if result and 'intents' in result:
                # Convert intents to displayable format
                display_results = []
                for intent in result['intents']:
                    # Handle bracket structure from new format
                    bracket = intent.get('bracket', {})
                    meta = intent.get('meta', {})
                    
                    display_results.append({
                        'symbol': intent['symbol'],
                        'score': meta.get('score', 0),
                        'close': meta.get('close', 0),
                        'entry_price': 0,  # Market order, no fixed price
                        'stop_price': bracket.get('stop_loss', 0),
                        'target_price': bracket.get('take_profit', 0),
                        'shares': intent.get('qty', 0),
                        'risk_amount': 500  # Fixed $500 risk per trade
                    })
                
                # Step 3: Complete
                active_paper_scans[run_id]['progress']['done'] = 100
                active_paper_scans[run_id]['results'] = display_results
                active_paper_scans[run_id]['state'] = 'done'
                active_paper_scans[run_id]['status_message'] = f'Found {len(display_results)} candidates'
                print(f"Paper scan {run_id} found {len(display_results)} candidates meeting criteria (score >= 45)", file=sys.stderr)
            else:
                # Step 3: Complete (no results)
                active_paper_scans[run_id]['progress']['done'] = 100
                active_paper_scans[run_id]['results'] = []
                active_paper_scans[run_id]['state'] = 'done'
                active_paper_scans[run_id]['status_message'] = 'No candidates found meeting criteria'
                print(f"Paper scan {run_id} found no candidates meeting criteria (score >= 45)", file=sys.stderr)
                
        except Exception as e:
            print(f"Paper scan {run_id} failed: {e}", file=sys.stderr)
            active_paper_scans[run_id]['state'] = 'error'
            active_paper_scans[run_id]['error'] = str(e)

def get_score_breakdown(bars, ticker, score, components):
    """Get detailed breakdown of how score was calculated."""
    try:
        # Handle different bar formats (dict vs object with attributes)
        def get_bar_value(bar, key):
            if isinstance(bar, dict):
                # Try different key formats
                return bar.get(key) or bar.get(key[0]) or bar.get(key.upper())
            else:
                # Object with attributes
                return getattr(bar, key, None) or getattr(bar, key[0], None)

        # Get current price info
        current_price = get_bar_value(bars[-1], 'close')
        if not current_price:
            return {'error': 'Could not get current price from bars data'}

        # Calculate price changes safely
        price_change_1d = 0
        price_change_5d = 0

        if len(bars) >= 2:
            prev_price = get_bar_value(bars[-2], 'close')
            if prev_price:
                price_change_1d = ((current_price - prev_price) / prev_price) * 100

        if len(bars) >= 6:
            price_5d = get_bar_value(bars[-6], 'close')
            if price_5d:
                price_change_5d = ((current_price - price_5d) / price_5d) * 100

        # Calculate volume metrics
        volumes = []
        for bar in bars[-20:]:
            vol = get_bar_value(bar, 'volume')
            if vol:
                volumes.append(vol)

        avg_volume_20 = sum(volumes) / len(volumes) if volumes else 0
        current_volume = get_bar_value(bars[-1], 'volume') or 0
        volume_ratio = current_volume / avg_volume_20 if avg_volume_20 > 0 else 1

        # Calculate volatility
        returns = []
        for i in range(1, min(21, len(bars))):
            curr_close = get_bar_value(bars[i], 'close')
            prev_close = get_bar_value(bars[i-1], 'close')
            if curr_close and prev_close:
                returns.append(curr_close / prev_close - 1)

        volatility = 0
        if returns:
            volatility = (sum(r*r for r in returns) / len(returns)) ** 0.5 * (252 ** 0.5) * 100

        # Format components for display
        formatted_components = {}
        if components:
            formatted_components = {
                'Score': f"{score:.2f}" if score else "N/A",
                'Model_version': components.get('model_version', 'N/A'),
                'Percentiles': components.get('percentiles', {}),
                'Raw_features': components.get('raw_features', {}),
                'Gates_passed': components.get('gates_passed', 'N/A'),
                'Market_regime': components.get('market_regime', 'N/A'),
                'Adjusted_weights': components.get('adjusted_weights', {})
            }

        return {
            'total_score': score,
            'components': formatted_components,
            'price_metrics': {
                'current_price': round(current_price, 2),
                'change_1d': round(price_change_1d, 2),
                'change_5d': round(price_change_5d, 2)
            },
            'volume_metrics': {
                'current_volume': int(current_volume),
                'avg_volume_20d': int(avg_volume_20),
                'volume_ratio': round(volume_ratio, 2)
            },
            'risk_metrics': {
                'volatility_annualized': round(volatility, 1),
                'risk_level': 'High' if volatility > 30 else 'Medium' if volatility > 20 else 'Low'
            }
        }
    except Exception as e:
        return {'error': f'Could not calculate breakdown: {str(e)}'}

def get_confidence_level(score, components):
    """Determine confidence level based on score and components."""
    if score is None:
        return 'No Score'

    # Base confidence on score
    if score >= 45:
        base_confidence = 'Very High'
    elif score >= 40:
        base_confidence = 'High'
    elif score >= 35:
        base_confidence = 'Medium'
    elif score >= 30:
        base_confidence = 'Low'
    else:
        base_confidence = 'Very Low'

    return base_confidence

def get_risk_assessment(bars, ticker):
    """Provide risk assessment for the stock."""
    try:
        # Handle different bar formats
        def get_bar_value(bar, key):
            if isinstance(bar, dict):
                return bar.get(key) or bar.get(key[0]) or bar.get(key.upper())
            else:
                return getattr(bar, key, None) or getattr(bar, key[0], None)

        # Calculate various risk metrics
        current_price = get_bar_value(bars[-1], 'close')
        if not current_price:
            return {'error': 'Could not get current price'}

        # Price volatility (20-day)
        returns = []
        for i in range(max(1, len(bars)-20), len(bars)):
            if i > 0:
                curr_close = get_bar_value(bars[i], 'close')
                prev_close = get_bar_value(bars[i-1], 'close')
                if curr_close and prev_close:
                    returns.append(curr_close / prev_close - 1)

        volatility = 0
        if returns:
            volatility = (sum(r*r for r in returns) / len(returns)) ** 0.5 * (252 ** 0.5) * 100

        # Maximum drawdown (60-day)
        prices = []
        for bar in bars[-60:]:
            price = get_bar_value(bar, 'close')
            if price:
                prices.append(price)

        max_drawdown = 0
        if prices:
            peak = prices[0]
            for price in prices:
                if price > peak:
                    peak = price
                drawdown = (peak - price) / peak if peak > 0 else 0
                max_drawdown = max(max_drawdown, drawdown)

        # Volume consistency
        volumes = []
        for bar in bars[-20:]:
            vol = get_bar_value(bar, 'volume')
            if vol:
                volumes.append(vol)

        volume_consistency = 0
        if volumes:
            avg_volume = sum(volumes) / len(volumes)
            if avg_volume > 0:
                volume_std = (sum((v - avg_volume)**2 for v in volumes) / len(volumes)) ** 0.5
                volume_consistency = 1 - (volume_std / avg_volume)

        risk_score = calculate_risk_score(volatility, max_drawdown, volume_consistency)

        return {
            'volatility': round(volatility, 1),
            'max_drawdown_60d': round(max_drawdown * 100, 1),
            'volume_consistency': round(max(0, volume_consistency), 2),
            'risk_score': risk_score,
            'recommendation': get_risk_recommendation(volatility, max_drawdown)
        }
    except Exception as e:
        return {'error': f'Could not assess risk: {str(e)}'}

def calculate_risk_score(volatility, max_drawdown, volume_consistency):
    """Calculate overall risk score (0-100, lower is better)."""
    vol_score = min(volatility * 2, 50)  # Cap at 50
    drawdown_score = max_drawdown * 100 * 0.5  # Weight drawdown
    volume_score = (1 - volume_consistency) * 20  # Inconsistent volume adds risk

    total_risk = vol_score + drawdown_score + volume_score
    return min(100, round(total_risk))

def get_risk_recommendation(volatility, max_drawdown):
    """Get risk-based recommendation."""
    if volatility > 40 or max_drawdown > 0.3:
        return "High Risk - Consider smaller position size"
    elif volatility > 25 or max_drawdown > 0.2:
        return "Medium Risk - Standard position size"
    else:
        return "Lower Risk - Suitable for larger position"


def calculate_confidence_level(score, components):
    """Calculate confidence level based on score and component alignment."""
    if not score or not components:
        return "Unknown"

    # Get raw features for more detailed analysis
    raw_features = components.get('raw_features', {})
    percentiles = components.get('percentiles', {})

    # Count strong signals (percentiles > 60)
    strong_signals = 0
    total_signals = 0

    for key, value in percentiles.items():
        if isinstance(value, (int, float)):
            total_signals += 1
            if value >= 60:
                strong_signals += 1

    # Calculate alignment ratio
    alignment_ratio = strong_signals / total_signals if total_signals > 0 else 0

    # High confidence: Score > 40 AND good alignment
    if score >= 40 and alignment_ratio >= 0.75:
        return "High"
    elif score >= 35 and alignment_ratio >= 0.5:
        return "Medium"
    elif score >= 30:
        return "Low"
    else:
        return "Very Low"


def calculate_trading_levels(bars, symbol, score, components):
    """Calculate entry, stop loss, and target prices for trading."""
    try:
        # Handle different bar formats
        def get_bar_value(bar, key):
            if isinstance(bar, dict):
                return bar.get(key) or bar.get(key[0]) or bar.get(key.upper())
            else:
                return getattr(bar, key, None) or getattr(bar, key[0], None)

        current_price = get_bar_value(bars[-1], 'close')
        if not current_price:
            return {}

        # Get ATR for stop loss calculation
        raw_features = components.get('raw_features', {}) if components else {}
        atr_value = raw_features.get('atr_value', 0)

        # If no ATR, calculate simple volatility
        if not atr_value and len(bars) >= 20:
            returns = []
            for i in range(max(1, len(bars)-20), len(bars)):
                if i > 0:
                    curr_close = get_bar_value(bars[i], 'close')
                    prev_close = get_bar_value(bars[i-1], 'close')
                    if curr_close and prev_close:
                        returns.append(abs(curr_close - prev_close))
            atr_value = sum(returns) / len(returns) if returns else current_price * 0.02

        # Default to 2% if still no ATR
        if not atr_value:
            atr_value = current_price * 0.02

        # Calculate trading levels
        entry_price = current_price  # Market entry
        stop_loss = current_price - (atr_value * 2)  # 2x ATR stop
        target_1 = current_price + (atr_value * 3)   # 3x ATR target (1.5:1 R/R)
        target_2 = current_price + (atr_value * 4)   # 4x ATR target (2:1 R/R)

        # Calculate position sizing (0.5% portfolio risk)
        risk_per_share = current_price - stop_loss
        portfolio_value = 100000  # Assume $100k portfolio
        risk_amount = portfolio_value * 0.005  # 0.5% risk
        shares = int(risk_amount / risk_per_share) if risk_per_share > 0 else 100

        # Ensure minimum viable trade
        shares = max(shares, 1)

        return {
            'entry_price': round(entry_price, 2),
            'stop_loss': round(stop_loss, 2),
            'target_1': round(target_1, 2),
            'target_2': round(target_2, 2),
            'shares': shares,
            'risk_per_share': round(risk_per_share, 2),
            'risk_amount': round(shares * risk_per_share, 2),
            'reward_risk_ratio': round((target_1 - entry_price) / risk_per_share, 2) if risk_per_share > 0 else 0
        }

    except Exception as e:
        return {'error': f'Could not calculate trading levels: {str(e)}'}

def get_stock_insights(bars, symbol, score):
    """Generate actionable insights about the stock."""
    try:
        # Handle different bar formats
        def get_bar_value(bar, key):
            if isinstance(bar, dict):
                return bar.get(key) or bar.get(key[0]) or bar.get(key.upper())
            else:
                return getattr(bar, key, None) or getattr(bar, key[0], None)

        insights = []

        # Price trend analysis
        current_price = get_bar_value(bars[-1], 'close')
        if not current_price:
            return {'error': 'Could not get current price', 'key_insights': []}

        price_5d = get_bar_value(bars[-6], 'close') if len(bars) >= 6 else current_price
        price_20d = get_bar_value(bars[-21], 'close') if len(bars) >= 21 else current_price

        trend_5d = ((current_price - price_5d) / price_5d) * 100 if price_5d else 0
        trend_20d = ((current_price - price_20d) / price_20d) * 100 if price_20d else 0

        if trend_5d > 2:
            insights.append(f"Strong 5-day momentum: +{trend_5d:.1f}%")
        elif trend_5d < -2:
            insights.append(f"Weak 5-day momentum: {trend_5d:.1f}%")

        if trend_20d > 5:
            insights.append(f"Strong 20-day trend: +{trend_20d:.1f}%")
        elif trend_20d < -5:
            insights.append(f"Declining 20-day trend: {trend_20d:.1f}%")

        # Volume analysis
        volumes = []
        for bar in bars[-20:]:
            vol = get_bar_value(bar, 'volume')
            if vol:
                volumes.append(vol)

        avg_volume_20 = sum(volumes) / len(volumes) if volumes else 0
        current_volume = get_bar_value(bars[-1], 'volume') or 0
        volume_ratio = current_volume / avg_volume_20 if avg_volume_20 > 0 else 1

        if volume_ratio > 1.5:
            insights.append(f"High volume activity: {volume_ratio:.1f}x average")
        elif volume_ratio < 0.5:
            insights.append(f"Low volume: {volume_ratio:.1f}x average")

        # Score interpretation
        if score and score >= 40:
            insights.append("High scoring opportunity - strong technical setup")
        elif score and score >= 35:
            insights.append("Moderate scoring opportunity - decent setup")
        elif score and score < 30:
            insights.append("Low score - weak technical setup")

        # Support/Resistance levels
        recent_highs = []
        recent_lows = []
        for bar in bars[-20:]:
            high = get_bar_value(bar, 'high')
            low = get_bar_value(bar, 'low')
            if high:
                recent_highs.append(high)
            if low:
                recent_lows.append(low)

        resistance = max(recent_highs) if recent_highs else current_price
        support = min(recent_lows) if recent_lows else current_price

        distance_to_resistance = ((resistance - current_price) / current_price) * 100
        distance_to_support = ((current_price - support) / current_price) * 100

        if distance_to_resistance < 2:
            insights.append(f"Near resistance at ${resistance:.2f}")
        if distance_to_support < 2:
            insights.append(f"Near support at ${support:.2f}")

        return {
            'key_insights': insights[:5],  # Limit to top 5 insights
            'price_levels': {
                'current': current_price,
                'resistance': resistance,
                'support': support
            },
            'trends': {
                'short_term': trend_5d,
                'medium_term': trend_20d
            },
            'volume_analysis': {
                'current_ratio': round(volume_ratio, 2),
                'interpretation': 'High' if volume_ratio > 1.5 else 'Low' if volume_ratio < 0.5 else 'Normal'
            }
        }
    except Exception as e:
        return {'error': f'Could not generate insights: {str(e)}', 'key_insights': []}

PORT = 8002
print(f"Starting SwingTrading Server v2 on port {PORT}")
print(f"Model version: {MODEL_VERSION}")
print(f"Alpaca API: {'Connected' if ALPACA_KEY else 'Not configured'}")
print(f"Cache: {'Initialized' if data_cache else 'Not available'}")
print(f"Open http://localhost:{PORT}/working.html")

socketserver.TCPServer.allow_reuse_address = True
with socketserver.TCPServer(("", PORT), WorkingHandlerV2) as httpd:
    httpd.serve_forever()
