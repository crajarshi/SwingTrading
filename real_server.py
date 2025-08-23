#!/usr/bin/env python3
"""Real SwingTrading Scanner Server - Uses actual Alpaca API data."""

import http.server
import socketserver
import json
import uuid
import threading
import asyncio
from urllib.parse import urlparse
import os
import sys

# Read .env file manually
env_file = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(env_file):
    with open(env_file) as f:
        for line in f:
            if '=' in line and not line.startswith('#'):
                key, value = line.strip().split('=', 1)
                os.environ[key] = value

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Import the actual scanner
from swingtrading.scanner import Scanner
from swingtrading.config import Config
from swingtrading.data_provider import AlpacaDataProvider

# Store active scans
active_scans = {}

class RealScanHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory="web", **kwargs)
    
    def do_GET(self):
        parsed_path = urlparse(self.path)
        
        # API endpoints
        if parsed_path.path == '/api/config':
            self.send_json({'status': 'ok', 'version': '1.0.0', 'mode': 'real_data'})
        elif parsed_path.path.startswith('/api/scan/') and '/status' in parsed_path.path:
            run_id = parsed_path.path.split('/')[3]
            if run_id in active_scans:
                scan = active_scans[run_id]
                self.send_json(scan)
            else:
                self.send_error(404)
        elif parsed_path.path.startswith('/api/scan/') and '/results' in parsed_path.path:
            run_id = parsed_path.path.split('/')[3]
            if run_id in active_scans and active_scans[run_id]['state'] == 'done':
                results = active_scans[run_id].get('results', [])
                self.send_json({'results': results, 'run_id': run_id})
            else:
                self.send_error(404)
        else:
            # Serve static files
            super().do_GET()
    
    def do_POST(self):
        if self.path == '/api/scan':
            # Start a real scan
            run_id = str(uuid.uuid4())
            active_scans[run_id] = {
                'run_id': run_id,
                'state': 'running',
                'progress': {'done': 0, 'total': 0, 'partial_results': 0},
                'results': []
            }
            
            # Start background thread to run real scan
            threading.Thread(target=self.run_real_scan, args=(run_id,)).start()
            
            self.send_json({'run_id': run_id, 'state': 'created'})
        else:
            self.send_error(404)
    
    def do_OPTIONS(self):
        # Handle CORS preflight
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
    
    def run_real_scan(self, run_id):
        """Run actual scan using Alpaca API."""
        try:
            print(f"Starting real scan {run_id}")
            
            # Create event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # Initialize components
            config = Config()
            
            # Use a smaller universe for faster testing
            config.universe = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 
                              'TSLA', 'NVDA', 'AMD', 'INTC', 'ORCL',
                              'IBM', 'CSCO', 'ADBE', 'CRM', 'NFLX']
            
            # Update scan status with total
            active_scans[run_id]['progress']['total'] = len(config.universe)
            
            provider = AlpacaDataProvider(
                api_key=os.getenv('ALPACA_API_KEY'),
                api_secret=os.getenv('ALPACA_API_SECRET'),
                feed=config.feed
            )
            
            scanner = Scanner(config, provider)
            
            # Progress callback
            def on_progress(done, total, symbol=None):
                if run_id in active_scans:
                    active_scans[run_id]['progress']['done'] = done
                    active_scans[run_id]['progress']['total'] = total
                    if done > 0:
                        active_scans[run_id]['progress']['partial_results'] = len(active_scans[run_id]['results'])
                    print(f"Scan {run_id}: {done}/{total} - {symbol}")
            
            # Run the scan
            results = loop.run_until_complete(
                self.async_scan(scanner, on_progress)
            )
            
            # Convert results to JSON-serializable format
            json_results = []
            for r in results[:10]:  # Top 10 results
                json_results.append({
                    'symbol': r.symbol,
                    'close': float(r.close),
                    'score': float(r.score),
                    'rsi14': float(r.rsi14),
                    'gap_percent': float(r.gap_percent),
                    'volume': int(r.volume),
                    'volume_ratio': float(r.volume / 1e6),  # Convert to millions
                    'trend_vs_sma50': 0.0,  # Would need calculation
                    'pullback_from_high20': 0.0  # Would need calculation
                })
            
            # Update scan with results
            if run_id in active_scans:
                active_scans[run_id]['state'] = 'done'
                active_scans[run_id]['results'] = json_results
                active_scans[run_id]['progress']['partial_results'] = len(json_results)
                print(f"Scan {run_id} complete with {len(json_results)} results")
            
        except Exception as e:
            print(f"Error in scan {run_id}: {e}")
            if run_id in active_scans:
                active_scans[run_id]['state'] = 'error'
                active_scans[run_id]['error'] = str(e)
        finally:
            loop.close()
    
    async def async_scan(self, scanner, on_progress):
        """Async wrapper for scan with progress."""
        results = []
        total = len(scanner.config.universe)
        
        for i, symbol in enumerate(scanner.config.universe):
            try:
                # Scan single symbol
                symbol_results = await scanner.scan([symbol])
                if symbol_results:
                    results.extend(symbol_results)
                    # Keep results sorted by score
                    results.sort(key=lambda x: x.score, reverse=True)
            except Exception as e:
                print(f"Error scanning {symbol}: {e}")
            
            # Update progress
            on_progress(i + 1, total, symbol)
        
        return results

# Start server
PORT = 8000
print(f"Starting REAL DATA server at http://localhost:{PORT}")
print(f"Using Alpaca API credentials from .env")
print(f"API endpoints available:")
print(f"  - GET  /api/config")
print(f"  - POST /api/scan")
print(f"  - GET  /api/scan/{{run_id}}/status")
print(f"  - GET  /api/scan/{{run_id}}/results")
print(f"\nOpen http://localhost:{PORT}/ to use the UI with REAL market data")

# Make sure we can reuse the port
socketserver.TCPServer.allow_reuse_address = True

with socketserver.TCPServer(("", PORT), RealScanHandler) as httpd:
    httpd.serve_forever()