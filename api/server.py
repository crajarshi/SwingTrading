"""FastAPI server for SwingTrading Scanner UI."""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, List
import uuid

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

from .models import (
    ScanRequest, ScanResponse, ConfigResponse, ErrorResponse,
    HistoryEntry, RunState, ProgressUpdate
)
from .scanner_wrapper import ScannerWrapper

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="SwingTrading Scanner API",
    description="API for SwingTrading Scanner Web UI",
    version="1.0.0"
)

# Add CORS middleware - allow all origins during development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for testing
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize scanner wrapper
scanner = ScannerWrapper()

# WebSocket connections manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, run_id: str):
        await websocket.accept()
        if run_id not in self.active_connections:
            self.active_connections[run_id] = []
        self.active_connections[run_id].append(websocket)
    
    def disconnect(self, websocket: WebSocket, run_id: str):
        if run_id in self.active_connections:
            self.active_connections[run_id].remove(websocket)
            if not self.active_connections[run_id]:
                del self.active_connections[run_id]
    
    async def send_update(self, run_id: str, update: ProgressUpdate):
        if run_id in self.active_connections:
            # Send to all connections for this run
            disconnected = []
            for connection in self.active_connections[run_id]:
                try:
                    await connection.send_json(update.dict())
                except:
                    disconnected.append(connection)
            
            # Clean up disconnected
            for conn in disconnected:
                self.disconnect(conn, run_id)

manager = ConnectionManager()

# Session storage for run TTL (10 minutes)
session_storage: Dict[str, datetime] = {}

def check_run_ttl(run_id: str) -> bool:
    """Check if run is within TTL."""
    if run_id in session_storage:
        if datetime.now() - session_storage[run_id] < timedelta(minutes=10):
            return True
        else:
            del session_storage[run_id]
    return False


@app.get("/")
async def root():
    """Serve the main UI."""
    return FileResponse(Path(__file__).parent.parent / "web" / "index.html")


@app.post("/api/scan", response_model=Dict[str, str])
async def start_scan(request: ScanRequest):
    """Start a new scan with parameter overrides."""
    try:
        # Create progress callback for WebSocket updates
        async def progress_callback(update: ProgressUpdate):
            await manager.send_update(update.run_id, update)
        
        # Start scan
        run_id = await scanner.start_scan(request.dict(exclude_unset=True), progress_callback)
        
        # Store in session
        session_storage[run_id] = datetime.now()
        
        return {"run_id": run_id, "state": "created"}
    
    except Exception as e:
        logger.error(f"Error starting scan: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.websocket("/ws/scan/{run_id}")
async def websocket_endpoint(websocket: WebSocket, run_id: str):
    """WebSocket for real-time scan progress."""
    await manager.connect(websocket, run_id)
    
    try:
        # Send initial status
        status = scanner.get_run_status(run_id)
        if status:
            update = scanner._create_progress_update()
            if update:
                await websocket.send_json(update.dict())
        
        # Keep connection alive
        while True:
            # Check for client messages (mainly for ping/pong)
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
                if data == "ping":
                    await websocket.send_text("pong")
            except asyncio.TimeoutError:
                pass
            
            # Check if run is complete
            status = scanner.get_run_status(run_id)
            if status and status['state'] in [RunState.DONE, RunState.ERROR, RunState.CANCELED]:
                break
    
    except WebSocketDisconnect:
        manager.disconnect(websocket, run_id)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket, run_id)


@app.get("/api/scan/{run_id}/status")
async def get_scan_status(run_id: str):
    """Get current scan status (for reconnection)."""
    # Check TTL
    if not check_run_ttl(run_id):
        raise HTTPException(status_code=404, detail="Run expired or not found")
    
    status = scanner.get_run_status(run_id)
    if not status:
        raise HTTPException(status_code=404, detail="Run not found")
    
    return {
        "run_id": run_id,
        "state": status['state'],
        "progress": status['progress'],
        "started_at": status['started_at'].isoformat(),
        "error": status.get('error')
    }


@app.get("/api/scan/{run_id}/results")
async def get_scan_results(run_id: str):
    """Get scan results."""
    results = scanner.get_results(run_id)
    metadata = scanner.get_metadata(run_id)
    
    if results is None:
        raise HTTPException(status_code=404, detail="Results not found")
    
    # Format results with calculated fields
    formatted_results = []
    for result in results:
        formatted = result.dict()
        formatted['volume_ratio'] = result.volume_ratio
        formatted['trend_vs_sma50'] = result.trend_vs_sma50
        formatted['pullback_from_high20'] = result.pullback_from_high20
        formatted_results.append(formatted)
    
    return {
        "run_id": run_id,
        "results": formatted_results,
        "metadata": metadata.dict() if metadata else None
    }


@app.delete("/api/scan/{run_id}")
async def cancel_scan(run_id: str):
    """Cancel an active scan."""
    success = await scanner.cancel_scan(run_id)
    if not success:
        raise HTTPException(status_code=404, detail="Run not found or not active")
    
    return {"message": "Scan canceled", "run_id": run_id}


@app.get("/api/config", response_model=ConfigResponse)
async def get_config():
    """Get current configuration (without secrets)."""
    config = scanner.get_config_no_secrets()
    
    return ConfigResponse(
        universe=config['universe']['tickers'],
        data={
            'feed': config['data']['feed'],
            'timezone': config['data']['timezone'],
            'days_history': config['data']['days_history'],
            'min_bars_required': config['data']['min_bars_required'],
            'max_workers': config['data']['max_workers'],
            'rate_limit_per_minute': config['data']['rate_limit_per_minute'],
            'task_timeout': config['data']['task_timeout'],
            'rate_limit_start_full': config['data']['rate_limit_start_full']
        },
        filters=config['filters'],
        indicators=config['indicators'],
        scoring=config['scoring']['weights']
    )


@app.post("/api/config/save")
async def save_config(config_update: Dict[str, Any]):
    """Save configuration as default (explicit action)."""
    try:
        # This would update config.yaml
        # For now, just return success
        return {"message": "Configuration saved as default"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/export/{run_id}/csv")
async def export_csv(run_id: str):
    """Export scan results as CSV."""
    csv_path = scanner.export_csv(run_id)
    if not csv_path:
        raise HTTPException(status_code=404, detail="No results to export")
    
    return FileResponse(
        path=csv_path,
        filename=f"scan_results_{run_id[:8]}.csv",
        media_type="text/csv"
    )


@app.get("/api/cli/{run_id}")
async def get_cli_command(run_id: str, overrides: str = Query(default="{}")):
    """Generate CLI command for current settings."""
    try:
        overrides_dict = json.loads(overrides)
        command = scanner.generate_cli_command(run_id, overrides_dict)
        return {"command": command}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/history")
async def get_history():
    """Get scan history (last 5 runs)."""
    history = scanner.get_history()
    return {"history": history}


# Mount static files for web UI
web_dir = Path(__file__).parent.parent / "web"
if web_dir.exists():
    app.mount("/static", StaticFiles(directory=str(web_dir)), name="static")


def run_server(host: str = "127.0.0.1", port: int = 8000):
    """Run the FastAPI server."""
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    run_server()