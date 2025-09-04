# SwingTrading Backtesting Framework

This backtesting framework allows you to evaluate and optimize your scoring system using historical data.

## Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements_backtest.txt
```

### 2. Set Up Alpaca Credentials
```bash
export ALPACA_API_KEY="your_key_here"
export ALPACA_SECRET_KEY="your_secret_here"
```

### 3. Run Simple Example
```bash
python example_backtest.py
```

This will:
- Test on AAPL, MSFT, GOOGL, AMZN, TSLA
- Use last 3 months of data
- Generate performance reports in `example_backtest_results/`

## How to Get Backtesting Data

### Method 1: Use Your Existing Alpaca Account
The backtesting system uses the same Alpaca API you're already using for live trading. It will:
- Fetch historical data automatically
- Cache data locally to avoid repeated API calls
- Work with your existing credentials

### Method 2: Run Full Backtest Suite
```bash
python run_backtest.py
```

This comprehensive suite will:
- Test different score thresholds
- Analyze performance by score ranges
- Optionally optimize component weights
- Generate detailed reports

## Understanding the Results

### Key Metrics Explained

**Win Rate**: Percentage of profitable trades
- Good: >60%
- Excellent: >70%

**Average Return**: Mean return per trade
- Target: >2% for swing trades

**Profit Factor**: Gross profit / Gross loss
- Good: >1.5
- Excellent: >2.0

**Sharpe Ratio**: Risk-adjusted returns
- Good: >1.0
- Excellent: >1.5

**Max Drawdown**: Largest peak-to-trough decline
- Target: <15% for swing trading

### Score Performance Analysis

The backtest will show you how different score ranges perform:

```
Score 30-40: 15 trades, 60% win rate, 1.8% avg return
Score 40-50: 22 trades, 68% win rate, 2.4% avg return  
Score 50-60: 18 trades, 72% win rate, 3.1% avg return
Score 60+:   8 trades, 75% win rate, 4.2% avg return
```

This helps you:
- **Adjust minimum score threshold** (raise it if low scores perform poorly)
- **Understand score effectiveness** (higher scores should perform better)
- **Optimize position sizing** (allocate more capital to higher scores)

## Improving Your Scoring System

### 1. Analyze Score Distribution
Look at the score analysis report to see:
- Which score ranges have the best win rates
- Whether higher scores actually perform better
- If your minimum score threshold is optimal

### 2. Examine Exit Reasons
Check what percentage of trades exit via:
- **Time**: Held for maximum period (may indicate weak signals)
- **Stop**: Hit stop loss (risk management working)
- **Target**: Hit take profit (strong signals)

### 3. Study Time Patterns
Monthly performance analysis shows:
- Seasonal effects (some months may be better)
- Market regime changes
- Consistency over time

### 4. Optimize Component Weights
Run weight optimization to find better combinations:
```bash
# In run_backtest.py, answer 'y' when prompted
Run weight optimization? (y/n): y
```

This will test different weight combinations and suggest optimal allocations.

## Customizing Backtests

### Modify Backtest Parameters

Edit the `BacktestConfig` in your script:

```python
config = BacktestConfig(
    start_date='2023-01-01',
    end_date='2024-01-01', 
    universe=['AAPL', 'MSFT', 'GOOGL'],  # Your symbols
    min_score=35.0,           # Raise for higher quality
    max_positions=8,          # More concurrent positions
    holding_period_days=15,   # Longer holding period
    stop_loss_atr_mult=2.0,   # Wider stops
    take_profit_atr_mult=4.0  # Higher targets
)
```

### Test Different Universes

```python
# Technology stocks
tech_universe = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA']

# Large cap value
value_universe = ['JPM', 'JNJ', 'PG', 'KO', 'WMT', 'HD', 'VZ']

# Full S&P 500 (slower but comprehensive)
with open('sp500_tickers.txt', 'r') as f:
    sp500_universe = [line.strip() for line in f]
```

## Interpreting Results for Scoring Improvements

### If Win Rate is Low (<50%)
- **Increase minimum score threshold**
- **Tighten entry gates** (stricter ATR, pullback ranges)
- **Add momentum filters** (require recent price strength)

### If Average Return is Low (<1.5%)
- **Optimize component weights** (emphasize best predictors)
- **Improve trend detection** (add multiple timeframes)
- **Enhance volume analysis** (require institutional interest)

### If Drawdowns are High (>20%)
- **Implement position sizing** based on score confidence
- **Add market regime filters** (avoid bear markets)
- **Tighten stop losses** or add trailing stops

### If Few Trades are Generated
- **Lower minimum score threshold**
- **Expand universe** (more symbols)
- **Relax entry gates** (wider ATR ranges)

## Advanced Analysis

### Walk-Forward Optimization
Test how well optimized weights perform out-of-sample:

```python
from backtesting import walk_forward_analysis

results = walk_forward_analysis(
    symbols=universe,
    start_date='2022-01-01',
    end_date='2024-01-01',
    train_months=12,  # Optimize on 12 months
    test_months=3     # Test on next 3 months
)
```

### Market Regime Analysis
Compare performance in different market conditions:
- Bull markets (SPY trending up)
- Bear markets (SPY trending down)  
- High volatility (VIX > 25)
- Low volatility (VIX < 15)

## Files Generated

After running backtests, you'll find:

```
backtest_results/
├── performance_summary.md     # Overall metrics
├── score_analysis.md         # Performance by score range
├── time_analysis.md          # Monthly/seasonal patterns
├── drawdown_analysis.md      # Risk analysis
└── backtest_results.json     # Raw data for further analysis
```

## Next Steps

1. **Start with example_backtest.py** to understand the basics
2. **Run run_backtest.py** for comprehensive analysis
3. **Analyze the generated reports** to identify improvements
4. **Modify your scoring weights** based on findings
5. **Re-run backtests** to validate improvements
6. **Implement changes** in your live scoring system

## Troubleshooting

**"No historical data"**: Check Alpaca credentials and internet connection
**"Insufficient bars"**: Reduce the `days` parameter or use more liquid stocks
**"No trades generated"**: Lower the `min_score` threshold or expand universe
**Slow performance**: Use smaller universe or enable data caching

## Important Notes

- **Past performance doesn't guarantee future results**
- **Backtest on out-of-sample data** to avoid overfitting
- **Consider transaction costs** and slippage in real trading
- **Market conditions change** - regularly re-evaluate your system
- **Start with paper trading** before risking real capital
