#!/usr/bin/env python3
"""Comprehensive S&P 500 backtest with improved scoring system v2.1."""

import sys
import os
from datetime import datetime, timedelta
from pathlib import Path
import time

# Add project root to path
sys.path.append(str(Path(__file__).parent))

# Load environment variables from .env file
def load_env_file():
    """Load environment variables from .env file."""
    env_file = Path('.env')
    if env_file.exists():
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key] = value

load_env_file()

from backtesting import (
    BacktestEngine,
    BacktestConfig,
    HistoricalDataManager,
    PerformanceAnalyzer
)


def load_sp500_universe() -> list:
    """Load full S&P 500 universe from file."""
    try:
        with open('sp500_tickers.txt', 'r') as f:
            symbols = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        print(f"✓ Loaded {len(symbols)} S&P 500 symbols")
        return symbols
    except FileNotFoundError:
        print("✗ sp500_tickers.txt not found")
        return []


def run_sp500_backtest():
    """Run comprehensive S&P 500 backtest."""
    print("=" * 70)
    print("S&P 500 COMPREHENSIVE BACKTEST - SCORING v2.1")
    print("=" * 70)
    
    # Load full S&P 500 universe
    universe = load_sp500_universe()
    if not universe:
        print("Failed to load S&P 500 universe")
        return None
    
    print(f"Universe: {len(universe)} S&P 500 stocks")
    
    # Define backtest period (last 6 months for comprehensive analysis)
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=180)).strftime('%Y-%m-%d')
    
    print(f"Period: {start_date} to {end_date} (6 months)")
    print(f"Expected data points: {len(universe)} × 180 days = {len(universe) * 180:,} potential signals")
    
    # Create optimized configuration for large universe
    config = BacktestConfig(
        start_date=start_date,
        end_date=end_date,
        universe=universe,
        min_score=35.0,           # Optimized threshold from small backtest
        max_positions=20,         # Increased for larger universe
        holding_period_days=10,   # Standard swing trade period
        stop_loss_atr_mult=1.5,   # Conservative risk management
        take_profit_atr_mult=3.0, # 2:1 risk/reward
        commission_per_trade=1.0, # Realistic commission
        slippage_bps=5           # 5 basis points slippage
    )
    
    print(f"\nBacktest Configuration:")
    print(f"  Min Score: {config.min_score}")
    print(f"  Max Positions: {config.max_positions}")
    print(f"  Holding Period: {config.holding_period_days} days")
    print(f"  Stop Loss: {config.stop_loss_atr_mult}x ATR")
    print(f"  Take Profit: {config.take_profit_atr_mult}x ATR")
    
    # Initialize components
    print(f"\nInitializing backtest engine...")
    data_manager = HistoricalDataManager()
    engine = BacktestEngine(data_manager)
    
    # Preload data for faster execution
    print(f"\n🔄 Preloading historical data for {len(universe)} stocks...")
    print("This may take 10-15 minutes due to API rate limits...")
    
    start_time = time.time()
    data_manager.preload_universe_data(universe, start_date, end_date)
    preload_time = time.time() - start_time
    
    print(f"✓ Data preloading complete in {preload_time/60:.1f} minutes")
    
    # Run the comprehensive backtest
    print(f"\n🚀 Running S&P 500 backtest...")
    backtest_start = time.time()
    
    results = engine.run_backtest(config)
    
    backtest_time = time.time() - backtest_start
    total_time = time.time() - start_time
    
    print(f"\n✓ Backtest complete in {backtest_time/60:.1f} minutes")
    print(f"✓ Total execution time: {total_time/60:.1f} minutes")
    
    return results


