#!/usr/bin/env python3
"""Working SwingTrading Server with Real Alpaca Data."""

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
from datetime import datetime

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

def get_real_price(symbol):
    """Get real price from Alpaca."""
    try:
        url = f"https://data.alpaca.markets/v2/stocks/{symbol}/trades/latest?feed=iex"
        req = urllib.request.Request(url, headers={
            'APCA-API-KEY-ID': ALPACA_KEY,
            'APCA-API-SECRET-KEY': ALPACA_SECRET
        })
        response = urllib.request.urlopen(req)
        data = json.loads(response.read())
        return data['trade']['p'] if 'trade' in data else 100.0
    except:
        return 100.0

def get_historical_data(symbol, days=90):
    """Get historical OHLCV data from Alpaca."""
    try:
        from datetime import datetime, timedelta
        # Use today as end date - Alpaca will return data up to last trading day
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        
        url = f"https://data.alpaca.markets/v2/stocks/{symbol}/bars?start={start_date}&end={end_date}&timeframe=1Day&feed=iex"
        
        print(f"Fetching historical data for {symbol} from {start_date} to {end_date}", file=sys.stderr)
        
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
        
        if 'bars' in data and data['bars']:
            bar_count = len(data['bars'])
            print(f"Got {bar_count} bars for {symbol}", file=sys.stderr)
            return data['bars']
        else:
            print(f"No bars data in response for {symbol}: {data.keys()}", file=sys.stderr)
            return None
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8') if e.fp else ""
        print(f"ERROR fetching historical data for {symbol}: HTTP {e.code} - {error_body}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"ERROR fetching historical data for {symbol}: {e}", file=sys.stderr)
        return None

def calculate_indicators(bars):
    """Calculate technical indicators from historical data."""
    if not bars:
        print(f"ERROR: No bars provided to calculate_indicators", file=sys.stderr)
        return None
    if len(bars) < 40:
        print(f"ERROR: Insufficient bars for indicators: {len(bars)} < 40", file=sys.stderr)
        return None
    
    # Extract price and volume data
    closes = [bar['c'] for bar in bars]
    highs = [bar['h'] for bar in bars]
    lows = [bar['l'] for bar in bars]
    opens = [bar['o'] for bar in bars]
    volumes = [bar['v'] for bar in bars]
    
    # Calculate SMAs
    sma20 = sum(closes[-20:]) / 20
    # Use available data for SMA50, or at least 40 bars
    sma50_period = min(50, len(closes))
    sma50 = sum(closes[-sma50_period:]) / sma50_period
    
    # Calculate 20-day high
    high20 = max(highs[-20:])
    
    # Calculate RSI (14-period)
    def calculate_rsi(prices, period=14):
        if len(prices) < period + 1:
            return 50  # Default neutral RSI
        
        deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
        gains = [d if d > 0 else 0 for d in deltas]
        losses = [-d if d < 0 else 0 for d in deltas]
        
        # Use simple moving average for RSI
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        
        if avg_loss == 0:
            return 100 if avg_gain > 0 else 50
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    rsi14 = calculate_rsi(closes)
    
    # Calculate ATR (20-period)
    def calculate_atr(highs, lows, closes, period=20):
        trs = []
        for i in range(1, len(highs)):
            high_low = highs[i] - lows[i]
            high_close = abs(highs[i] - closes[i-1])
            low_close = abs(lows[i] - closes[i-1])
            tr = max(high_low, high_close, low_close)
            trs.append(tr)
        
        if len(trs) >= period:
            return sum(trs[-period:]) / period
        return 0
    
    atr20 = calculate_atr(highs, lows, closes)
    
    # Calculate volume average (10-day, excluding current)
    volume_avg_10d = sum(volumes[-11:-1]) / 10 if len(volumes) > 10 else volumes[-1]
    
    # Gap percentage
    if len(closes) > 1 and closes[-2] != 0:
        gap_percent = ((opens[-1] - closes[-2]) / closes[-2]) * 100
    else:
        gap_percent = 0
    
    return {
        'close': closes[-1],
        'sma20': sma20,
        'sma50': sma50,
        'high20': high20,
        'rsi14': rsi14,
        'atr20': atr20,
        'volume': volumes[-1],
        'volume_avg_10d': volume_avg_10d,
        'gap_percent': gap_percent
    }

def calculate_proper_score(indicators):
    """Calculate weighted composite score based on actual indicators."""
    if not indicators:
        return {'total': 0, 'components': {}}
    
    # Extract values
    close = indicators['close']
    high20 = indicators['high20']
    sma50 = indicators['sma50']
    rsi14 = indicators['rsi14']
    volume = indicators['volume']
    volume_avg = indicators['volume_avg_10d']
    
    # Component 1: Pullback proximity (30% weight)
    if high20 > 0:
        pullback_pct = ((high20 - close) / high20) * 100
        pullback_score = (1 - close / high20) * 100
        pullback_score = max(0, min(100, pullback_score))  # Clamp to 0-100
    else:
        pullback_pct = 0
        pullback_score = 0
    
    # Component 2: Trend strength (25% weight)
    if sma50 > 0:
        trend_pct = ((close - sma50) / sma50) * 100
        trend_score = ((close / sma50) - 1) * 100
        trend_score = max(0, min(100, trend_score))  # Clamp to 0-100
    else:
        trend_pct = 0
        trend_score = 0
    
    # Component 3: RSI headroom (25% weight)
    rsi_room = 70 - rsi14
    rsi_room_score = max(0, min(100, rsi_room))  # Clamp to 0-100
    
    # Component 4: Volume ratio (20% weight)
    if volume_avg > 0:
        vol_ratio_actual = volume / volume_avg
        vol_ratio_score = (volume / volume_avg) * 20
        vol_ratio_score = max(0, min(100, vol_ratio_score))  # Clamp to 0-100
    else:
        vol_ratio_actual = 0
        vol_ratio_score = 0
    
    # Calculate weighted score
    total_score = (
        pullback_score * 0.30 +
        trend_score * 0.25 +
        rsi_room_score * 0.25 +
        vol_ratio_score * 0.20
    )
    
    return {
        'total': max(0, min(100, total_score)),
        'components': {
            'pullback': {
                'score': pullback_score,
                'weighted': pullback_score * 0.30,
                'pct_below_high': pullback_pct,
                'high20': high20
            },
            'trend': {
                'score': trend_score,
                'weighted': trend_score * 0.25,
                'pct_vs_sma50': trend_pct,
                'sma50': sma50
            },
            'rsi': {
                'score': rsi_room_score,
                'weighted': rsi_room_score * 0.25,
                'value': rsi14,
                'headroom': rsi_room
            },
            'volume': {
                'score': vol_ratio_score,
                'weighted': vol_ratio_score * 0.20,
                'ratio': vol_ratio_actual,
                'current': volume,
                'average': volume_avg
            }
        }
    }

def determine_action(score, indicators, preset='balanced'):
    """Determine trading action based on score, RSI, and preset."""
    if not indicators:
        return 'AVOID'
    
    # Get preset thresholds from KNOWLEDGE
    presets = {
        "conservative": {"min_score": 15, "max_rsi": 40, "watch_score": 12},
        "balanced": {"min_score": 10, "max_rsi": 50, "watch_score": 7},
        "aggressive": {"min_score": 5, "max_rsi": 60, "watch_score": 3}
    }
    
    settings = presets.get(preset, presets['balanced'])
    
    rsi = indicators['rsi14']
    close = indicators['close']
    sma50 = indicators['sma50']
    
    # Never buy overbought stocks
    if rsi > 70:
        return 'AVOID'
    
    # Reduce score if below 50-day average (weak trend)
    if sma50 > 0 and close < sma50:
        score = score * 0.7
    
    # Apply preset-specific thresholds
    if score >= settings['min_score'] and rsi <= settings['max_rsi']:
        return 'BUY'
    elif score >= settings['watch_score'] and rsi < 65:
        return 'WATCH'
    else:
        return 'AVOID'

# Store active scans
active_scans = {}

# Knowledge base for educational content
KNOWLEDGE = {
    "what_is_swing": {
        "title": "What is Swing Trading?",
        "content": """Swing trading is a strategy where you:
• Hold stocks for 2-10 days (not minutes, not months)
• Target 3-8% gains per trade
• Buy when stocks are oversold (RSI under 40)
• Sell when they bounce back up
• Use stop losses to limit risk to 2-3%

Think of it like catching a wave - you ride the price movement for a short distance, then get out with profit."""
    },
    "understanding_scores": {
        "title": "Understanding Scores",
        "content": """The score tells you how good the setup is:

Score 15-25: STRONG BUY
• Excellent risk/reward ratio
• Stock is oversold and ready to bounce
• Use larger position size (8-10% of portfolio)

Score 10-15: MODERATE BUY
• Good opportunity 
• Standard position size (5-7% of portfolio)

Score 5-10: WATCH
• Wait for better entry
• Or use small position (3-5% of portfolio)

Score <5: AVOID
• No clear setup
• Poor risk/reward"""
    },
    "how_to_trade": {
        "title": "How to Execute a Trade",
        "content": """Step-by-step process:

1. See a BUY signal in the scanner
2. Check the entry price (e.g., $150.30)
3. Place a 'Buy Stop' order at entry price
4. Once filled, immediately set:
   • Stop loss order (protect downside)
   • Limit sell at Target 1 (take profits)
5. When Target 1 hits, sell half position
6. Move stop to breakeven for remaining shares
7. Sell rest at Target 2 or if stopped out"""
    },
    "risk_management": {
        "title": "Risk Management Rules",
        "content": """Golden rules to protect your money:

1. ALWAYS use stop losses (no exceptions!)
2. Never risk more than 2% on a single trade
3. Maximum 3 trades open at once
4. Keep 30-50% cash for opportunities
5. If down 5% in a month, stop and review

Position sizing example:
• $10,000 account
• Strong signal = $1,000 position (10%)
• With 3% stop loss = Risk only $30"""
    },
    "rsi_explained": {
        "title": "Understanding RSI",
        "content": """RSI (Relative Strength Index) measures momentum:

• Under 30 = Oversold (GREEN)
  Stock beaten down, bounce likely
  
• 30-40 = Getting oversold (YELLOW)
  Starting to look interesting
  
• 40-60 = Neutral zone
  No strong signal either way
  
• 60-70 = Getting overbought (YELLOW)
  Be cautious, pullback possible
  
• Over 70 = Overbought (RED)
  Too extended, avoid buying"""
    },
    "presets": {
        "conservative": {"min_score": 15, "max_rsi": 40, "position_size": "3-5%"},
        "balanced": {"min_score": 10, "max_rsi": 50, "position_size": "5-8%"},
        "aggressive": {"min_score": 5, "max_rsi": 60, "position_size": "8-12%"}
    },
    "scoring_system": {
        "title": "How Scoring Works",
        "content": """The score (0-100) ranks stocks by swing trade potential:

FOUR COMPONENTS:
1. Pullback (30%): Distance from 20-day high
   • 5-10% pullback is ideal
   • Shows temporary weakness in strong stock

2. Trend (25%): Price vs 50-day average
   • Above average = uptrend
   • 5-10% above is perfect zone

3. RSI Room (25%): How far from overbought
   • RSI under 40 = lots of room to rise
   • RSI over 70 = too extended

4. Volume (20%): Current vs 10-day average
   • 1.5-2x average = strong interest
   • Confirms the price movement

SCORE RANGES:
• 70-100: EXCEPTIONAL - Rare perfect setup
• 40-70: STRONG BUY - Great opportunity
• 20-40: MODERATE - Decent setup
• 10-20: WATCH - Wait for improvement
• 0-10: AVOID - Poor risk/reward

Example: Score 45 means:
Good pullback + Strong trend + Room to rise = BUY"""
    }
}

class WorkingHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory="web", **kwargs)
    
    def do_GET(self):
        parsed = urlparse(self.path)
        
        if parsed.path == '/api/config':
            self.send_json({'status': 'ok', 'alpaca_connected': bool(ALPACA_KEY)})
        
        elif parsed.path == '/api/knowledge':
            self.send_json(KNOWLEDGE)
        
        elif parsed.path.startswith('/api/scan/') and '/status' in parsed.path:
            run_id = parsed.path.split('/')[3]
            if run_id in active_scans:
                self.send_json(active_scans[run_id])
            else:
                self.send_error(404)
        
        elif parsed.path.startswith('/api/scan/') and '/results' in parsed.path:
            run_id = parsed.path.split('/')[3]
            if run_id in active_scans and active_scans[run_id]['state'] == 'done':
                self.send_json({'results': active_scans[run_id]['results']})
            else:
                self.send_error(404)
        
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
                'preset': request_data.get('preset', 'balanced')
            }
            threading.Thread(target=self.run_scan, args=(run_id,)).start()
            self.send_json({'run_id': run_id})
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
    
    def run_scan(self, run_id):
        """Run scan with real Alpaca prices."""
        import random
        
        # Debug: Check API credentials
        print(f"Starting scan with Alpaca API configured: {bool(ALPACA_KEY and ALPACA_SECRET)}", file=sys.stderr)
        if ALPACA_KEY:
            print(f"API Key present (first 4 chars): {ALPACA_KEY[:4]}...", file=sys.stderr)
        else:
            print(f"WARNING: No API Key found!", file=sys.stderr)
        
        # Determine which tickers to scan
        if active_scans[run_id].get('custom_tickers'):
            # Use custom tickers provided by user
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
        
        # Scan ALL S&P 500 stocks - no limiting
        # The UI will handle pagination to show 20 at a time
        # Note: In production, you may want to implement rate limiting or batching
        
        # Process each ticker with real data
        stocks_with_scores = []
        active_scans[run_id]['progress']['total'] = len(all_tickers)
        
        for i, ticker in enumerate(all_tickers):
            try:
                # Get historical data
                bars = get_historical_data(ticker)
                
                if bars:
                    # Calculate indicators
                    indicators = calculate_indicators(bars)
                    
                    if indicators:
                        # Calculate proper score with components
                        score_data = calculate_proper_score(indicators)
                        score = score_data['total']
                        
                        # Determine action using preset
                        preset = active_scans[run_id].get('preset', 'balanced')
                        action = determine_action(score, indicators, preset)
                        
                        stocks_with_scores.append({
                            'symbol': ticker,
                            'indicators': indicators,
                            'score': score,
                            'score_components': score_data['components'],
                            'action': action
                        })
                else:
                    # Fallback for stocks with no data
                    print(f"No historical data for {ticker}, using fallback", file=sys.stderr)
                    stocks_with_scores.append({
                        'symbol': ticker,
                        'indicators': {
                            'close': get_real_price(ticker),
                            'rsi14': 50,
                            'volume': 1000000,
                            'gap_percent': 0
                        },
                        'score': 5,
                        'action': 'AVOID'
                    })
            except Exception as e:
                print(f"Error processing {ticker}: {e}", file=sys.stderr)
                # Fallback for errors
                stocks_with_scores.append({
                    'symbol': ticker,
                    'indicators': {
                        'close': get_real_price(ticker),
                        'rsi14': 50,
                        'volume': 1000000,
                        'gap_percent': 0
                    },
                    'score': 5,
                    'action': 'AVOID'
                })
            
            # Update progress
            active_scans[run_id]['progress']['done'] = i + 1
            time.sleep(0.2)  # Small delay to avoid rate limiting
        
        # Sort by score descending
        stocks_with_scores.sort(key=lambda x: x['score'], reverse=True)
        
        print(f"Scanned {len(stocks_with_scores)} stocks total", file=sys.stderr)
        
        # Format ALL results for UI (UI will handle pagination)
        results = []
        for stock_data in stocks_with_scores:
            indicators = stock_data['indicators']
            close = indicators['close']
            action = stock_data['action']
            
            # Calculate entry and targets based on action
            if action == 'BUY':
                entry = close * 1.002
                stop = close * 0.97
                target1 = close * 1.05  # 5% gain
                target2 = close * 1.08  # 8% gain
            elif action == 'WATCH':
                entry = close * 0.99
                stop = entry * 0.97
                target1 = entry * 1.03  # 3% gain
                target2 = entry * 1.05  # 5% gain
            else:
                entry = stop = target1 = target2 = 0
            
            result_data = {
                'symbol': stock_data['symbol'],
                'close': round(close, 2),
                'score': round(stock_data['score'], 1),
                'rsi14': round(indicators.get('rsi14', 50), 1),
                'action': action,
                'entry_price': round(entry, 2) if entry else None,
                'stop_loss': round(stop, 2) if stop else None,
                'target_1': round(target1, 2) if target1 else None,
                'target_2': round(target2, 2) if target2 else None,
                'gap_percent': round(indicators.get('gap_percent', 0), 1),
                'volume': indicators.get('volume', 0)
            }
            
            # Add score components if available
            if 'score_components' in stock_data:
                result_data['score_components'] = stock_data['score_components']
            
            results.append(result_data)
        
        active_scans[run_id]['state'] = 'done'
        active_scans[run_id]['results'] = results

PORT = 8001
print(f"Starting Working Server on port {PORT}")
print(f"Alpaca API: {'Connected' if ALPACA_KEY else 'Not configured'}")
print(f"Open http://localhost:{PORT}/working.html")

socketserver.TCPServer.allow_reuse_address = True
with socketserver.TCPServer(("", PORT), WorkingHandler) as httpd:
    httpd.serve_forever()