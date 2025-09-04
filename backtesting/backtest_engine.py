"""Core backtesting engine for scoring system validation."""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, NamedTuple
from dataclasses import dataclass
from pathlib import Path
import json

from scoring_v2.scoring import calculate_score_v2


@dataclass
class BacktestConfig:
    """Configuration for backtesting."""
    start_date: str  # 'YYYY-MM-DD'
    end_date: str    # 'YYYY-MM-DD'
    universe: List[str]  # List of symbols
    min_score: float = 30.0
    max_positions: int = 10
    holding_period_days: int = 10
    stop_loss_atr_mult: float = 1.5
    take_profit_atr_mult: float = 3.0
    commission_per_trade: float = 1.0
    slippage_bps: int = 5  # basis points


class TradeResult(NamedTuple):
    """Individual trade result."""
    symbol: str
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    score: float
    atr: float
    rsi: float
    holding_days: int
    return_pct: float
    exit_reason: str  # 'time', 'stop', 'target'


@dataclass
class BacktestResults:
    """Complete backtest results."""
    trades: List[TradeResult]
    config: BacktestConfig
    start_date: str
    end_date: str
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    avg_return: float
    avg_win: float
    avg_loss: float
    profit_factor: float
    max_drawdown: float
    sharpe_ratio: float
    total_return: float
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'summary': {
                'start_date': self.start_date,
                'end_date': self.end_date,
                'total_trades': self.total_trades,
                'winning_trades': self.winning_trades,
                'losing_trades': self.losing_trades,
                'win_rate': self.win_rate,
                'avg_return': self.avg_return,
                'avg_win': self.avg_win,
                'avg_loss': self.avg_loss,
                'profit_factor': self.profit_factor,
                'max_drawdown': self.max_drawdown,
                'sharpe_ratio': self.sharpe_ratio,
                'total_return': self.total_return
            },
            'trades': [trade._asdict() for trade in self.trades],
            'config': {
                'start_date': self.config.start_date,
                'end_date': self.config.end_date,
                'min_score': self.config.min_score,
                'max_positions': self.config.max_positions,
                'holding_period_days': self.config.holding_period_days,
                'stop_loss_atr_mult': self.config.stop_loss_atr_mult,
                'take_profit_atr_mult': self.config.take_profit_atr_mult
            }
        }


