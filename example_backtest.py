#!/usr/bin/env python3
"""Simple example of how to run a backtest."""

import sys
import os
from datetime import datetime, timedelta
from pathlib import Path

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


def main():
    """Run a simple backtest example with improved scoring system."""
    print("SwingTrading Backtest Example - IMPROVED SCORING v2.1")
    print("=" * 55)
    
    # Define a small universe for testing
    universe = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA']
    
    # Define backtest period (last 6 months for more data)
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=180)).strftime('%Y-%m-%d')
    
    print(f"Universe: {universe}")
    print(f"Period: {start_date} to {end_date}")
    
    # Create backtest configuration
    config = BacktestConfig(
        start_date=start_date,
        end_date=end_date,
        universe=universe,
        min_score=35.0,           # Optimized minimum score based on backtest results
        max_positions=3,          # Maximum concurrent positions
        holding_period_days=10,   # Maximum holding period
        stop_loss_atr_mult=1.5,   # Stop loss at 1.5x ATR below entry
        take_profit_atr_mult=3.0, # Take profit at 3x ATR above entry
        commission_per_trade=1.0, # $1 commission per trade
        slippage_bps=5           # 5 basis points slippage
    )
    
    # Initialize data manager and backtest engine
    print("\nInitializing backtest engine...")
    data_manager = HistoricalDataManager()
    engine = BacktestEngine(data_manager)
    
    # Optional: Preload data for faster execution
    print("Preloading historical data...")
    data_manager.preload_universe_data(universe, start_date, end_date)
    
    # Run the backtest
    print("Running backtest...")
    results = engine.run_backtest(config)
    
    # Display basic results
    print("\n" + "=" * 40)
    print("BACKTEST RESULTS")
    print("=" * 40)
    print(f"Period: {results.start_date} to {results.end_date}")
    print(f"Total Trades: {results.total_trades}")
    print(f"Winning Trades: {results.winning_trades}")
    print(f"Losing Trades: {results.losing_trades}")
    print(f"Win Rate: {results.win_rate:.1%}")
    print(f"Average Return: {results.avg_return:.2f}%")
    print(f"Average Win: {results.avg_win:.2f}%")
    print(f"Average Loss: {results.avg_loss:.2f}%")
    print(f"Profit Factor: {results.profit_factor:.2f}")
    print(f"Total Return: {results.total_return:.2f}%")
    print(f"Max Drawdown: {results.max_drawdown:.2f}%")
    print(f"Sharpe Ratio: {results.sharpe_ratio:.2f}")
    
    # Show some individual trades
    if results.trades:
        print(f"\nSample Trades (first 5):")
        print("-" * 80)
        print(f"{'Symbol':<8} {'Entry':<12} {'Exit':<12} {'Days':<5} {'Return':<8} {'Reason':<8}")
        print("-" * 80)
        
        for trade in results.trades[:5]:
            print(f"{trade.symbol:<8} {trade.entry_date:<12} {trade.exit_date:<12} "
                  f"{trade.holding_days:<5} {trade.return_pct:>7.2f}% {trade.exit_reason:<8}")
    
    # Generate detailed performance report
    print(f"\nGenerating detailed performance report...")
    analyzer = PerformanceAnalyzer(results)
    report_paths = analyzer.generate_performance_report("example_backtest_results")
    
    print(f"\nDetailed reports saved to: example_backtest_results/")
    for report_type, path in report_paths.items():
        if isinstance(path, str):
            print(f"  {report_type}: {Path(path).name}")
    
    # Analyze performance by score ranges
    if results.trades:
        print(f"\nPerformance by Score Range:")
        print("-" * 50)
        
        score_ranges = [(30, 40), (40, 50), (50, 60), (60, 100)]
        
        for min_score, max_score in score_ranges:
            range_trades = [t for t in results.trades if min_score <= t.score < max_score]
            
            if range_trades:
                returns = [t.return_pct for t in range_trades]
                win_rate = sum(1 for r in returns if r > 0) / len(returns)
                avg_return = sum(returns) / len(returns)
                
                print(f"Score {min_score}-{max_score}: {len(range_trades)} trades, "
                      f"{win_rate:.1%} win rate, {avg_return:.2f}% avg return")
    
    print(f"\n✓ Backtest complete!")
    return results


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nBacktest interrupted by user")
    except Exception as e:
        print(f"\nError running backtest: {e}")
        import traceback
        traceback.print_exc()
