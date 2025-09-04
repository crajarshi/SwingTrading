#!/usr/bin/env python3
"""Run backtests to evaluate scoring system performance."""

import sys
import yaml
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent))

from backtesting import (
    BacktestEngine,
    BacktestConfig, 
    HistoricalDataManager,
    PerformanceAnalyzer,
    optimize_scoring_weights
)


def load_universe_from_file(file_path: str) -> list:
    """Load universe of symbols from file."""
    try:
        with open(file_path, 'r') as f:
            symbols = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        return symbols
    except FileNotFoundError:
        print(f"Universe file not found: {file_path}")
        return []


def run_simple_backtest():
    """Run a simple backtest with default parameters."""
    print("=== Simple Backtest ===")
    
    # Load universe
    universe = load_universe_from_file('sp500_tickers.txt')
    if not universe:
        print("Using default universe")
        universe = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NVDA', 'JPM', 'JNJ', 'V']
    
    # Limit to smaller universe for testing
    universe = universe[:20]  # First 20 symbols
    
    # Define backtest period (last 6 months)
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=180)).strftime('%Y-%m-%d')
    
    print(f"Universe: {len(universe)} symbols")
    print(f"Period: {start_date} to {end_date}")
    
    # Create configuration
    config = BacktestConfig(
        start_date=start_date,
        end_date=end_date,
        universe=universe,
        min_score=30.0,
        max_positions=5,  # Conservative for testing
        holding_period_days=10,
        stop_loss_atr_mult=1.5,
        take_profit_atr_mult=3.0
    )
    
    # Initialize components
    data_manager = HistoricalDataManager()
    engine = BacktestEngine(data_manager)
    
    # Preload data to speed up backtest
    print("Preloading historical data...")
    data_manager.preload_universe_data(universe, start_date, end_date)
    
    # Run backtest
    print("Running backtest...")
    results = engine.run_backtest(config)
    
    # Analyze results
    analyzer = PerformanceAnalyzer(results)
    report_paths = analyzer.generate_performance_report("backtest_results")
    
    print("\n=== Results Summary ===")
    print(f"Total Trades: {results.total_trades}")
    print(f"Win Rate: {results.win_rate:.1%}")
    print(f"Average Return: {results.avg_return:.2f}%")
    print(f"Total Return: {results.total_return:.2f}%")
    print(f"Max Drawdown: {results.max_drawdown:.2f}%")
    print(f"Sharpe Ratio: {results.sharpe_ratio:.2f}")
    
    print(f"\nReports saved to: backtest_results/")
    for report_type, path in report_paths.items():
        if isinstance(path, str):
            print(f"  {report_type}: {path}")
    
    return results


def run_score_analysis():
    """Run analysis of different score thresholds."""
    print("\n=== Score Threshold Analysis ===")
    
    # Load smaller universe for faster testing
    universe = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA']
    
    # Test period
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')
    
    # Test different score thresholds
    score_thresholds = [20, 30, 40, 50, 60]
    
    data_manager = HistoricalDataManager()
    engine = BacktestEngine(data_manager)
    
    print("Preloading data...")
    data_manager.preload_universe_data(universe, start_date, end_date)
    
    results_by_threshold = {}
    
    for min_score in score_thresholds:
        print(f"\nTesting min_score = {min_score}")
        
        config = BacktestConfig(
            start_date=start_date,
            end_date=end_date,
            universe=universe,
            min_score=min_score,
            max_positions=3,
            holding_period_days=10
        )
        
        results = engine.run_backtest(config)
        results_by_threshold[min_score] = results
        
        print(f"  Trades: {results.total_trades}, Win Rate: {results.win_rate:.1%}, Avg Return: {results.avg_return:.2f}%")
    
    # Summary comparison
    print("\n=== Score Threshold Comparison ===")
    print("Threshold | Trades | Win Rate | Avg Return | Total Return")
    print("-" * 55)
    
    for threshold, results in results_by_threshold.items():
        print(f"{threshold:8d} | {results.total_trades:6d} | {results.win_rate:8.1%} | {results.avg_return:10.2f}% | {results.total_return:11.2f}%")
    
    return results_by_threshold


def run_weight_optimization():
    """Run weight optimization analysis."""
    print("\n=== Weight Optimization ===")
    
    # Small universe for faster optimization
    universe = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA']
    
    # Optimization period (last 3 months)
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')
    
    print(f"Optimizing weights for period: {start_date} to {end_date}")
    print(f"Universe: {universe}")
    
    try:
        # Run optimization
        optimization_results = optimize_scoring_weights(
            symbols=universe,
            start_date=start_date,
            end_date=end_date,
            objective='sharpe_ratio'
        )
        
        print("\n=== Optimization Results ===")
        print(f"Method: {optimization_results['method']}")
        print(f"Objective: {optimization_results['objective']}")
        
        weights = optimization_results['optimal_weights']
        print(f"\nOptimal Weights:")
        print(f"  Pullback: {weights['pullback']:.1%}")
        print(f"  Trend: {weights['trend']:.1%}")
        print(f"  RSI: {weights['rsi']:.1%}")
        print(f"  Volume: {weights['volume']:.1%}")
        
        performance = optimization_results['performance']
        print(f"\nPerformance with Optimal Weights:")
        print(f"  Total Trades: {performance['total_trades']}")
        print(f"  Win Rate: {performance['win_rate']:.1%}")
        print(f"  Average Return: {performance['avg_return']:.2f}%")
        print(f"  Sharpe Ratio: {performance['sharpe_ratio']:.2f}")
        
        return optimization_results
        
    except Exception as e:
        print(f"Optimization failed: {e}")
        return None


def main():
    """Main function to run different backtest analyses."""
    print("SwingTrading Backtest Suite")
    print("=" * 40)
    
    # Check for required files
    if not Path('sp500_tickers.txt').exists():
        print("Warning: sp500_tickers.txt not found, using default symbols")
    
    # Run different analyses
    try:
        # 1. Simple backtest
        simple_results = run_simple_backtest()
        
        # 2. Score threshold analysis
        threshold_results = run_score_analysis()
        
        # 3. Weight optimization (optional - can be slow)
        print("\nRun weight optimization? (y/n): ", end="")
        if input().lower().startswith('y'):
            optimization_results = run_weight_optimization()
        
        print("\n=== Backtest Suite Complete ===")
        print("Check the 'backtest_results' directory for detailed reports.")
        
    except KeyboardInterrupt:
        print("\nBacktest interrupted by user")
    except Exception as e:
        print(f"\nBacktest failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
