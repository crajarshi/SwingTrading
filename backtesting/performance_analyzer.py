"""Performance analysis tools for backtesting results."""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from typing import Dict, List, Tuple, Optional
from datetime import datetime
import json
from pathlib import Path

from .backtest_engine import BacktestResults, TradeResult


class PerformanceAnalyzer:
    """Analyzes backtest performance and generates reports."""
    
    def __init__(self, results: BacktestResults):
        """Initialize with backtest results."""
        self.results = results
        self.trades_df = pd.DataFrame([trade._asdict() for trade in results.trades])
        
        if not self.trades_df.empty:
            self.trades_df['entry_date'] = pd.to_datetime(self.trades_df['entry_date'])
            self.trades_df['exit_date'] = pd.to_datetime(self.trades_df['exit_date'])
    
    def generate_performance_report(self, output_dir: str = "backtest_results") -> Dict:
        """Generate comprehensive performance report.
        
        Args:
            output_dir: Directory to save reports
            
        Returns:
            Dict with report paths and key metrics
        """
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)
        
        # Generate different report sections
        summary = self._generate_summary_report(output_path)
        score_analysis = self._analyze_score_performance(output_path)
        time_analysis = self._analyze_time_patterns(output_path)
        drawdown_analysis = self._analyze_drawdowns(output_path)
        
        # Save complete results
        results_file = output_path / "backtest_results.json"
        with open(results_file, 'w') as f:
            json.dump(self.results.to_dict(), f, indent=2)
        
        return {
            'summary': summary,
            'score_analysis': score_analysis,
            'time_analysis': time_analysis,
            'drawdown_analysis': drawdown_analysis,
            'results_file': str(results_file)
        }
    
    def _generate_summary_report(self, output_path: Path) -> str:
        """Generate summary performance report."""
        report_lines = [
            "# Backtest Performance Summary",
            f"**Period:** {self.results.start_date} to {self.results.end_date}",
            f"**Strategy:** Swing Trading with Score v2",
            "",
            "## Key Metrics",
            f"- **Total Trades:** {self.results.total_trades:,}",
            f"- **Win Rate:** {self.results.win_rate:.1%}",
            f"- **Average Return:** {self.results.avg_return:.2f}%",
            f"- **Average Win:** {self.results.avg_win:.2f}%", 
            f"- **Average Loss:** {self.results.avg_loss:.2f}%",
            f"- **Profit Factor:** {self.results.profit_factor:.2f}",
            f"- **Total Return:** {self.results.total_return:.2f}%",
            f"- **Max Drawdown:** {self.results.max_drawdown:.2f}%",
            f"- **Sharpe Ratio:** {self.results.sharpe_ratio:.2f}",
            ""
        ]
        
        if not self.trades_df.empty:
            # Add distribution analysis
            report_lines.extend([
                "## Return Distribution",
                f"- **Best Trade:** {self.trades_df['return_pct'].max():.2f}%",
                f"- **Worst Trade:** {self.trades_df['return_pct'].min():.2f}%",
                f"- **Median Return:** {self.trades_df['return_pct'].median():.2f}%",
                f"- **Standard Deviation:** {self.trades_df['return_pct'].std():.2f}%",
                ""
            ])
            
            # Exit reason breakdown
            exit_reasons = self.trades_df['exit_reason'].value_counts()
            report_lines.extend([
                "## Exit Reasons",
                *[f"- **{reason.title()}:** {count} trades ({count/len(self.trades_df):.1%})" 
                  for reason, count in exit_reasons.items()],
                ""
            ])
            
            # Holding period analysis
            avg_holding = self.trades_df['holding_days'].mean()
            report_lines.extend([
                "## Holding Period",
                f"- **Average:** {avg_holding:.1f} days",
                f"- **Median:** {self.trades_df['holding_days'].median():.0f} days",
                f"- **Range:** {self.trades_df['holding_days'].min()}-{self.trades_df['holding_days'].max()} days",
                ""
            ])
        
        # Configuration used
        config = self.results.config
        report_lines.extend([
            "## Configuration",
            f"- **Min Score:** {config.min_score}",
            f"- **Max Positions:** {config.max_positions}",
            f"- **Holding Period:** {config.holding_period_days} days",
            f"- **Stop Loss:** {config.stop_loss_atr_mult}x ATR",
            f"- **Take Profit:** {config.take_profit_atr_mult}x ATR",
            ""
        ])
        
        # Save report
        report_file = output_path / "performance_summary.md"
        with open(report_file, 'w') as f:
            f.write('\n'.join(report_lines))
        
        return str(report_file)
    
    def _analyze_score_performance(self, output_path: Path) -> str:
        """Analyze performance by score ranges."""
        if self.trades_df.empty:
            return ""
        
        # Define score buckets
        score_buckets = [
            (0, 30, "Low (0-30)"),
            (30, 50, "Medium (30-50)"), 
            (50, 70, "High (50-70)"),
            (70, 100, "Very High (70+)")
        ]
        
        analysis = []
        analysis.append("# Score Performance Analysis\n")
        
        for min_score, max_score, label in score_buckets:
            bucket_trades = self.trades_df[
                (self.trades_df['score'] >= min_score) & 
                (self.trades_df['score'] < max_score)
            ]
            
            if len(bucket_trades) == 0:
                continue
            
            win_rate = (bucket_trades['return_pct'] > 0).mean()
            avg_return = bucket_trades['return_pct'].mean()
            trade_count = len(bucket_trades)
            
            analysis.extend([
                f"## {label}",
                f"- **Trades:** {trade_count}",
                f"- **Win Rate:** {win_rate:.1%}",
                f"- **Avg Return:** {avg_return:.2f}%",
                f"- **Best:** {bucket_trades['return_pct'].max():.2f}%",
                f"- **Worst:** {bucket_trades['return_pct'].min():.2f}%",
                ""
            ])
        
        # Save analysis
        analysis_file = output_path / "score_analysis.md"
        with open(analysis_file, 'w') as f:
            f.write('\n'.join(analysis))
        
        return str(analysis_file)
    
    def _analyze_time_patterns(self, output_path: Path) -> str:
        """Analyze performance patterns over time."""
        if self.trades_df.empty:
            return ""
        
        # Monthly performance
        self.trades_df['entry_month'] = self.trades_df['entry_date'].dt.to_period('M')
        monthly_stats = self.trades_df.groupby('entry_month').agg({
            'return_pct': ['count', 'mean'],
            'score': 'mean'
        }).round(2)

        # Calculate win rate separately
        monthly_win_rates = self.trades_df.groupby('entry_month')['return_pct'].apply(lambda x: (x > 0).mean()).round(3)
        
        analysis = ["# Time Pattern Analysis\n", "## Monthly Performance\n"]
        
        for month, stats in monthly_stats.iterrows():
            trade_count = stats[('return_pct', 'count')]
            avg_return = stats[('return_pct', 'mean')]
            avg_score = stats[('score', 'mean')]
            win_rate = monthly_win_rates[month]

            analysis.extend([
                f"**{month}:**",
                f"- Trades: {trade_count}, Win Rate: {win_rate:.1%}, Avg Return: {avg_return:.2f}%, Avg Score: {avg_score:.1f}",
                ""
            ])
        
        # Save analysis
        time_file = output_path / "time_analysis.md"
        with open(time_file, 'w') as f:
            f.write('\n'.join(analysis))
        
        return str(time_file)
    
    def _analyze_drawdowns(self, output_path: Path) -> str:
        """Analyze drawdown periods."""
        if self.trades_df.empty:
            return ""
        
        # Calculate cumulative returns
        sorted_trades = self.trades_df.sort_values('exit_date')
        sorted_trades['cumulative_return'] = (1 + sorted_trades['return_pct'] / 100).cumprod()
        sorted_trades['running_max'] = sorted_trades['cumulative_return'].expanding().max()
        sorted_trades['drawdown'] = (sorted_trades['cumulative_return'] - sorted_trades['running_max']) / sorted_trades['running_max']
        
        max_dd = sorted_trades['drawdown'].min()
        max_dd_date = sorted_trades.loc[sorted_trades['drawdown'].idxmin(), 'exit_date']
        
        analysis = [
            "# Drawdown Analysis\n",
            f"**Maximum Drawdown:** {abs(max_dd):.2%}",
            f"**Max DD Date:** {max_dd_date.strftime('%Y-%m-%d')}",
            "",
            "## Drawdown Periods",
            ""
        ]
        
        # Find significant drawdown periods (>5%)
        significant_dd = sorted_trades[sorted_trades['drawdown'] < -0.05]
        if not significant_dd.empty:
            for idx, row in significant_dd.iterrows():
                analysis.append(f"- {row['exit_date'].strftime('%Y-%m-%d')}: {abs(row['drawdown']):.2%}")
        else:
            analysis.append("- No significant drawdown periods (>5%)")
        
        # Save analysis
        dd_file = output_path / "drawdown_analysis.md"
        with open(dd_file, 'w') as f:
            f.write('\n'.join(analysis))
        
        return str(dd_file)


