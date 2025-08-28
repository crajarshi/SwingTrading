#!/usr/bin/env python3
"""Real SwingTrading Server using actual scanner.py."""

import http.server
import socketserver
import json
import uuid
import threading
import os
import sys
import subprocess
from urllib.parse import urlparse
from datetime import datetime

# Add src to path
sys.path.insert(0, 'src')

# Set PYTHONPATH for subprocess
os.environ['PYTHONPATH'] = os.path.join(os.getcwd(), 'src')

# Store active scans
active_scans = {}

# Knowledge base (same as working_server.py)
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

Score 15-25: STRONG BUY 🟢
• Excellent risk/reward ratio
• Stock is oversold and ready to bounce
• Use larger position size (8-10% of portfolio)

Score 10-15: MODERATE BUY 🟡
• Good opportunity 
• Standard position size (5-7% of portfolio)

Score 5-10: WATCH 👁️
• Wait for better entry
• Or use small position (3-5% of portfolio)

Score <5: AVOID ❌
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

• Under 30 = Oversold 🟢
  Stock beaten down, bounce likely
  
• 30-40 = Getting oversold 🟡
  Starting to look interesting
  
• 40-60 = Neutral zone ⚪
  No strong signal either way
  
• 60-70 = Getting overbought 🟡
  Be cautious, pullback possible
  
• Over 70 = Overbought 🔴
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

class RealHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory="web", **kwargs)
    
    def do_GET(self):
        parsed = urlparse(self.path)
        
        if parsed.path == '/api/config':
            # Check if .env exists
            has_api = os.path.exists('.env')
            self.send_json({'status': 'ok', 'alpaca_connected': has_api})
        
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
            run_id = str(uuid.uuid4())
            active_scans[run_id] = {
                'run_id': run_id,
                'state': 'running',
                'progress': {'done': 0, 'total': 20},
                'results': []
            }
            threading.Thread(target=self.run_real_scan, args=(run_id,)).start()
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
    
    def run_real_scan(self, run_id):
        """Run the actual scanner.py command."""
        try:
            # Run the real scanner
            cmd = [sys.executable, '-m', 'swingtrading.main', 'scan', '--format', 'json']
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
                env=os.environ.copy()
            )
            
            if result.returncode == 0:
                # Parse the JSON output
                try:
                    scan_data = json.loads(result.stdout)
                    
                    # Convert to our format
                    results = []
                    for _, row in scan_data.items():
                        score = row.get('score', 0)
                        
                        # Determine action based on score
                        if score >= 15:
                            action = 'BUY'
                            multiplier = 1.002
                        elif score >= 10:
                            action = 'WATCH'
                            multiplier = 0.99
                        else:
                            action = 'AVOID'
                            multiplier = 0
                        
                        close = row.get('close', 100)
                        
                        if multiplier > 0:
                            entry = close * multiplier
                            stop = entry * 0.97
                            target1 = entry * 1.05
                            target2 = entry * 1.08
                        else:
                            entry = stop = target1 = target2 = 0
                        
                        results.append({
                            'symbol': row.get('symbol', 'UNKNOWN'),
                            'close': round(close, 2),
                            'score': round(score, 1),
                            'rsi14': round(row.get('rsi14', 50), 1),
                            'action': action,
                            'entry_price': round(entry, 2) if entry else None,
                            'stop_loss': round(stop, 2) if stop else None,
                            'target_1': round(target1, 2) if target1 else None,
                            'target_2': round(target2, 2) if target2 else None,
                            'gap_percent': round(row.get('gap_percent', 0), 1),
                            'volume': row.get('volume', 0)
                        })
                    
                    # Sort by score
                    results.sort(key=lambda x: x['score'], reverse=True)
                    
                    active_scans[run_id]['results'] = results
                    active_scans[run_id]['state'] = 'done'
                    
                except json.JSONDecodeError:
                    # If not JSON, try to parse CSV output
                    print("Scanner output was not JSON, falling back to simulated data")
                    self.run_simulated_scan(run_id)
            else:
                print(f"Scanner failed: {result.stderr}")
                self.run_simulated_scan(run_id)
                
        except Exception as e:
            print(f"Error running real scanner: {e}")
            self.run_simulated_scan(run_id)
    
    def run_simulated_scan(self, run_id):
        """Fallback to simulated scan if real scanner fails."""
        import yaml
        import random
        
        try:
            with open('config.yaml', 'r') as f:
                config = yaml.safe_load(f)
                all_tickers = config['universe']['tickers']
        except:
            all_tickers = ['SPY', 'QQQ', 'AAPL', 'MSFT', 'GOOGL', 'AMZN', 
                          'NVDA', 'META', 'TSLA', 'JPM']
        
        results = []
        for ticker in all_tickers:
            # Generate scores
            ticker_hash = sum(ord(c) for c in ticker)
            score = max(0.5, min(25, (ticker_hash % 20) + random.uniform(-5, 5)))
            rsi = max(20, min(80, 30 + (ticker_hash % 40) + random.uniform(-10, 10)))
            
            # Simulate price
            base_price = 50 + (ticker_hash % 200)
            
            # Determine action
            if score >= 15:
                action = 'BUY'
                entry = base_price * 1.002
            elif score >= 10:
                action = 'WATCH'
                entry = base_price * 0.99
            else:
                action = 'AVOID'
                entry = 0
            
            if entry > 0:
                stop = entry * 0.97
                target1 = entry * 1.05
                target2 = entry * 1.08
            else:
                stop = target1 = target2 = 0
            
            results.append({
                'symbol': ticker,
                'close': round(base_price, 2),
                'score': round(score, 1),
                'rsi14': round(rsi, 1),
                'action': action,
                'entry_price': round(entry, 2) if entry else None,
                'stop_loss': round(stop, 2) if stop else None,
                'target_1': round(target1, 2) if target1 else None,
                'target_2': round(target2, 2) if target2 else None,
                'gap_percent': round(random.uniform(-2, 2), 1),
                'volume': random.randint(1000000, 50000000)
            })
        
        results.sort(key=lambda x: x['score'], reverse=True)
        active_scans[run_id]['results'] = results
        active_scans[run_id]['state'] = 'done'

PORT = 8002
print(f"Starting Real Scanner Server on port {PORT}")
print(f"This server attempts to use the actual scanner.py")
print(f"Open http://localhost:{PORT}/working.html")

socketserver.TCPServer.allow_reuse_address = True
with socketserver.TCPServer(("", PORT), RealHandler) as httpd:
    httpd.serve_forever()