class BacktestEngine:
    """Main backtesting engine."""
    
    def __init__(self, data_manager):
        """Initialize with data manager."""
        self.data_manager = data_manager
        
    def run_backtest(self, config: BacktestConfig) -> BacktestResults:
        """Run complete backtest."""
        print(f"Starting backtest from {config.start_date} to {config.end_date}")
        print(f"Universe: {len(config.universe)} symbols")
        
        trades = []
        active_positions = {}  # symbol -> entry_info
        
        # Get trading dates
        trading_dates = self._get_trading_dates(config.start_date, config.end_date)
        
        for i, current_date in enumerate(trading_dates):
            # Progress reporting - less frequent for large backtests
            if len(config.universe) > 50:
                if i % 10 == 0 or i == len(trading_dates) - 1:
                    progress = (i + 1) / len(trading_dates) * 100
                    print(f"Processing {current_date} ({i+1}/{len(trading_dates)}) - {progress:.1f}% complete")
            else:
                print(f"Processing {current_date} ({i+1}/{len(trading_dates)})")
            
            # Exit positions first
            exits = self._process_exits(active_positions, current_date, config)
            trades.extend(exits)
            
            # Remove exited positions
            for exit_trade in exits:
                if exit_trade.symbol in active_positions:
                    del active_positions[exit_trade.symbol]
            
            # Find new entries if we have capacity
            if len(active_positions) < config.max_positions:
                new_entries = self._find_entries(
                    current_date, 
                    config, 
                    active_positions,
                    config.max_positions - len(active_positions)
                )
                active_positions.update(new_entries)
        
        # Close any remaining positions at end date
        final_exits = self._close_remaining_positions(active_positions, config.end_date, config)
        trades.extend(final_exits)
        
        # Calculate results
        results = self._calculate_results(trades, config)
        
        print(f"Backtest complete: {len(trades)} trades, {results.win_rate:.1%} win rate")
        return results
    
    def _get_trading_dates(self, start_date: str, end_date: str) -> List[str]:
        """Get list of trading dates between start and end."""
        # Simple implementation - in production, use market calendar
        dates = []
        current = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')
        
        while current <= end:
            # Skip weekends (simple approximation)
            if current.weekday() < 5:
                dates.append(current.strftime('%Y-%m-%d'))
            current += timedelta(days=1)
            
        return dates
    
    def _process_exits(self, active_positions: Dict, current_date: str, config: BacktestConfig) -> List[TradeResult]:
        """Process exits for active positions."""
        exits = []
        
        for symbol, entry_info in list(active_positions.items()):
            # Get current price data
            current_data = self.data_manager.get_daily_data(symbol, current_date)
            if not current_data:
                continue
                
            current_price = current_data['close']
            entry_date = datetime.strptime(entry_info['date'], '%Y-%m-%d')
            current_date_dt = datetime.strptime(current_date, '%Y-%m-%d')
            holding_days = (current_date_dt - entry_date).days
            
            exit_reason = None
            exit_price = current_price
            
            # Check time exit
            if holding_days >= config.holding_period_days:
                exit_reason = 'time'
            
            # Check stop loss
            elif current_price <= entry_info['stop_price']:
                exit_reason = 'stop'
                exit_price = entry_info['stop_price']
            
            # Check take profit
            elif current_price >= entry_info['target_price']:
                exit_reason = 'target' 
                exit_price = entry_info['target_price']
            
            if exit_reason:
                return_pct = (exit_price - entry_info['entry_price']) / entry_info['entry_price'] * 100
                
                trade = TradeResult(
                    symbol=symbol,
                    entry_date=entry_info['date'],
                    exit_date=current_date,
                    entry_price=entry_info['entry_price'],
                    exit_price=exit_price,
                    score=entry_info['score'],
                    atr=entry_info['atr'],
                    rsi=entry_info['rsi'],
                    holding_days=holding_days,
                    return_pct=return_pct,
                    exit_reason=exit_reason
                )
                exits.append(trade)
        
        return exits

    def _find_entries(self, current_date: str, config: BacktestConfig,
                     active_positions: Dict, max_new_entries: int) -> Dict:
        """Find new entry candidates for current date."""
        new_entries = {}
        candidates = []

        # Score all symbols for current date
        scored_candidates = 0
        valid_scores = 0

        for symbol in config.universe:
            if symbol in active_positions:
                continue  # Already have position

            # Get historical data (need 366+ bars)
            bars = self.data_manager.get_historical_bars(symbol, current_date, days=550)
            if not bars or len(bars) < 366:
                continue

            scored_candidates += 1

            # Calculate score
            score, gate_reason, components = calculate_score_v2(bars, symbol)
            if score is None or score < config.min_score:
                continue

            valid_scores += 1

            # Get current price and ATR
            current_data = bars[-1]  # Most recent bar
            current_price = current_data['c']
            atr = components['raw_features'].get('atr_value', current_price * 0.02)
            rsi = components['raw_features'].get('rsi_value', 50)

            candidates.append({
                'symbol': symbol,
                'score': score,
                'price': current_price,
                'atr': atr,
                'rsi': rsi
            })

        # Sort by score and take top candidates
        candidates.sort(key=lambda x: x['score'], reverse=True)
        selected = candidates[:max_new_entries]

        # Create entry positions
        for candidate in selected:
            symbol = candidate['symbol']
            entry_price = candidate['price']
            atr = candidate['atr']

            # Calculate stop and target prices
            stop_price = entry_price - (atr * config.stop_loss_atr_mult)
            target_price = entry_price + (atr * config.take_profit_atr_mult)

            new_entries[symbol] = {
                'date': current_date,
                'entry_price': entry_price,
                'stop_price': stop_price,
                'target_price': target_price,
                'score': candidate['score'],
                'atr': atr,
                'rsi': candidate['rsi']
            }

        # Log scoring statistics for large universes
        if len(config.universe) > 50 and scored_candidates > 0:
            score_rate = valid_scores / scored_candidates * 100
            print(f"    Scored {scored_candidates} stocks, {valid_scores} passed filters ({score_rate:.1f}%), selected {len(selected)}")

        return new_entries

    def _close_remaining_positions(self, active_positions: Dict, end_date: str,
                                 config: BacktestConfig) -> List[TradeResult]:
        """Close any remaining positions at end of backtest."""
        exits = []

        for symbol, entry_info in active_positions.items():
            # Get final price
            final_data = self.data_manager.get_daily_data(symbol, end_date)
            if not final_data:
                continue

            final_price = final_data['close']
            entry_date = datetime.strptime(entry_info['date'], '%Y-%m-%d')
            end_date_dt = datetime.strptime(end_date, '%Y-%m-%d')
            holding_days = (end_date_dt - entry_date).days

            return_pct = (final_price - entry_info['entry_price']) / entry_info['entry_price'] * 100

            trade = TradeResult(
                symbol=symbol,
                entry_date=entry_info['date'],
                exit_date=end_date,
                entry_price=entry_info['entry_price'],
                exit_price=final_price,
                score=entry_info['score'],
                atr=entry_info['atr'],
                rsi=entry_info['rsi'],
                holding_days=holding_days,
                return_pct=return_pct,
                exit_reason='end'
            )
            exits.append(trade)

        return exits

    def _calculate_results(self, trades: List[TradeResult], config: BacktestConfig) -> BacktestResults:
        """Calculate backtest performance metrics."""
        if not trades:
            return BacktestResults(
                trades=[], config=config, start_date=config.start_date, end_date=config.end_date,
                total_trades=0, winning_trades=0, losing_trades=0, win_rate=0.0,
                avg_return=0.0, avg_win=0.0, avg_loss=0.0, profit_factor=0.0,
                max_drawdown=0.0, sharpe_ratio=0.0, total_return=0.0
            )

        returns = [trade.return_pct for trade in trades]
        winning_trades = [r for r in returns if r > 0]
        losing_trades = [r for r in returns if r <= 0]

        total_trades = len(trades)
        win_count = len(winning_trades)
        loss_count = len(losing_trades)
        win_rate = win_count / total_trades if total_trades > 0 else 0

        avg_return = np.mean(returns) if returns else 0
        avg_win = np.mean(winning_trades) if winning_trades else 0
        avg_loss = np.mean(losing_trades) if losing_trades else 0

        # Profit factor
        gross_profit = sum(winning_trades) if winning_trades else 0
        gross_loss = abs(sum(losing_trades)) if losing_trades else 0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

        # Sharpe ratio (simplified)
        sharpe_ratio = avg_return / np.std(returns) if len(returns) > 1 and np.std(returns) > 0 else 0

        # Total return (compound)
        total_return = np.prod([1 + r/100 for r in returns]) - 1 if returns else 0

        # Max drawdown (simplified)
        cumulative_returns = np.cumprod([1 + r/100 for r in returns])
        running_max = np.maximum.accumulate(cumulative_returns)
        drawdowns = (cumulative_returns - running_max) / running_max
        max_drawdown = abs(np.min(drawdowns)) if len(drawdowns) > 0 else 0

        return BacktestResults(
            trades=trades,
            config=config,
            start_date=config.start_date,
            end_date=config.end_date,
            total_trades=total_trades,
            winning_trades=win_count,
            losing_trades=loss_count,
            win_rate=win_rate,
            avg_return=avg_return,
            avg_win=avg_win,
            avg_loss=avg_loss,
            profit_factor=profit_factor,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe_ratio,
            total_return=total_return * 100  # Convert to percentage
        )