def calculate_trade_metrics(trades: List[TradeResult]) -> Dict:
    """Calculate basic trade metrics from trade list."""
    if not trades:
        return {}
    
    returns = [trade.return_pct for trade in trades]
    winning_trades = [r for r in returns if r > 0]
    losing_trades = [r for r in returns if r <= 0]
    
    return {
        'total_trades': len(trades),
        'winning_trades': len(winning_trades),
        'losing_trades': len(losing_trades),
        'win_rate': len(winning_trades) / len(trades),
        'avg_return': np.mean(returns),
        'avg_win': np.mean(winning_trades) if winning_trades else 0,
        'avg_loss': np.mean(losing_trades) if losing_trades else 0,
        'best_trade': max(returns),
        'worst_trade': min(returns),
        'profit_factor': sum(winning_trades) / abs(sum(losing_trades)) if losing_trades else float('inf')
    }


def analyze_score_performance(trades: List[TradeResult], score_buckets: List[Tuple[float, float]]) -> Dict:
    """Analyze performance by score ranges.
    
    Args:
        trades: List of trade results
        score_buckets: List of (min_score, max_score) tuples
        
    Returns:
        Dict with performance by score bucket
    """
    results = {}
    
    for min_score, max_score in score_buckets:
        bucket_trades = [t for t in trades if min_score <= t.score < max_score]
        if bucket_trades:
            results[f"{min_score}-{max_score}"] = calculate_trade_metrics(bucket_trades)
    
    return results
