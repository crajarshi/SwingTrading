# SwingTrading Scanner Results Guide

## Understanding Your Scan Results

### Overview
The scanner identifies potential swing trading opportunities by analyzing technical indicators and market conditions. Higher scores indicate stocks that better match the swing trading criteria.

## Key Metrics Explained

### 1. **Score (0-100)**
The overall ranking that combines multiple factors:
- **20+**: Excellent swing trade setup
- **10-20**: Good potential opportunity  
- **5-10**: Moderate interest
- **<5**: Weak setup

Score components (from config.yaml):
- **30%** - Pullback Proximity (distance from 20-day high)
- **25%** - Trend Strength (price above SMA50)
- **25%** - RSI Headroom (potential to rise)
- **20%** - Volume Ratio (current vs average)

### 2. **RSI (Relative Strength Index)**
Momentum indicator ranging from 0-100:
- **<30**: Oversold (potential bounce)
- **30-50**: Neutral to slightly bearish
- **50-70**: Neutral to slightly bullish
- **70+**: Overbought (potential pullback)

**Sweet spot for swing trading**: 35-65 (room to move up without being overbought)

### 3. **Gap% (Gap Percentage)**
The overnight gap from previous close:
- **<2%**: Normal movement
- **2-5%**: Moderate gap (increased volatility)
- **5-15%**: Large gap (high volatility)
- **>15%**: Extreme gap (filtered out by scanner)

### 4. **Volume Ratio**
Current volume compared to 10-day average:
- **<0.5x**: Very low volume (less liquid)
- **0.5-1.0x**: Below average volume
- **1.0-2.0x**: Normal to elevated volume
- **>2.0x**: High volume (increased interest)

## Reading Today's Results

### Top Picks Analysis

**WMT (Score: 20.37)**
- RSI 49.2: Perfect neutral position with upside room
- Gap 3.2%: Moderate volatility showing active trading
- Volume 3.3x: Strong investor interest
- **Interpretation**: Excellent setup - neutral RSI with high volume suggests building momentum

**MSFT (Score: 15.51)**
- RSI 34.6: Oversold territory, potential bounce
- Gap 0.3%: Stable, no extreme moves
- Volume 1.0x: Normal trading activity
- **Interpretation**: Good recovery candidate from oversold levels

**NVDA (Score: 11.40)**
- RSI 52.3: Neutral, balanced position
- Gap 0.3%: Stable movement
- Volume 1.0x: Normal activity
- **Interpretation**: Balanced setup with room to move either direction

## Filter Criteria

The scanner automatically filters out:
- Stocks under $5 (penny stock filter)
- Stocks with <$5M daily dollar volume (liquidity filter)
- Stocks with ATR ratio <0.01 (low volatility filter)
- Leveraged ETFs (3x/2x products)
- Stocks with gaps >15% (extreme volatility)

## How to Use These Results

### For Entry Decisions:
1. **High Score + Low-Mid RSI (30-50)**: Strong buy setup
2. **High Score + High Volume Ratio**: Momentum building
3. **Moderate Score + RSI <40**: Potential oversold bounce

### For Risk Management:
- **ATR (Average True Range)**: Use for stop-loss sizing
- **Gap%**: Higher gaps = higher volatility = adjust position size
- **Volume**: Ensure sufficient liquidity for your position size

### Best Practices:
1. Don't rely solely on the score - confirm with chart patterns
2. Check news for high gap% stocks
3. Higher volume ratios often precede moves
4. RSI extremes (<30 or >70) suggest reversals

## Output Files

### scan_results.csv
Contains all stocks that passed filters with:
- symbol, close, volume, dollar_volume_10d_avg
- Technical indicators: atr20, rsi14, gap_percent
- Final score

### scan_metadata.json
Contains scan configuration and summary:
- Timestamp and configuration used
- Market regime status
- Filter statistics
- Score distribution

## Market Regime Check

The scanner checks SPY RSI before running:
- **SPY RSI >30**: Market active, scan proceeds
- **SPY RSI <30**: Market oversold, scan skipped (bear market protection)

Current regime: ACTIVE (SPY RSI: 66.5)

## Suggested Workflow

1. **Review top 5 by score** - Best overall setups
2. **Check RSI <40 stocks** - Oversold bounces
3. **Look for volume spikes** - Unusual activity
4. **Verify with charts** - Confirm technical patterns
5. **Check news** - Understand gap movements
6. **Set alerts** - Monitor entry points

## Customization

Edit `config.yaml` to adjust:
- Universe (add/remove tickers)
- Score weights (emphasize different factors)
- Filter thresholds (price, volume, volatility)
- Technical indicator periods

## Questions to Ask

When reviewing results:
- Why is this stock scoring high/low?
- Is the volume ratio confirming the setup?
- Is RSI at an extreme or neutral?
- What's driving any gaps?
- Does the score align with the chart pattern?

---

*Remember: This scanner identifies potential opportunities but always do additional research, check charts, and manage risk appropriately.*