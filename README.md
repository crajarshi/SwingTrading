# SwingTrading Scanner

A production-ready market scanner for identifying swing trading opportunities using technical analysis and intelligent filtering.

## Features

- 🔍 **Smart Filtering**: Multi-stage filter pipeline for quality stock selection
- 📊 **Technical Analysis**: RSI, ATR, SMA, and gap analysis
- 🎯 **Intelligent Scoring**: Weighted composite scoring system
- 💾 **Efficient Caching**: Per-symbol Parquet cache with atomic writes
- 🚦 **Rate Limiting**: Global token bucket to respect API limits
- 📈 **Market Regime Filter**: SPY RSI-based market condition check
- 🔄 **Session Detection**: Pure data-driven trading session detection
- 📋 **Export Options**: CSV results and JSON metadata

## Requirements

- Python ≥ 3.10
- Alpaca Markets account (free or paid)
- Internet connection for market data

## Installation

### From Source (Recommended)

```bash
# Clone the repository
git clone https://github.com/yourusername/SwingTrading.git
cd SwingTrading

# Install the package
pip install .

# Or install in development mode
pip install -e ".[dev]"
```

### Using pipx (User Installation)

```bash
pipx install .
```

## Quick Start

### 1. Set Up Credentials

```bash
# Copy the example environment file
cp .env.example .env

# Edit .env with your Alpaca API credentials
# Get your API keys from: https://app.alpaca.markets/
```

### 2. Run Your First Scan

**Important**: Run after market close (5pm ET) to avoid partial-day data issues.

```bash
# Basic scan with default configuration
swing-scan

# Scan a single ticker
swing-scan --ticker AAPL

# Run with debug output
swing-scan --debug
```

## Configuration

The scanner uses `config.yaml` for all settings. Key sections include:

### Universe
- **tickers**: List of stocks to scan
- Automatically uppercased and deduplicated

### Data Settings
- **feed**: `iex` (free) or `sip` (paid subscription)
- **timezone**: Market timezone (default: America/New_York)
- **rate_limit_per_minute**: API request limit (default: 190)
- **task_timeout**: Per-ticker timeout in seconds

### Filters
- **min_price**: Minimum stock price
- **min_dollar_volume_10d_avg**: Minimum liquidity ($5M default)
- **min_atr_ratio**: Minimum ATR/price ratio (volatility filter)
- **max_gap_percent**: Maximum overnight gap
- **leveraged_etf_patterns**: Patterns to exclude

### Scoring Weights
Components (should sum to ~1.0):
- **pullback_proximity**: Distance from 20-day high (30%)
- **trend_strength**: Price above SMA(50) (25%)
- **rsi_headroom**: Room to rise from current RSI (25%)
- **volume_ratio**: Current vs average volume (20%)

## Usage Examples

### Basic Operations

```bash
# Standard scan
swing-scan

# Disable progress bar
swing-scan --no-progress

# Bypass market regime filter
swing-scan --ignore-regime

# Clear cache before scanning
swing-scan --clear-cache

# Validate configuration only
swing-scan --dry-run
```

### Advanced Usage

```bash
# Custom configuration file
swing-scan --config-file custom_config.yaml

# Single ticker with debug output
swing-scan --ticker NVDA --debug

# Scan with regime bypass and no progress
swing-scan --ignore-regime --no-progress
```

## Understanding the Output

### Console Display
- Top 20 results sorted by score
- Shows price, score, RSI, gap%, and volume ratio
- Formatted for readability

### CSV Export (`scan_results.csv`)
- **Index**: `session_date` in configured timezone
- **Columns**: symbol, close, volume, dollar_volume_10d_avg, atr20, rsi14, gap_percent, score
- **Precision**: Full numeric precision (no rounding)

### Metadata (`scan_metadata.json`)
- Scan timestamp
- Last complete session date
- Configuration used
- Market regime status

## Important Notes

### Timing
- **Run after 5pm ET** to ensure complete daily bars
- Scanner includes partial-day guard to exclude incomplete sessions
- All dates are market session dates in configured timezone

### Data Feeds
- **IEX (free)**: May have gaps and lower volume data
- **SIP (paid)**: Complete market data
- Results will differ between feeds - use consistent feed for comparisons

### Rate Limiting
- Token bucket starts empty by default (safer)
- SPY regime check consumes 1-2 API requests
- Cached data doesn't consume API requests
- Initial requests may be throttled

### Indicator Calculations
- **RSI and ATR use simple rolling means** (not Wilder's smoothing)
- **Gaps measured on adjusted prices** (handles splits/dividends)
- **Volume averages exclude current bar** (no look-ahead bias)

## Timeout Behavior

- **Per-ticker timeout**: Each ticker has `task_timeout` seconds to complete
- **On timeout**: That ticker is rejected and marked as 'timeout' in stats
- **Scan continues**: Other tickers are not affected
- Configure in `config.yaml` under `data.task_timeout`

## Exit Codes

| Code | Meaning | Common Causes |
|------|---------|---------------|
| 0 | Success | Normal completion |
| 1 | General error | Uncaught exception |
| 2 | Configuration error | Invalid config.yaml, missing credentials |
| 3 | Network/API error | Rate limit, connection issues, timeouts |
| 4 | Insufficient data | No bars available, symbol not found |

## Troubleshooting

### Rate Limiting Issues
- **Symptom**: Exit code 3, "429" errors
- **Solution**: 
  - Reduce `max_workers` in config
  - Ensure `rate_limit_per_minute` < 200
  - Set `rate_limit_start_full: false`

### Missing Data
- **Symptom**: "No data for ticker" messages
- **Solution**:
  - Verify ticker symbol is correct
  - Check if ticker is actively traded
  - IEX feed may have limited coverage
  - Increase `days_history` if needed

### Timeout Issues
- **Symptom**: Many tickers marked as 'timeout'
- **Solution**: 
  - Increase `task_timeout` in config
  - Reduce `max_workers` for better throughput
  - Check network connection

### Different Results Between Runs
- **Issue**: Results vary unexpectedly
- **Solution**:
  - Use same `feed` setting consistently
  - Run at same time each day
  - Clear cache if data seems stale

## Development

### Running Tests

```bash
# Install development dependencies
pip install -e ".[dev]"

# Run test suite
pytest tests/

# Run with coverage
pytest tests/ --cov=swingtrading
```

### Code Quality

```bash
# Format code
black src/

# Type checking
mypy src/
```

### Project Structure

```
SwingTrading/
├── src/swingtrading/     # Main package
│   ├── main.py          # CLI entry point
│   ├── scanner.py       # Core scanning logic
│   ├── data_provider.py # Alpaca integration
│   ├── cache_manager.py # Cache handling
│   └── ...
├── tests/               # Test suite
├── config.yaml         # Configuration
└── .env               # API credentials (not in git)
```

## Performance Tips

1. **Use caching**: Cached data loads instantly
2. **Optimize workers**: Start with 10, adjust based on throughput
3. **Filter early**: Strict filters reduce processing time
4. **Run consistently**: Same time daily for comparable results

## License

MIT License - See LICENSE file for details

## Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

## Support

For issues or questions:
- Open an issue on GitHub
- Check existing issues for solutions
- Include config and error messages in reports

## Disclaimer

This tool is for educational and research purposes only. Always do your own research and consult with a qualified financial advisor before making investment decisions. Past performance does not guarantee future results.