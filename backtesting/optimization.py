"""Optimization tools for scoring system weights and parameters."""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional, Callable
from datetime import datetime, timedelta
from scipy.optimize import minimize
import itertools
from concurrent.futures import ProcessPoolExecutor
import json

from .backtest_engine import BacktestEngine, BacktestConfig, BacktestResults
from .data_manager import HistoricalDataManager


class WeightOptimizer:
    """Optimizes scoring component weights using historical data."""
    
    def __init__(self, data_manager: HistoricalDataManager):
        """Initialize with data manager."""
        self.data_manager = data_manager
        self.engine = BacktestEngine(data_manager)
    
    def optimize_weights(self, 
                        base_config: BacktestConfig,
                        objective: str = 'sharpe_ratio',
                        method: str = 'scipy') -> Dict:
        """Optimize scoring weights to maximize objective function.
        
        Args:
            base_config: Base backtest configuration
            objective: Objective to optimize ('sharpe_ratio', 'total_return', 'win_rate')
            method: Optimization method ('scipy', 'grid_search', 'genetic')
            
        Returns:
            Dict with optimal weights and performance metrics
        """
        print(f"Optimizing weights using {method} method, objective: {objective}")
        
        if method == 'scipy':
            return self._scipy_optimize(base_config, objective)
        elif method == 'grid_search':
            return self._grid_search_optimize(base_config, objective)
        elif method == 'genetic':
            return self._genetic_optimize(base_config, objective)
        else:
            raise ValueError(f"Unknown optimization method: {method}")
    
    def _scipy_optimize(self, base_config: BacktestConfig, objective: str) -> Dict:
        """Use scipy optimization."""
        
        def objective_function(weights):
            """Objective function for scipy optimizer."""
            # Ensure weights sum to 1
            weights = weights / np.sum(weights)
            
            # Run backtest with these weights
            results = self._run_backtest_with_weights(base_config, weights)
            
            if results.total_trades == 0:
                return -999  # Penalty for no trades
            
            # Return negative value for minimization
            if objective == 'sharpe_ratio':
                return -results.sharpe_ratio
            elif objective == 'total_return':
                return -results.total_return
            elif objective == 'win_rate':
                return -results.win_rate
            elif objective == 'profit_factor':
                return -results.profit_factor
            else:
                return -results.avg_return
        
        # Initial weights (equal)
        initial_weights = np.array([0.25, 0.25, 0.25, 0.25])
        
        # Constraints: weights sum to 1, all positive
        constraints = {'type': 'eq', 'fun': lambda x: np.sum(x) - 1}
        bounds = [(0.05, 0.6) for _ in range(4)]  # Min 5%, max 60% per component
        
        print("Running scipy optimization...")
        result = minimize(
            objective_function,
            initial_weights,
            method='SLSQP',
            bounds=bounds,
            constraints=constraints,
            options={'maxiter': 50, 'disp': True}
        )
        
        optimal_weights = result.x / np.sum(result.x)  # Normalize
        
        # Run final backtest with optimal weights
        final_results = self._run_backtest_with_weights(base_config, optimal_weights)
        
        return {
            'method': 'scipy',
            'objective': objective,
            'optimal_weights': {
                'pullback': optimal_weights[0],
                'trend': optimal_weights[1], 
                'rsi': optimal_weights[2],
                'volume': optimal_weights[3]
            },
            'performance': final_results.to_dict()['summary'],
            'optimization_success': result.success,
            'iterations': result.nit
        }
    
    def _grid_search_optimize(self, base_config: BacktestConfig, objective: str) -> Dict:
        """Use grid search optimization."""
        print("Running grid search optimization...")
        
        # Define weight ranges (must sum to 1)
        weight_options = [0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40]
        
        best_score = -999
        best_weights = None
        best_results = None
        
        # Generate all combinations that sum to 1.0
        combinations_tested = 0
        
        for w1 in weight_options:
            for w2 in weight_options:
                for w3 in weight_options:
                    w4 = 1.0 - w1 - w2 - w3
                    
                    # Check if w4 is valid
                    if w4 < 0.05 or w4 > 0.6:
                        continue
                    
                    weights = np.array([w1, w2, w3, w4])
                    combinations_tested += 1
                    
                    # Run backtest
                    results = self._run_backtest_with_weights(base_config, weights)
                    
                    if results.total_trades == 0:
                        continue
                    
                    # Evaluate objective
                    if objective == 'sharpe_ratio':
                        score = results.sharpe_ratio
                    elif objective == 'total_return':
                        score = results.total_return
                    elif objective == 'win_rate':
                        score = results.win_rate
                    elif objective == 'profit_factor':
                        score = results.profit_factor
                    else:
                        score = results.avg_return
                    
                    if score > best_score:
                        best_score = score
                        best_weights = weights
                        best_results = results
                    
                    if combinations_tested % 10 == 0:
                        print(f"Tested {combinations_tested} combinations, best {objective}: {best_score:.3f}")
        
        return {
            'method': 'grid_search',
            'objective': objective,
            'optimal_weights': {
                'pullback': best_weights[0],
                'trend': best_weights[1],
                'rsi': best_weights[2], 
                'volume': best_weights[3]
            },
            'performance': best_results.to_dict()['summary'],
            'combinations_tested': combinations_tested,
            'best_score': best_score
        }
    
    def _genetic_optimize(self, base_config: BacktestConfig, objective: str) -> Dict:
        """Use genetic algorithm optimization."""
        # Simplified genetic algorithm implementation
        population_size = 20
        generations = 10
        mutation_rate = 0.1
        
        print(f"Running genetic algorithm: {population_size} population, {generations} generations")
        
        # Initialize population
        population = []
        for _ in range(population_size):
            weights = np.random.dirichlet([1, 1, 1, 1])  # Random weights that sum to 1
            population.append(weights)
        
        best_individual = None
        best_score = -999
        
        for generation in range(generations):
            print(f"Generation {generation + 1}/{generations}")
            
            # Evaluate population
            scores = []
            for weights in population:
                results = self._run_backtest_with_weights(base_config, weights)
                
                if results.total_trades == 0:
                    score = -999
                elif objective == 'sharpe_ratio':
                    score = results.sharpe_ratio
                elif objective == 'total_return':
                    score = results.total_return
                elif objective == 'win_rate':
                    score = results.win_rate
                else:
                    score = results.avg_return
                
                scores.append(score)
                
                if score > best_score:
                    best_score = score
                    best_individual = weights.copy()
            
            # Selection and reproduction (simplified)
            # Keep top 50% and generate new offspring
            sorted_indices = np.argsort(scores)[::-1]
            top_half = [population[i] for i in sorted_indices[:population_size//2]]
            
            # Generate new population
            new_population = top_half.copy()
            
            # Add offspring (crossover + mutation)
            while len(new_population) < population_size:
                parent1 = np.random.choice(len(top_half))
                parent2 = np.random.choice(len(top_half))
                
                # Simple crossover
                child = (top_half[parent1] + top_half[parent2]) / 2
                
                # Mutation
                if np.random.random() < mutation_rate:
                    child += np.random.normal(0, 0.05, 4)
                    child = np.abs(child)  # Ensure positive
                    child = child / np.sum(child)  # Normalize
                
                new_population.append(child)
            
            population = new_population
            print(f"Best score so far: {best_score:.3f}")
        
        # Final evaluation
        final_results = self._run_backtest_with_weights(base_config, best_individual)
        
        return {
            'method': 'genetic',
            'objective': objective,
            'optimal_weights': {
                'pullback': best_individual[0],
                'trend': best_individual[1],
                'rsi': best_individual[2],
                'volume': best_individual[3]
            },
            'performance': final_results.to_dict()['summary'],
            'generations': generations,
            'best_score': best_score
        }
    
    def _run_backtest_with_weights(self, base_config: BacktestConfig, weights: np.ndarray) -> BacktestResults:
        """Run backtest with specific weights.
        
        Note: This is a simplified implementation. In practice, you'd need to
        modify the scoring system to use these weights dynamically.
        """
        # For now, we'll run the standard backtest
        # In a full implementation, you'd modify the scoring calculation
        # to use the provided weights instead of the hardcoded 0.25 each
        
        return self.engine.run_backtest(base_config)


def optimize_scoring_weights(symbols: List[str], 
                           start_date: str, 
                           end_date: str,
                           objective: str = 'sharpe_ratio') -> Dict:
    """Convenience function to optimize scoring weights.
    
    Args:
        symbols: List of symbols for universe
        start_date: Start date for optimization period
        end_date: End date for optimization period
        objective: Objective function to optimize
        
    Returns:
        Dict with optimization results
    """
    # Initialize components
    data_manager = HistoricalDataManager()
    optimizer = WeightOptimizer(data_manager)
    
    # Create base configuration
    config = BacktestConfig(
        start_date=start_date,
        end_date=end_date,
        universe=symbols,
        min_score=30.0,
        max_positions=10,
        holding_period_days=10
    )
    
    # Run optimization
    return optimizer.optimize_weights(config, objective, method='grid_search')


def walk_forward_analysis(symbols: List[str],
                         start_date: str,
                         end_date: str, 
                         train_months: int = 12,
                         test_months: int = 3) -> Dict:
    """Perform walk-forward analysis of weight optimization.
    
    Args:
        symbols: Universe of symbols
        start_date: Overall start date
        end_date: Overall end date
        train_months: Months to use for training/optimization
        test_months: Months to use for out-of-sample testing
        
    Returns:
        Dict with walk-forward results
    """
    print(f"Starting walk-forward analysis: {train_months}m train, {test_months}m test")
    
    results = []
    current_date = datetime.strptime(start_date, '%Y-%m-%d')
    end_dt = datetime.strptime(end_date, '%Y-%m-%d')
    
    while current_date < end_dt:
        # Define train period
        train_start = current_date
        train_end = current_date + timedelta(days=train_months * 30)
        
        # Define test period
        test_start = train_end + timedelta(days=1)
        test_end = test_start + timedelta(days=test_months * 30)
        
        if test_end > end_dt:
            break
        
        print(f"Train: {train_start.date()} to {train_end.date()}")
        print(f"Test: {test_start.date()} to {test_end.date()}")
        
        # Optimize on train period
        train_results = optimize_scoring_weights(
            symbols,
            train_start.strftime('%Y-%m-%d'),
            train_end.strftime('%Y-%m-%d'),
            objective='sharpe_ratio'
        )
        
        # Test on out-of-sample period
        # (This would require implementing dynamic weight usage)
        
        results.append({
            'train_period': f"{train_start.date()} to {train_end.date()}",
            'test_period': f"{test_start.date()} to {test_end.date()}",
            'optimal_weights': train_results['optimal_weights'],
            'train_performance': train_results['performance']
            # 'test_performance': test_results  # Would add this
        })
        
        # Move to next period
        current_date = test_start
    
    return {
        'periods': results,
        'summary': {
            'total_periods': len(results),
            'train_months': train_months,
            'test_months': test_months
        }
    }
