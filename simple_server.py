#!/usr/bin/env python3
"""Simple HTTP server for SwingTrading Scanner - no external dependencies."""

import http.server
import socketserver
import json
import uuid
import threading
import time
from urllib.parse import urlparse, parse_qs
import random

# Store active scans
active_scans = {}

class ScanHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory="web", **kwargs)
    
    def do_GET(self):
        parsed_path = urlparse(self.path)
        
        # API endpoints
        if parsed_path.path == '/api/config':
            self.send_json({'status': 'ok', 'version': '1.0.0'})
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
                results = self.generate_mock_results()
                self.send_json({'results': results, 'run_id': run_id})
            else:
                self.send_error(404)
        else:
            # Serve static files
            super().do_GET()
    
    def do_POST(self):
        if self.path == '/api/scan':
            # Start a mock scan
            run_id = str(uuid.uuid4())
            active_scans[run_id] = {
                'run_id': run_id,
                'state': 'running',
                'progress': {'done': 0, 'total': 20, 'partial_results': 0}
            }
            
            # Start background thread to simulate progress
            threading.Thread(target=self.simulate_scan, args=(run_id,)).start()
            
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
    
    def simulate_scan(self, run_id):
        """Simulate scan progress."""
        for i in range(1, 21):
            time.sleep(0.2)  # Simulate processing time
            if run_id in active_scans:
                active_scans[run_id]['progress']['done'] = i
                if i > 5:  # Start showing partial results
                    active_scans[run_id]['progress']['partial_results'] = min(i - 5, 10)
        
        # Mark as done
        if run_id in active_scans:
            active_scans[run_id]['state'] = 'done'
            active_scans[run_id]['progress']['partial_results'] = 10
    
    def generate_mock_results(self):
        """Generate mock scan results."""
        symbols = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'TSLA', 'NVDA', 'AMD', 'INTC', 'ORCL']
        results = []
        
        for i, symbol in enumerate(symbols):
            results.append({
                'symbol': symbol,
                'close': round(100 + random.random() * 400, 2),
                'score': round(20 - i * 1.5 + random.random() * 2, 2),
                'rsi14': round(40 + random.random() * 30, 1),
                'gap_percent': round(random.random() * 5 - 2.5, 1),
                'volume': int((5 + random.random() * 20) * 1e6),
                'volume_ratio': round(0.8 + random.random() * 0.6, 2),
                'trend_vs_sma50': round(random.random() * 10 - 5, 1),
                'pullback_from_high20': round(random.random() * 15, 1)
            })
        
        return results

# Start server
PORT = 8000
print(f"Starting server at http://localhost:{PORT}")
print(f"Serving files from: web/")
print(f"API endpoints available:")
print(f"  - GET  /api/config")
print(f"  - POST /api/scan")
print(f"  - GET  /api/scan/{{run_id}}/status")
print(f"  - GET  /api/scan/{{run_id}}/results")
print(f"\nOpen http://localhost:{PORT}/test_working.html to test the UI")

with socketserver.TCPServer(("", PORT), ScanHandler) as httpd:
    httpd.serve_forever()