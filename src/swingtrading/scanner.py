"""Scanner for filtering and scoring stocks based on technical criteria."""

import logging
from datetime import date
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Dict, Any, Optional, Tuple, List

import pandas as pd
from rich.progress import Progress, SpinnerColumn, TextColumn

from .data_provider import DataProvider
from .cache_manager import CacheManager
from .rate_limiter import TokenBucket

logger = logging.getLogger(__name__)


class Scanner:
    """
    Scans and filters stocks based on technical and fundamental criteria.
    
    This class orchestrates the scanning process, applying filters
    and calculating scores for each stock in the universe.
    """
    
    def __init__(
        self,
        config: Dict[str, Any],
        data_provider: DataProvider,
        cache_manager: CacheManager,
        rate_limiter: TokenBucket
    ):
        """
        Initialize the scanner.
        
        Args:
            config: Validated configuration dictionary
            data_provider: Data provider instance
            cache_manager: Cache manager instance
            rate_limiter: Rate limiter instance
        """
        self.config = config
        self.data_provider = data_provider
        self.cache_manager = cache_manager
        self.rate_limiter = rate_limiter
        
        # Track rejection statistics
        self.filter_stats: Dict[str, int] = {}
    
    def scan(
        self,
        tickers: List[str],
        executor: ThreadPoolExecutor,
        show_progress: bool = True
    ) -> pd.DataFrame:
        """
        Scan multiple tickers in parallel.
        
        Args:
            tickers: List of ticker symbols to scan
            executor: Thread pool executor for parallel processing
            show_progress: Whether to show progress bar
            
        Returns:
            DataFrame with filtered and scored results
        """
        # Get last complete session for cache validation
        last_session = self.data_provider.get_last_complete_session()
        
        # Get task timeout from config
        task_timeout = self.config['data'].get('task_timeout', 30)
        
        # Reset filter statistics
        self.filter_stats = {}
        
        if show_progress:
            # Scan with progress bar
            results = self._scan_with_progress(tickers, executor, last_session, task_timeout)
        else:
            # Scan without progress bar
            results = self._scan_without_progress(tickers, executor, last_session, task_timeout)
        
        # Combine results
        if results:
            combined = pd.concat(results, ignore_index=False)
            logger.info(f"Scan complete: {len(combined)} stocks passed filters")
            return combined
        else:
            logger.info("Scan complete: No stocks passed filters")
            return pd.DataFrame()
    
    def _scan_with_progress(
        self,
        tickers: List[str],
        executor: ThreadPoolExecutor,
        last_session: date,
        task_timeout: int
    ) -> List[pd.DataFrame]:
        """Scan with progress bar display."""
        results = []
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True
        ) as progress:
            task = progress.add_task(
                f"Scanning {len(tickers)} tickers...",
                total=len(tickers)
            )
            
            # Submit all tasks
            futures = []
            for ticker in tickers:
                future = executor.submit(self._process_ticker, ticker, last_session)
                futures.append((ticker, future))
            
            # Collect results
            for ticker, future in futures:
                try:
                    df = future.result(timeout=task_timeout)
                    if df is not None and not df.empty:
                        results.append(df)
                except FuturesTimeoutError:
                    logger.warning(f"Timeout scanning {ticker} after {task_timeout}s")
                    self._track_rejection(ticker, 'timeout')
                except Exception as e:
                    logger.debug(f"Error processing {ticker}: {e}")
                    self._track_rejection(ticker, 'fetch_error')
                
                progress.advance(task)
        
        return results
    
    def _scan_without_progress(
        self,
        tickers: List[str],
        executor: ThreadPoolExecutor,
        last_session: date,
        task_timeout: int
    ) -> List[pd.DataFrame]:
        """Scan without progress bar display."""
        results = []
        
        # Submit all tasks
        futures = []
        for ticker in tickers:
            future = executor.submit(self._process_ticker, ticker, last_session)
            futures.append((ticker, future))
        
        # Collect results
        for ticker, future in futures:
            try:
                df = future.result(timeout=task_timeout)
                if df is not None and not df.empty:
                    results.append(df)
            except FuturesTimeoutError:
                logger.warning(f"Timeout scanning {ticker} after {task_timeout}s")
                self._track_rejection(ticker, 'timeout')
            except Exception as e:
                logger.debug(f"Error processing {ticker}: {e}")
                self._track_rejection(ticker, 'fetch_error')
        
        return results
    
    def _process_ticker(self, ticker: str, last_session: date) -> Optional[pd.DataFrame]:
        """
        Process a single ticker.
        
        This method checks cache, fetches data if needed, applies filters,
        and calculates the score.
        
        Args:
            ticker: Stock ticker symbol
            last_session: Date of last complete session
            
        Returns:
            DataFrame with single row if ticker passes filters, None otherwise
        """
        logger.debug(f"Processing {ticker}")
        
        try:
            # Check if cache is current
            if self.cache_manager.is_cache_current(ticker, last_session):
                df = self.cache_manager.read(ticker)
                logger.debug(f"Using cached data for {ticker}")
            else:
                # Fetch fresh data
                df = self.data_provider.fetch_and_calculate(ticker)
                
                if not df.empty:
                    # Update cache
                    self.cache_manager.write(ticker, df)
                    logger.debug(f"Fetched and cached data for {ticker}")
            
            if df.empty:
                self._track_rejection(ticker, 'no_data')
                return None
            
            # Apply filters to the LAST BAR ONLY
            last_bar = df.iloc[-1].copy()
            
            # Apply filter pipeline
            passed, rejection_reason = self._apply_filters(last_bar, ticker)
            
            if not passed:
                self._track_rejection(ticker, rejection_reason)
                return None
            
            # Calculate score
            last_bar['score'] = self._calculate_score(last_bar)
            
            # Return as DataFrame with session_date index
            result = pd.DataFrame([last_bar])
            result.index = [df.index[-1]]
            
            return result
            
        except Exception as e:
            logger.debug(f"Error processing {ticker}: {e}")
            self._track_rejection(ticker, 'processing_error')
            return None
    
    def _apply_filters(self, last_bar: pd.Series, ticker: str) -> Tuple[bool, Optional[str]]:
        """
        Apply filter pipeline to determine if ticker passes.
        
        Filter order (explicit):
        1. Leveraged ETF filter
        2. Price filter (effective minimum)
        3. Liquidity filter (dollar volume)
        4. Volatility filter (ATR ratio)
        5. Gap filter
        
        Args:
            last_bar: Series with the last bar's data
            ticker: Stock ticker symbol
            
        Returns:
            Tuple of (passed, rejection_reason)
        """
        filters = self.config['filters']
        
        # 1. Leveraged ETF filter (case-insensitive substring match)
        if self._is_leveraged_etf(ticker):
            return False, 'leveraged_etf'
        
        # 2. Price filter (effective minimum)
        effective_min_price = max(
            filters.get('min_price', 0),
            filters.get('penny_threshold', 0)
        )
        
        if last_bar['close'] < effective_min_price:
            return False, f'price < ${effective_min_price:.2f}'
        
        # 3. Liquidity filter (dollar volume)
        min_dollar_vol = filters.get('min_dollar_volume_10d_avg', 0)
        if last_bar.get('dollar_volume_10d_avg', 0) < min_dollar_vol:
            return False, 'low_liquidity'
        
        # 4. Volatility filter (ATR ratio with zero guard)
        min_atr_ratio = filters.get('min_atr_ratio', 0)
        if last_bar['close'] > 0:
            atr_ratio = last_bar.get('atr20', 0) / last_bar['close']
        else:
            atr_ratio = 0
        
        if atr_ratio < min_atr_ratio:
            return False, 'low_volatility'
        
        # 5. Gap filter
        max_gap = filters.get('max_gap_percent', 100)
        if last_bar.get('gap_percent', 0) > max_gap:
            return False, f'gap > {max_gap:.1f}%'
        
        # All filters passed
        return True, None
    
    def _is_leveraged_etf(self, ticker: str) -> bool:
        """
        Check if ticker matches leveraged ETF patterns.
        
        Uses simple substring matching for efficiency.
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            True if ticker matches a leveraged ETF pattern
        """
        patterns = self.config['filters'].get('leveraged_etf_patterns', [])
        ticker_upper = ticker.upper()
        
        # Use substring match instead of regex for efficiency
        return any(pat.upper() in ticker_upper for pat in patterns)
    
    def _calculate_score(self, row: pd.Series) -> float:
        """
        Calculate weighted composite score.
        
        Components:
        - Pullback proximity: Distance from 20-day high
        - Trend strength: Price above SMA(50)
        - RSI headroom: Room to rise from current RSI
        - Volume ratio: Current vs average volume
        
        Args:
            row: Series with indicator data
            
        Returns:
            Score between 0 and 100
        """
        weights = self.config['scoring']['weights']
        
        # Normalize weights if they don't sum to 1.0
        weight_sum = sum(weights.values())
        if abs(weight_sum - 1.0) > 1e-6:
            weights = {k: v / weight_sum for k, v in weights.items()}
        
        # Calculate components with zero guards
        
        # Pullback proximity: (1 - close/high20) * 100
        high20 = row.get('high20', row['close'])
        if high20 > 0:
            pullback = (1 - row['close'] / high20) * 100
        else:
            pullback = 0
        pullback = max(0, min(100, pullback))
        
        # Trend strength: ((close/sma50) - 1) * 100
        sma50 = row.get('sma50', row['close'])
        if sma50 > 0:
            trend = ((row['close'] / sma50) - 1) * 100
        else:
            trend = 0
        trend = max(0, min(100, trend))
        
        # RSI headroom: (70 - RSI)
        rsi = row.get('rsi14', 50)
        rsi_room = 70 - rsi
        rsi_room = max(0, min(100, rsi_room))
        
        # Volume ratio: (volume/avg_volume) * 20
        avg_vol = row.get('volume_avg_10d', row['volume'])
        if avg_vol > 0:
            vol_ratio = (row['volume'] / avg_vol) * 20
        else:
            vol_ratio = 0
        vol_ratio = max(0, min(100, vol_ratio))
        
        # Calculate weighted sum
        score = (
            pullback * weights.get('pullback_proximity', 0.25) +
            trend * weights.get('trend_strength', 0.25) +
            rsi_room * weights.get('rsi_headroom', 0.25) +
            vol_ratio * weights.get('volume_ratio', 0.25)
        )
        
        # Round to 2 decimal places for deterministic sorting
        return round(score, 2)
    
    def _track_rejection(self, ticker: str, reason: str) -> None:
        """
        Track rejection reason for summary statistics.
        
        Args:
            ticker: Stock ticker symbol
            reason: Rejection reason
        """
        if reason not in self.filter_stats:
            self.filter_stats[reason] = 0
        self.filter_stats[reason] += 1
        
        logger.debug(f"Rejected {ticker}: {reason}")