def analyze_sp500_results(results):
    """Analyze and display S&P 500 backtest results."""
    print("\n" + "=" * 70)
    print("S&P 500 BACKTEST RESULTS - SCORING v2.1")
    print("=" * 70)
    
    # Basic performance metrics
    print(f"📊 PERFORMANCE SUMMARY")
    print(f"Period: {results.start_date} to {results.end_date}")
    print(f"Universe: {len(results.config.universe)} S&P 500 stocks")
    print(f"")
    print(f"🎯 TRADE STATISTICS")
    print(f"  Total Trades: {results.total_trades:,}")
    print(f"  Winning Trades: {results.winning_trades:,}")
    print(f"  Losing Trades: {results.losing_trades:,}")
    print(f"  Win Rate: {results.win_rate:.1%}")
    print(f"")
    print(f"💰 RETURN METRICS")
    print(f"  Average Return per Trade: {results.avg_return:.2f}%")
    print(f"  Average Win: {results.avg_win:.2f}%")
    print(f"  Average Loss: {results.avg_loss:.2f}%")
    print(f"  Total Return: {results.total_return:.2f}%")
    print(f"  Annualized Return: {results.total_return * 2:.2f}%")  # 6 months → annual
    print(f"")
    print(f"⚖️ RISK METRICS")
    print(f"  Profit Factor: {results.profit_factor:.2f}")
    print(f"  Max Drawdown: {results.max_drawdown:.2f}%")
    print(f"  Sharpe Ratio: {results.sharpe_ratio:.2f}")
    
    # Trade frequency analysis
    trading_days = 130  # Approximate trading days in 6 months
    trades_per_day = results.total_trades / trading_days
    print(f"")
    print(f"📈 ACTIVITY METRICS")
    print(f"  Trades per Day: {trades_per_day:.1f}")
    print(f"  Stocks Traded: {len(set(trade.symbol for trade in results.trades))}")
    print(f"  Average Positions: {results.total_trades / trading_days * results.config.holding_period_days:.1f}")
    
    # Show top performing trades
    if results.trades:
        sorted_trades = sorted(results.trades, key=lambda x: x.return_pct, reverse=True)
        
        print(f"\n🏆 TOP 10 WINNING TRADES")
        print(f"{'Symbol':<8} {'Entry':<12} {'Exit':<12} {'Days':<5} {'Return':<8} {'Score':<6} {'Reason'}")
        print("-" * 75)
        
        for trade in sorted_trades[:10]:
            print(f"{trade.symbol:<8} {trade.entry_date:<12} {trade.exit_date:<12} "
                  f"{trade.holding_days:<5} {trade.return_pct:>7.2f}% {trade.score:>5.1f} {trade.exit_reason}")
        
        print(f"\n💸 WORST 5 LOSING TRADES")
        print(f"{'Symbol':<8} {'Entry':<12} {'Exit':<12} {'Days':<5} {'Return':<8} {'Score':<6} {'Reason'}")
        print("-" * 75)
        
        for trade in sorted_trades[-5:]:
            print(f"{trade.symbol:<8} {trade.entry_date:<12} {trade.exit_date:<12} "
                  f"{trade.holding_days:<5} {trade.return_pct:>7.2f}% {trade.score:>5.1f} {trade.exit_reason}")
    
    # Generate detailed reports
    print(f"\n📋 Generating comprehensive performance reports...")
    analyzer = PerformanceAnalyzer(results)
    report_paths = analyzer.generate_performance_report("sp500_backtest_results")
    
    print(f"\n📁 Detailed reports saved to: sp500_backtest_results/")
    for report_type, path in report_paths.items():
        if isinstance(path, str):
            print(f"  📄 {report_type}: {Path(path).name}")
    
    return results


def compare_with_benchmark(results):
    """Compare results with S&P 500 benchmark."""
    print(f"\n📊 BENCHMARK COMPARISON")
    print("-" * 40)
    
    # Approximate S&P 500 return for comparison (you could fetch real data)
    # For 6 months, assume ~5-10% typical return
    sp500_6m_return = 8.0  # Placeholder - you could fetch real SPY data
    
    strategy_return = results.total_return
    excess_return = strategy_return - sp500_6m_return
    
    print(f"Strategy Return (6m): {strategy_return:.2f}%")
    print(f"S&P 500 Return (6m): {sp500_6m_return:.2f}% (estimated)")
    print(f"Excess Return: {excess_return:+.2f}%")
    print(f"")
    
    if excess_return > 0:
        print(f"✅ Strategy OUTPERFORMED S&P 500 by {excess_return:.2f}%")
    else:
        print(f"❌ Strategy UNDERPERFORMED S&P 500 by {abs(excess_return):.2f}%")
    
    # Risk-adjusted comparison
    strategy_sharpe = results.sharpe_ratio
    print(f"")
    print(f"Risk-Adjusted Performance:")
    print(f"  Strategy Sharpe Ratio: {strategy_sharpe:.2f}")
    print(f"  Max Drawdown: {results.max_drawdown:.2f}%")


def main():
    """Main function to run S&P 500 comprehensive backtest."""
    try:
        # Run the backtest
        results = run_sp500_backtest()
        
        if results is None:
            print("❌ Backtest failed")
            return
        
        # Analyze results
        analyze_sp500_results(results)
        
        # Compare with benchmark
        compare_with_benchmark(results)
        
        print(f"\n🎉 S&P 500 BACKTEST COMPLETE!")
        print(f"Check 'sp500_backtest_results' directory for detailed analysis.")
        
    except KeyboardInterrupt:
        print(f"\n⏹️ Backtest interrupted by user")
    except Exception as e:
        print(f"\n❌ Backtest failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
