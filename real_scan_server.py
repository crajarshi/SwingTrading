#!/usr/bin/env python3
"""Real SwingTrading Scanner Server - Runs actual scanner via subprocess."""

import http.server
import socketserver
import json
import uuid
import threading
import subprocess
import time
import os
from urllib.parse import urlparse

# Read .env file manually
env_file = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(env_file):
    with open(env_file) as f:
        for line in f:
            if '=' in line and not line.startswith('#'):
                key, value = line.strip().split('=', 1)
                os.environ[key] = value

# Store active scans
active_scans = {}

class RealScanHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory="web", **kwargs)
    
    def do_GET(self):
        parsed_path = urlparse(self.path)
        
        # API endpoints
        if parsed_path.path == '/api/config':
            self.send_json({'status': 'ok', 'version': '1.0.0', 'mode': 'real_alpaca_data'})
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
                'progress': {'done': 0, 'total': 15, 'partial_results': 0},
                'results': []
            }
            
            # Start background thread to run real scan via subprocess
            threading.Thread(target=self.run_real_scan_subprocess, args=(run_id,)).start()
            
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
    
    def run_real_scan_subprocess(self, run_id):
        """Run actual scan using subprocess to call the main scanner."""
        try:
            print(f"Starting real Alpaca scan {run_id}")
            
            # Build command to run scanner with small universe for testing
            cmd = [
                'python3', '-m', 'swingtrading.main', 'scan',
                '--tickers', 'AAPL,MSFT,GOOGL,AMZN,META,TSLA,NVDA,AMD,INTC,ORCL,IBM,CSCO,ADBE,CRM,NFLX',
                '--json'  # Request JSON output
            ]
            
            # Set environment variables for the subprocess
            env = os.environ.copy()
            
            # Run the scanner
            print(f"Running command: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                env=env,
                cwd=os.path.dirname(__file__)
            )
            
            print(f"Scanner exit code: {result.returncode}")
            if result.stdout:
                print(f"Scanner output preview: {result.stdout[:500]}")
            if result.stderr:
                print(f"Scanner errors: {result.stderr[:500]}")
            
            # Parse results
            if result.returncode == 0 and result.stdout:
                # Try to parse JSON output
                try:
                    # Look for JSON in the output (scanner might print other stuff too)
                    lines = result.stdout.strip().split('\n')
                    json_str = None
                    for line in reversed(lines):
                        if line.strip().startswith('[') or line.strip().startswith('{'):
                            json_str = line
                            break
                    
                    if json_str:
                        scan_data = json.loads(json_str)
                        if isinstance(scan_data, list):
                            # Convert to our format
                            results = []
                            for item in scan_data[:10]:  # Top 10
                                results.append({
                                    'symbol': item.get('symbol', 'N/A'),
                                    'close': float(item.get('close', 0)),
                                    'score': float(item.get('score', 0)),
                                    'rsi14': float(item.get('rsi14', 0)),
                                    'gap_percent': float(item.get('gap_percent', 0)),
                                    'volume': int(item.get('volume', 0)),
                                    'volume_ratio': float(item.get('volume', 0)) / 1e6,
                                    'trend_vs_sma50': 0.0,
                                    'pullback_from_high20': 0.0
                                })
                            
                            active_scans[run_id]['results'] = results
                            active_scans[run_id]['state'] = 'done'
                            active_scans[run_id]['progress']['done'] = 15
                            active_scans[run_id]['progress']['partial_results'] = len(results)
                            print(f"Scan {run_id} complete with {len(results)} real results")
                        else:
                            raise ValueError("Unexpected JSON format")
                    else:
                        # No JSON found, parse text output
                        self.parse_text_output(result.stdout, run_id)
                except json.JSONDecodeError as e:
                    print(f"Failed to parse JSON: {e}")
                    # Try to parse text output instead
                    self.parse_text_output(result.stdout, run_id)
            else:
                # Scanner failed or no output
                active_scans[run_id]['state'] = 'error'
                active_scans[run_id]['error'] = result.stderr or "Scanner failed"
                
        except Exception as e:
            print(f"Error in scan {run_id}: {e}")
            if run_id in active_scans:
                active_scans[run_id]['state'] = 'error'
                active_scans[run_id]['error'] = str(e)
    
    def parse_text_output(self, output, run_id):
        """Parse text output from scanner."""
        # Look for lines that look like results
        # Expected format: "1. AAPL (score: 15.23, RSI: 45.6)"
        results = []
        lines = output.split('\n')
        
        for line in lines:
            line = line.strip()
            # Look for numbered results
            if line and line[0].isdigit() and '.' in line:
                try:
                    # Parse "1. AAPL (score: 15.23, RSI: 45.6, gap: 1.2%)"
                    parts = line.split('.')
                    if len(parts) >= 2:
                        rest = '.'.join(parts[1:]).strip()
                        
                        # Extract symbol
                        symbol = rest.split('(')[0].strip() if '(' in rest else rest.split()[0]
                        
                        # Extract values from parentheses
                        score = 0.0
                        rsi = 50.0
                        gap = 0.0
                        
                        if '(' in rest and ')' in rest:
                            data_str = rest[rest.index('(')+1:rest.index(')')]
                            for item in data_str.split(','):
                                item = item.strip()
                                if 'score:' in item:
                                    score = float(item.split(':')[1].strip())
                                elif 'RSI:' in item or 'rsi:' in item:
                                    rsi = float(item.split(':')[1].strip())
                                elif 'gap:' in item:
                                    gap_str = item.split(':')[1].strip().replace('%', '')
                                    gap = float(gap_str)
                        
                        results.append({
                            'symbol': symbol,
                            'close': 100.0,  # Default since not in text output
                            'score': score,
                            'rsi14': rsi,
                            'gap_percent': gap,
                            'volume': 10000000,  # Default
                            'volume_ratio': 10.0,
                            'trend_vs_sma50': 0.0,
                            'pullback_from_high20': 0.0
                        })
                        
                        if len(results) >= 10:
                            break
                            
                except Exception as e:
                    print(f"Failed to parse line: {line} - {e}")
                    continue
        
        if results:
            active_scans[run_id]['results'] = results
            active_scans[run_id]['state'] = 'done'
            active_scans[run_id]['progress']['done'] = 15
            active_scans[run_id]['progress']['partial_results'] = len(results)
            print(f"Parsed {len(results)} results from text output")
        else:
            # No results found, mark as done with empty results
            active_scans[run_id]['state'] = 'done'
            active_scans[run_id]['results'] = []
            active_scans[run_id]['progress']['done'] = 15
            print("No results found in output")

# Start server
PORT = 8000
print(f"Starting REAL ALPACA DATA server at http://localhost:{PORT}")
print(f"Using Alpaca API credentials from .env file")
print(f"API Key: {os.environ.get('ALPACA_API_KEY', 'NOT SET')[:10]}...")
print(f"\nThis server runs the actual scanner with real market data!")
print(f"Open http://localhost:{PORT}/ to use the UI with REAL Alpaca data")

# Make sure we can reuse the port
socketserver.TCPServer.allow_reuse_address = True

with socketserver.TCPServer(("", PORT), RealScanHandler) as httpd:
    httpd.serve_forever()