# SwingTrading Scanner Web UI

## Overview

A lightweight, single-page web interface for the SwingTrading Scanner that provides real-time scanning and interactive paper trading with an intuitive control system.

## Features

### Core Functionality
- **Single Active Run**: One scan at a time with automatic cancellation of previous runs
- **Real-time Progress**: WebSocket-based updates showing tickers processed and partial results
- **Edited State Tracking**: "Apply & Re-Run" flow when parameters change
- **Auto-normalized Weights**: Automatic normalization when scoring weights don't sum to 100%
- **Session Persistence**: Reconnect to in-progress scans after page reload (10-minute TTL)
- **Consistent Formatting**: 2dp for prices/scores, 1dp for percentages/ratios

### User Interface
- **3-Panel Layout**: Controls sidebar, results table, detail drawer
- **Empty States**: Distinct screens for never-run, regime-blocked, and no-results
- **Guidance Strip**: Timeout handling with suggested settings
- **Keyboard Navigation**: Enter to run, ? for help, Esc to close drawers
- **Responsive Design**: Adapts to desktop, tablet, and mobile screens

## Quick Start

### Installation

1. Install API dependencies:
```bash
pip install -r api/requirements.txt
```

2. Ensure scanner dependencies are installed:
```bash
pip install -e .
```

### Running the UI (v2 local server)

```bash
# Install dependencies into the repo venv (once)
venv/bin/python -m pip install --upgrade pip
venv/bin/python -m pip install numpy scipy

# Start the v2 server and open the page
venv/bin/python working_server_v2.py
# UI: http://localhost:8002/working.html
```

## Usage Guide

### Basic Workflow

1. **Set Parameters**: Adjust filters and settings in the controls panel
2. **Run Scan**: Click "Run Scan" or press Enter
3. **Monitor Progress**: Watch real-time progress bar showing N/Total tickers
4. **Review Results**: Click table rows to see detailed analysis
5. **Export**: Use Export button for CSV or Copy CLI for command-line equivalent

### Controls

#### Quick Controls (Always Visible)
- **Tickers**: Comma-separated list (preserves order, case-insensitive deduplication)
- **Data Feed**: IEX (free) or SIP (paid subscription)
- **Regime Bypass**: Override SPY RSI market regime filter
- **Sort By**: Score, RSI, or Gap percentage
- **Presets**: Conservative, Balanced (default), Aggressive

#### Advanced Settings (Collapsible)
- **Filters**: Min price, max gap%, ATR ratio, dollar volume
- **Indicators**: Periods for ATR, RSI, SMA short/long
- **Scoring Weights**: Auto-normalized to 100%
- **Performance**: Workers, rate limit, timeout settings

### Edited State Flow

When you change any control:
1. Button changes to "Apply & Re-Run" (orange)
2. Results table dims with "Results reflect previous settings" overlay
3. Running the scan clears the edited state

### Results Table

- **Sortable Columns**: Click headers to sort
- **Visual Indicators**:
  - Score progress bar in cell
  - RSI dots for oversold (<30) and overbought (>70)
- **Row Click**: Opens detail drawer with full analysis

### Detail Drawer

Shows for selected symbol:
- Price and session date
- Technical indicators (ATR, RSI, SMAs)
- Score breakdown with component contributions
- Liquidity metrics
- Copy symbol button

## Keyboard Shortcuts

- **Enter**: Run scan (from any input except textarea)
- **?**: Open help overlay
- **Esc**: Close drawer or overlay
- **Tab**: Navigate through controls

## Error Handling

### Error Codes
- **2 (Config)**: Invalid configuration - check settings
- **3 (Network)**: Rate limited - reduce workers or increase timeout
- **4 (Data)**: Insufficient data - increase history or lower min bars

### Timeout Handling
When some tickers timeout:
- Partial results are shown
- Guidance strip appears with suggestions
- "Re-run with suggested settings" applies optimized parameters

## Persistence & Recovery

### Local Storage
- Control settings persist across sessions
- "Reset to Defaults" restores Balanced preset

