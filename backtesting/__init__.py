"""Backtesting framework for SwingTrading scoring system."""

from .backtest_engine import (
    BacktestEngine,
    BacktestConfig,
    TradeResult,
    BacktestResults
)

from .data_manager import (
    HistoricalDataManager,
    get_historical_universe_data
)

from .performance_analyzer import (
    PerformanceAnalyzer,
    calculate_trade_metrics,
    analyze_score_performance
)

from .optimization import (
    WeightOptimizer,
    optimize_scoring_weights,
    walk_forward_analysis
)

__all__ = [
    'BacktestEngine',
    'BacktestConfig', 
    'TradeResult',
    'BacktestResults',
    'HistoricalDataManager',
    'get_historical_universe_data',
    'PerformanceAnalyzer',
    'calculate_trade_metrics',
    'analyze_score_performance',
    'WeightOptimizer',
    'optimize_scoring_weights',
    'walk_forward_analysis'
]
