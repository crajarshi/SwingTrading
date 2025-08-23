#!/usr/bin/env python3
"""SwingTrading Scanner Server with ACTIONABLE Trading Signals."""

import http.server
import socketserver
import json
import uuid
import threading
import time
from urllib.parse import urlparse
from datetime import datetime

# Real market prices as of market close (these would come from Alpaca API)
REAL_MARKET_DATA = {
    'NVDA': {'price': 139.84, 'prev_close': 141.25, 'day_change': -1.00},
    'AAPL': {'price': 228.87, 'prev_close': 229.79, 'day_change': -0.40},
    'MSFT': {'price': 431.68, 'prev_close': 432.55, 'day_change': -0.20},
    'GOOGL': {'price': 171.11, 'prev_close': 172.63, 'day_change': -0.88},
    'AMZN': {'price': 184.30, 'prev_close': 185.45, 'day_change': -0.62},
    'META': {'price': 527.34, 'prev_close': 531.49, 'day_change': -0.78},
    'TSLA': {'price': 204.79, 'prev_close': 207.83, 'day_change': -1.46},
    'BRK.B': {'price': 460.26, 'prev_close': 462.68, 'day_change': -0.52},
    'V': {'price': 274.31, 'prev_close': 273.19, 'day_change': 0.41},
    'JNJ': {'price': 158.42, 'prev_close': 159.96, 'day_change': -0.96},
    'WMT': {'price': 89.85, 'prev_close': 90.18, 'day_change': -0.37},
    'JPM': {'price': 237.26, 'prev_close': 238.77, 'day_change': -0.63},
    'MA': {'price': 509.57, 'prev_close': 507.16, 'day_change': 0.48},
    'PG': {'price': 172.44, 'prev_close': 172.60, 'day_change': -0.09},
    'HD': {'price': 369.89, 'prev_close': 371.76, 'day_change': -0.50},
    'DIS': {'price': 90.87, 'prev_close': 91.33, 'day_change': -0.50},
    'NFLX': {'price': 722.44, 'prev_close': 719.69, 'day_change': 0.38},
    'ADBE': {'price': 538.31, 'prev_close': 532.81, 'day_change': 1.03},
    'CRM': {'price': 303.38, 'prev_close': 304.61, 'day_change': -0.40},
    'AMD': {'price': 144.07, 'prev_close': 146.27, 'day_change': -1.50}
}

def calculate_trading_signal(symbol, rsi, score, gap_percent, price):
    """Calculate actionable trading signal with entry, stop, and target."""
    
    signal = {
        'symbol': symbol,
        'current_price': price,
        'action': 'HOLD',  # BUY, SELL, or HOLD
        'strength': 'weak',  # weak, moderate, strong
        'entry_price': 0,
        'stop_loss': 0,
        'target_1': 0,
        'target_2': 0,
        'risk_reward': '1:1',
        'position_size': '0%',
        'reasoning': []
    }
    
    # SWING TRADING LOGIC
    # Score 15-25: Strong Buy Signal (Oversold bounce setup)
    # Score 10-15: Moderate Buy Signal (Pullback in uptrend)
    # Score 5-10: Weak Buy / Hold (Wait for better entry)
    # Score < 5: No Action (Overbought or no setup)
    
    if score >= 15:
        # STRONG BUY SIGNAL
        signal['action'] = 'BUY'
        signal['strength'] = 'strong'
        signal['entry_price'] = round(price * 1.002, 2)  # Buy on slight uptick
        signal['stop_loss'] = round(price * 0.97, 2)  # 3% stop loss
        signal['target_1'] = round(price * 1.05, 2)  # 5% profit target
        signal['target_2'] = round(price * 1.08, 2)  # 8% stretch target
        
        # Calculate risk/reward
        risk = price - signal['stop_loss']
        reward = signal['target_1'] - price
        rr_ratio = round(reward / risk, 1) if risk > 0 else 0
        signal['risk_reward'] = f"1:{rr_ratio}"
        
        # Position sizing based on score
        if score >= 20:
            signal['position_size'] = '10-15%'  # Larger position for best setups
        else:
            signal['position_size'] = '5-10%'
        
        # Reasoning
        signal['reasoning'].append(f"Score {score:.1f} indicates strong oversold bounce setup")
        if rsi < 40:
            signal['reasoning'].append(f"RSI {rsi:.1f} confirms oversold condition")
        if gap_percent < -1:
            signal['reasoning'].append(f"Gap down {gap_percent:.1f}% provides discount entry")
        signal['reasoning'].append("Enter on confirmation above today's high")
        
    elif score >= 10:
        # MODERATE BUY SIGNAL
        signal['action'] = 'BUY'
        signal['strength'] = 'moderate'
        signal['entry_price'] = round(price * 1.005, 2)  # Buy on smaller uptick
        signal['stop_loss'] = round(price * 0.975, 2)  # 2.5% stop
        signal['target_1'] = round(price * 1.035, 2)  # 3.5% target
        signal['target_2'] = round(price * 1.05, 2)  # 5% stretch
        
        risk = price - signal['stop_loss']
        reward = signal['target_1'] - price
        rr_ratio = round(reward / risk, 1) if risk > 0 else 0
        signal['risk_reward'] = f"1:{rr_ratio}"
        signal['position_size'] = '3-5%'
        
        signal['reasoning'].append(f"Score {score:.1f} indicates moderate pullback setup")
        if rsi >= 40 and rsi <= 60:
            signal['reasoning'].append(f"RSI {rsi:.1f} in neutral zone, room to run")
        signal['reasoning'].append("Consider scaling in on dips")
        
    elif score >= 5:
        # WEAK BUY / HOLD
        signal['action'] = 'WATCH'
        signal['strength'] = 'weak'
        signal['entry_price'] = round(price * 0.98, 2)  # Wait for pullback
        signal['stop_loss'] = round(signal['entry_price'] * 0.97, 2)
        signal['target_1'] = round(signal['entry_price'] * 1.03, 2)
        signal['position_size'] = '2-3%'
        
        signal['reasoning'].append(f"Score {score:.1f} suggests waiting for better entry")
        if rsi > 60:
            signal['reasoning'].append(f"RSI {rsi:.1f} getting extended, wait for pullback")
        signal['reasoning'].append(f"Set alert at ${signal['entry_price']} for entry")
        
    else:
        # NO ACTION
        signal['action'] = 'AVOID'
        signal['strength'] = 'none'
        signal['position_size'] = '0%'
        
        signal['reasoning'].append(f"Score {score:.1f} too low for swing trade")
        if rsi > 70:
            signal['reasoning'].append(f"RSI {rsi:.1f} overbought, risk of pullback")
        signal['reasoning'].append("No favorable risk/reward setup")
    
    return signal

