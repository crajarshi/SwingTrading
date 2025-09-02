# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Core Commands

### Running the Application

```bash
# Run the web server (main application)
python3 working_server_v2.py
# Server runs on http://localhost:8000

# Quick test of scoring system
python3 test_v2_quick.py
```

### Testing

```bash
# Run determinism tests
python3 scoring_v2/tests/test_determinism.py

# Run no-leak tests  
python3 scoring_v2/tests/test_no_leak.py
```

### Environment Setup

```bash
# Python 3.10+ required (currently using 3.13.2)
# Copy and configure environment variables
cp .env.example .env
# Edit .env with Alpaca API credentials
```

## Architecture Overview

### High-Level Structure

The SwingTrading system is a stock scanner that identifies swing trading opportunities using technical analysis and intelligent scoring.

**Key Components:**

1. **Web Server** (`working_server_v2.py`): HTTP server providing REST API endpoints for scanning stocks and retrieving scores. Handles real-time data fetching from Alpaca Markets API.

2. **Scoring Engine** (`scoring_v2/`): Modular scoring system that:
   - Calculates technical indicators (RSI, ATR, SMA)
   - Applies multi-stage filtering gates
   - Computes percentile-based scores
   - Provides deterministic, cacheable results

3. **Caching Layer** (`scoring_v2/cache.py`): SQLite-based cache system that stores historical data and computed scores to minimize API calls and improve performance.

### Data Flow

1. **Data Acquisition**: Alpaca API → Cache → Scoring Engine
2. **Processing Pipeline**: Raw bars → Indicators → Gates → Percentiles → Final Score
3. **Client Interface**: Web UI requests → Server API → JSON responses

### Key Design Principles

- **Determinism**: Same inputs always produce same outputs (critical for testing/debugging)
- **No Look-Ahead Bias**: Indicators computed without future data
- **Modular Architecture**: Clear separation between data fetching, caching, scoring, and serving
- **Production-Ready**: Includes telemetry, error handling, and rate limiting

### API Endpoints

- `GET /api/scan` - Scan multiple symbols
- `GET /api/score/{symbol}` - Get score for single symbol
- `GET /api/telemetry` - Get system metrics
- `GET /api/cache/clear` - Clear cache

### Critical Files

- `working_server_v2.py`: Main server implementation
- `scoring_v2/scoring.py`: Core scoring logic and orchestration
- `scoring_v2/indicators.py`: Technical indicator calculations
- `scoring_v2/gates.py`: Filtering logic
- `scoring_v2/percentiles.py`: Percentile mapping for score normalization
- `web/index.html`: Frontend UI