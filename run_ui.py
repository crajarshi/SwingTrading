#!/usr/bin/env python3
"""
SwingTrading Scanner Web UI Launcher

This script starts the FastAPI backend server and opens the web UI in your browser.
"""

import os
import sys
import time
import socket
import subprocess
import webbrowser
import threading
from pathlib import Path

# Add project to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / 'src'))

def check_port(port):
    """Check if a port is available."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(('127.0.0.1', port))
        sock.close()
        return True
    except OSError:
        return False

def find_available_port(start_port=8000, max_attempts=10):
    """Find an available port starting from start_port."""
    for port in range(start_port, start_port + max_attempts):
        if check_port(port):
            return port
    raise RuntimeError(f"No available ports found in range {start_port}-{start_port + max_attempts}")

def install_dependencies():
    """Install required dependencies if not present."""
    print("Checking dependencies...")
    
    # Check if fastapi is installed
    try:
        import fastapi
        import uvicorn
        import websockets
        print("✓ API dependencies installed")
    except ImportError:
        print("Installing API dependencies...")
        subprocess.run([
            sys.executable, "-m", "pip", "install", 
            "-r", str(project_root / "api" / "requirements.txt"),
            "-q"
        ], check=False)
        print("✓ API dependencies installed")
    
    # Check if scanner dependencies are installed
    try:
        import pandas
        import alpaca
        print("✓ Scanner dependencies installed")
    except ImportError:
        print("Note: Some scanner dependencies may be missing.")
        print("Run: pip install -e . to install all dependencies")

def start_server(port):
    """Start the FastAPI server."""
    import uvicorn
    from api.server import app
    
    print(f"\n🚀 Starting SwingTrading Scanner API on port {port}...")
    
    # Configure uvicorn
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="info",
        access_log=False  # Reduce noise
    )
    
    server = uvicorn.Server(config)
    server.run()

def open_browser(port, delay=2):
    """Open the web browser after a delay."""
    time.sleep(delay)
    url = f"http://localhost:{port}"
    print(f"\n🌐 Opening browser at {url}")
    webbrowser.open(url)

def main():
    """Main launcher function."""
    print("=" * 60)
    print("SwingTrading Scanner Web UI")
    print("=" * 60)
    
    # Check and install dependencies
    install_dependencies()
    
    # Find available port
    port = find_available_port()
    if port != 8000:
        print(f"ℹ️  Port 8000 is busy, using port {port}")
    
    # Start browser opener in background thread
    browser_thread = threading.Thread(target=open_browser, args=(port,))
    browser_thread.daemon = True
    browser_thread.start()
    
    # Start server (blocks)
    try:
        start_server(port)
    except KeyboardInterrupt:
        print("\n\n✋ Server stopped by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error starting server: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()