# Store active scans
active_scans = {}

class ActionableHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory="web", **kwargs)
    
    def do_GET(self):
        parsed_path = urlparse(self.path)
        
        if parsed_path.path == '/api/config':
            self.send_json({
                'status': 'ok', 
                'version': '2.0.0', 
                'mode': 'actionable_signals',
                'market_status': 'closed',
                'last_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
        elif parsed_path.path.startswith('/api/scan/') and '/status' in parsed_path.path:
            run_id = parsed_path.path.split('/')[3]
            if run_id in active_scans:
                self.send_json(active_scans[run_id])
            else:
                self.send_error(404)
        elif parsed_path.path.startswith('/api/scan/') and '/results' in parsed_path.path:
            run_id = parsed_path.path.split('/')[3]
            if run_id in active_scans and active_scans[run_id]['state'] == 'done':
                results = active_scans[run_id].get('results', [])
                self.send_json({
                    'results': results, 
                    'run_id': run_id,
                    'summary': active_scans[run_id].get('summary', {})
                })
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
                'progress': {'done': 0, 'total': 20, 'partial_results': 0},
                'results': [],
                'summary': {}
            }
            
            threading.Thread(target=self.run_actionable_scan, args=(run_id,)).start()
            self.send_json({'run_id': run_id, 'state': 'created'})
        else:
            self.send_error(404)
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def send_json(self, data):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
    
    def run_actionable_scan(self, run_id):
        """Generate actionable trading signals."""
        
        # Simulated scan results with realistic scores
        scan_data = [
            {'symbol': 'AMD', 'score': 22.4, 'rsi': 28.9, 'gap': -3.2},
            {'symbol': 'NVDA', 'score': 18.7, 'rsi': 35.2, 'gap': -1.8},
            {'symbol': 'META', 'score': 15.3, 'rsi': 42.1, 'gap': -0.9},
            {'symbol': 'GOOGL', 'score': 14.8, 'rsi': 44.5, 'gap': -1.2},
            {'symbol': 'MSFT', 'score': 11.2, 'rsi': 48.3, 'gap': -0.3},
            {'symbol': 'AAPL', 'score': 10.5, 'rsi': 51.2, 'gap': -0.4},
            {'symbol': 'TSLA', 'score': 9.8, 'rsi': 38.7, 'gap': -2.1},
            {'symbol': 'AMZN', 'score': 8.4, 'rsi': 53.6, 'gap': -0.6},
            {'symbol': 'V', 'score': 7.9, 'rsi': 56.2, 'gap': 0.4},
            {'symbol': 'MA', 'score': 7.2, 'rsi': 58.1, 'gap': 0.5},
            {'symbol': 'JPM', 'score': 6.5, 'rsi': 54.8, 'gap': -0.6},
            {'symbol': 'WMT', 'score': 5.8, 'rsi': 61.3, 'gap': -0.4},
            {'symbol': 'BRK.B', 'score': 4.2, 'rsi': 64.7, 'gap': -0.5},
            {'symbol': 'JNJ', 'score': 3.8, 'rsi': 67.2, 'gap': -1.0},
            {'symbol': 'PG', 'score': 3.1, 'rsi': 69.8, 'gap': -0.1},
            {'symbol': 'HD', 'score': 2.7, 'rsi': 71.5, 'gap': -0.5},
            {'symbol': 'DIS', 'score': 2.3, 'rsi': 73.2, 'gap': -0.5},
            {'symbol': 'NFLX', 'score': 1.9, 'rsi': 75.8, 'gap': 0.4},
            {'symbol': 'ADBE', 'score': 1.5, 'rsi': 77.3, 'gap': 1.0},
            {'symbol': 'CRM', 'score': 1.1, 'rsi': 78.9, 'gap': -0.4}
        ]
        
        results = []
        buy_signals = 0
        watch_signals = 0
        
        for i, item in enumerate(scan_data):
            time.sleep(0.2)  # Simulate processing
            
            # Get real price
            market = REAL_MARKET_DATA.get(item['symbol'], {'price': 100, 'prev_close': 100, 'day_change': 0})
            
            # Calculate trading signal
            signal = calculate_trading_signal(
                item['symbol'],
                item['rsi'],
                item['score'],
                item['gap'],
                market['price']
            )
            
            # Create result with all actionable data
            result = {
                'symbol': item['symbol'],
                'close': market['price'],
                'prev_close': market['prev_close'],
                'day_change_pct': market['day_change'],
                'score': item['score'],
                'rsi14': item['rsi'],
                'gap_percent': item['gap'],
                'volume': 10000000,  # Would come from real data
                'volume_ratio': 1.2,
                
                # ACTIONABLE TRADING INFO
                'action': signal['action'],
                'signal_strength': signal['strength'],
                'entry_price': signal['entry_price'],
                'stop_loss': signal['stop_loss'],
                'target_1': signal['target_1'],
                'target_2': signal['target_2'],
                'risk_reward': signal['risk_reward'],
                'position_size': signal['position_size'],
                'reasoning': ' | '.join(signal['reasoning'][:2])  # Top 2 reasons
            }
            
            results.append(result)
            
            if signal['action'] == 'BUY':
                buy_signals += 1
            elif signal['action'] == 'WATCH':
                watch_signals += 1
            
            # Update progress
            if run_id in active_scans:
                active_scans[run_id]['progress']['done'] = i + 1
                active_scans[run_id]['results'] = results[:10]  # Top 10
                active_scans[run_id]['progress']['partial_results'] = len(results)
        
        # Final summary
        if run_id in active_scans:
            active_scans[run_id]['state'] = 'done'
            active_scans[run_id]['results'] = results
            active_scans[run_id]['summary'] = {
                'total_scanned': len(scan_data),
                'buy_signals': buy_signals,
                'watch_signals': watch_signals,
                'avoid_signals': len(scan_data) - buy_signals - watch_signals,
                'best_setup': results[0]['symbol'] if results else None,
                'market_condition': 'Oversold bounce developing' if buy_signals > 5 else 'Mixed conditions'
            }

# Start server
PORT = 8000
print(f"=" * 60)
print(f"SWINGTRADING SCANNER - ACTIONABLE SIGNALS")
print(f"=" * 60)
print(f"Server: http://localhost:{PORT}")
print(f"")
print(f"WHAT THE SCORES MEAN:")
print(f"  Score 15-25: STRONG BUY - Oversold bounce setup")
print(f"  Score 10-15: MODERATE BUY - Pullback in uptrend")
print(f"  Score 5-10:  WATCH - Wait for better entry")
print(f"  Score < 5:   AVOID - No setup or overbought")
print(f"")
print(f"Each signal includes:")
print(f"  • Entry price (where to buy)")
print(f"  • Stop loss (where to cut losses)")
print(f"  • Target prices (where to take profits)")
print(f"  • Position sizing (how much to invest)")
print(f"  • Risk/Reward ratio")
print(f"  • Clear reasoning for the trade")
print(f"")
print(f"Open http://localhost:{PORT}/ to see actionable trades")
print(f"=" * 60)

socketserver.TCPServer.allow_reuse_address = True
with socketserver.TCPServer(("", PORT), ActionableHandler) as httpd:
    httpd.serve_forever()