### Session Storage
- Active run ID stored for reconnection
- 10-minute TTL for abandoned runs
- Automatic resume on page reload

### WebSocket Reconnection
1. Attempts reconnection 3 times on disconnect
2. Falls back to 1-second polling if WebSocket fails
3. Maintains progress state during reconnection

## Performance

### Targets
- First paint: <1.0s
- Progress updates: 250ms throttled
- Virtual scrolling: Activates >300 rows
- WebSocket timeout: 3s before polling fallback

### Optimizations
- Debounced control changes (100ms)
- Throttled progress updates (250ms)
- Lazy-loaded detail drawer content
- Minimal CSS with CSS Grid/Flexbox

## Security

- **No Secrets in API**: Credentials never sent to frontend
- **Runtime Overrides Only**: Parameters don't auto-save to config.yaml
- **Run-scoped Exports**: Export endpoints use run IDs only
- **CORS Protection**: Limited to localhost origins

## Troubleshooting

### Common Issues

**Port Already in Use**
- The launcher automatically finds an available port
- Check console output for actual port used

**WebSocket Connection Failed**
- Verify firewall allows localhost WebSocket connections
- Check browser console for specific errors
- UI automatically falls back to polling

**Results Not Loading**
- Ensure scan completed successfully
- Check browser console for API errors
- Verify backend server is running

**Edited State Stuck**
- Refresh page to clear state
- Check localStorage for corrupted data
- Use "Reset to Defaults" to clear settings

### Debug Mode

Open browser console and check:
- Network tab for API calls
- Console for error messages
- Application tab for localStorage/sessionStorage

## Architecture

### Frontend
- **Vanilla JavaScript**: No framework dependencies
- **Single Page**: All functionality in one page
- **Component Structure**: Modular but combined for simplicity

### Backend
- **FastAPI**: Async Python web framework
- **WebSocket**: Real-time bidirectional communication
- **Scanner Wrapper**: Manages single active run

### Data Flow
1. UI sends scan request with parameter overrides
2. Backend starts scan, returns run ID
3. WebSocket streams progress updates
4. UI displays results on completion
5. Session persists for reconnection

## Development

### File Structure
```
SwingTrading/
├── api/
│   ├── server.py          # FastAPI application
│   ├── scanner_wrapper.py # Scanner integration
│   └── models.py          # Pydantic models
├── web/
│   ├── index.html         # Single page UI
│   ├── app.js             # Application logic
│   └── styles.css         # Minimal styling
└── run_ui.py              # Launcher script
```

### Adding Features

1. **New Control**: Add to HTML, handle in getControls()
2. **New API Endpoint**: Add to server.py with Pydantic model
3. **New Display Mode**: Extend displayResults() function
4. **New Keyboard Shortcut**: Add to keydown event listener

## Browser Support

- Chrome 90+
- Firefox 88+
- Safari 14+
- Edge 90+

No IE11 support.

## Known Limitations

- Single user/session (not multi-tenant)
- 10-minute TTL for abandoned runs
- Maximum 1000 rows before performance impact
- WebSocket required for real-time updates (polling fallback available)

## Support

For issues or questions:
- Check browser console for errors
- Review this documentation
- Check main README.md for scanner configuration
- Report issues at: https://github.com/crajarshi/SwingTrading/issues
### Paper Trading (Interactive)

- Click “Scan for Candidates” to build the candidate list
- For each row, edit Side, Entry (blank = market), Stop, Target, Shares, and Risk/Share
- Select desired rows and click “Place Selected Orders” to submit day bracket orders

Server endpoints used:
- `POST /api/paper/scan` → Create scan run for candidates
- `GET  /api/paper/scan/{run_id}/status` → Poll status
- `GET  /api/paper/positions` → Current positions
- `POST /api/paper/report` → Generate EOD report
- `POST /api/paper/place-custom` → Place selected custom bracket orders

Scoring v2 (P0) in UI details:
- Components shown: Pullback, Trend, RSI Percentile, Dollar‑Volume Uplift
- Values are symbol‑relative percentiles with 3‑day EMA smoothing
