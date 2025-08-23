"""Data provider for fetching and processing market data from Alpaca."""

import os
import time
import logging
from datetime import datetime, timedelta, date
from typing import Dict, Any, Optional

import pandas as pd
import numpy as np
import pytz
from alpaca.data import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import Adjustment, DataFeed
from alpaca.common.exceptions import APIError as AlpacaAPIError
from alpaca.data.exceptions import NoDataAvailable

from .exceptions import DataError
from .rate_limiter import TokenBucket

logger = logging.getLogger(__name__)


class DataProvider:
    """
    Handles all data fetching and indicator calculation.
    
    This class manages the Alpaca API connection, implements retry logic,
    and calculates technical indicators on the fetched data.
    """
    
    # Feed mapping from config strings to Alpaca enums
    FEED_MAP = {
        'iex': DataFeed.IEX,
        'sip': DataFeed.SIP,
        'otc': DataFeed.OTC
    }
    
    # Retry configuration
    RETRY_STATUS_CODES = {429, 503, 504, 408}  # Retry on these HTTP codes
    FAST_FAIL_CODES = {400, 401, 403}  # Don't retry on these
    MAX_RETRIES = 3
    BACKOFF_BASE = 2  # Exponential backoff: 2^attempt seconds
    
    def __init__(self, config: Dict[str, Any], rate_limiter: TokenBucket):
        """
        Initialize the data provider.
        
        Args:
            config: Validated configuration dictionary
            rate_limiter: Token bucket for rate limiting
        """
        self.config = config
        self.rate_limiter = rate_limiter
        
        # Parse feed configuration
        feed_str = config['data']['feed'].lower()
        if feed_str not in self.FEED_MAP:
            raise ValueError(f"Invalid feed: {feed_str}. Must be one of: {list(self.FEED_MAP.keys())}")
        
        self.feed = self.FEED_MAP[feed_str]
        self.timezone = pytz.timezone(config['data']['timezone'])
        
        # Initialize Alpaca client
        api_key = os.getenv(config['data']['api_key_env'])
        api_secret = os.getenv(config['data']['api_secret_env'])
        
        if not api_key or not api_secret:
            raise ValueError(
                f"API credentials not found. Please set {config['data']['api_key_env']} "
                f"and {config['data']['api_secret_env']} environment variables."
            )
        
        self.client = StockHistoricalDataClient(
            api_key=api_key,
            secret_key=api_secret,
            url_override=config['data']['base_url']
        )
        
        # Cache for last complete session
        self._cached_last_session: Optional[date] = None
    
    def get_last_complete_session(self) -> date:
        """
        Get the last complete trading session date.
        
        This method probes SPY to determine the last complete trading day,
        with a partial-day guard to exclude today's incomplete session.
        
        Returns:
            Date of the last complete trading session
            
        Raises:
            DataError: If unable to determine the session
        """
        if self._cached_last_session is not None:
            return self._cached_last_session
        
        logger.debug("Probing SPY to determine last complete session")
        
        # Fetch SPY with sufficient history
        end = datetime.now(self.timezone)
        start = end - timedelta(days=15)
        
        try:
            spy_bars = self._fetch_bars_with_retry("SPY", start, end)
        except Exception as e:
            raise DataError(f"Cannot determine session from SPY: {e}")
        
        if spy_bars.empty:
            raise DataError("No SPY data available for session probe")
        
        if len(spy_bars) < 2:
            raise DataError("Insufficient SPY data for session determination")
        
        # Get the last bar's date
        last_date = spy_bars.index[-1].date()
        today = datetime.now(self.timezone).date()
        
        # Partial-day guard: If the latest bar is today, use the previous session
        if last_date == today and len(spy_bars) >= 2:
            last_date = spy_bars.index[-2].date()
            logger.debug(f"Today's session incomplete, using previous: {last_date}")
        else:
            logger.debug(f"Last complete session: {last_date}")
        
        # Cache the result for the entire run
        self._cached_last_session = last_date
        return last_date
    
    def fetch_and_calculate(self, symbol: str) -> pd.DataFrame:
        """
        Main entry point: fetch data, trim to session, and calculate indicators.
        
        Args:
            symbol: Stock ticker symbol
            
        Returns:
            DataFrame with OHLCV data and calculated indicators
            
        Raises:
            DataError: If data is insufficient or invalid
        """
        logger.debug(f"Fetching and calculating indicators for {symbol}")
        
        # Determine date range
        end = datetime.now(self.timezone)
        start = end - timedelta(days=self.config['data']['days_history'])
        
        # Fetch data with retry logic
        df = self._fetch_bars_with_retry(symbol, start, end)
        
        if df.empty:
            logger.warning(f"No data returned for {symbol}")
            return df
        
        # Get last complete session
        last_session = self.get_last_complete_session()
        
        # Trim to last complete session
        df = self._trim_to_session(df, last_session)
        
        if df.empty:
            logger.warning(f"No data for {symbol} after session trim")
            return df
        
        # Calculate indicators
        df = self.calculate_indicators(df)
        
        # Add symbol column for tracking
        df['symbol'] = symbol
        
        return df
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate all technical indicators.
        
        Uses simple rolling means (not Wilder's smoothing) for consistency
        and simplicity. All volume averages exclude the current bar to
        avoid look-ahead bias.
        
        Args:
            df: DataFrame with OHLCV data
            
        Returns:
            DataFrame with added indicator columns
            
        Raises:
            DataError: If insufficient bars for calculation
        """
        min_bars = self.config['data']['min_bars_required']
        if len(df) < min_bars:
            raise DataError(f"Insufficient bars: {len(df)} < {min_bars}")
        
        periods = self.config['indicators']
        
        # Price-based indicators
        df['sma20'] = df['close'].rolling(periods['sma_short']).mean()
        df['sma50'] = df['close'].rolling(periods['sma_long']).mean()
        df['high20'] = df['high'].rolling(periods['sma_short']).max()
        
        # ATR (Average True Range) - FIXED row-wise calculation
        tr_parts = pd.concat([
            df['high'] - df['low'],
            (df['high'] - df['close'].shift(1)).abs(),
            (df['low'] - df['close'].shift(1)).abs()
        ], axis=1)
        df['tr'] = tr_parts.max(axis=1)
        df['atr20'] = df['tr'].rolling(periods['atr_period']).mean()
        
        # RSI (Relative Strength Index) using simple rolling mean
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(periods['rsi_period']).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(periods['rsi_period']).mean()
        
        # Prevent division by zero
        loss = loss.replace(0, 1e-10)
        rs = gain / loss
        df['rsi14'] = 100 - (100 / (1 + rs))
        
        # Volume metrics (shifted to exclude current bar)
        df['volume_avg_10d'] = df['volume'].shift(1).rolling(periods['volume_avg_period']).mean()
        df['dollar_volume'] = df['close'] * df['volume']
        df['dollar_volume_10d_avg'] = (
            df['dollar_volume'].shift(1).rolling(periods['volume_avg_period']).mean()
        )
        
        # Gap calculation on adjusted prices
        prev_close = df['close'].shift(1)
        # Prevent division by zero
        prev_close = prev_close.replace(0, 1e-10)
        df['gap_percent'] = ((df['open'] - prev_close).abs() / prev_close) * 100
        
        # Drop warmup rows with NaN values
        df = df.dropna()
        
        # Validate no NaN in the last row
        if df.empty:
            raise DataError("All data lost after indicator calculation")
        
        if df.iloc[-1].isna().any():
            raise DataError("NaN values in final bar after indicator calculation")
        
        return df
    
    def _fetch_bars_with_retry(self, symbol: str, start: datetime, end: datetime) -> pd.DataFrame:
        """
        Fetch bars with retry logic and exponential backoff.
        
        Args:
            symbol: Stock ticker symbol
            start: Start datetime
            end: End datetime
            
        Returns:
            DataFrame with OHLCV data
            
        Raises:
            Various exceptions based on failure type
        """
        last_exception = None
        
        for attempt in range(self.MAX_RETRIES):
            try:
                if attempt > 0:
                    wait_time = self.BACKOFF_BASE ** (attempt - 1)
                    logger.debug(
                        f"Retry {attempt}/{self.MAX_RETRIES} for {symbol}, "
                        f"waiting {wait_time}s"
                    )
                
                # Apply rate limit
                self.rate_limiter.acquire()
                
                # Fetch bars
                df = self._fetch_bars(symbol, start, end)
                
                # Validate response
                if not self._validate_dataframe(df):
                    raise DataError(f"Invalid data structure for {symbol}")
                
                return df
                
            except AlpacaAPIError as e:
                last_exception = e
                logger.debug(f"Attempt {attempt + 1}/{self.MAX_RETRIES} for {symbol}: API error {e.code if hasattr(e, 'code') else 'unknown'}")
                
                if hasattr(e, 'code'):
                    # Don't retry on auth/permission errors
                    if e.code in self.FAST_FAIL_CODES:
                        raise
                    
                    # Special handling for 422 (could be no data or bad params)
                    elif e.code == 422:
                        error_msg = str(e).lower()
                        if 'no data' in error_msg or 'not found' in error_msg:
                            raise DataError(f"No data available for {symbol}")
                        else:
                            raise  # Bad parameters, don't retry
                    
                    # Retry on rate limit and server errors
                    elif e.code in self.RETRY_STATUS_CODES:
                        if attempt < self.MAX_RETRIES - 1:
                            wait_time = self.BACKOFF_BASE ** attempt
                            time.sleep(wait_time)
                            continue
                    
                raise
                
            except NoDataAvailable:
                raise DataError(f"No data available for {symbol}")
                
            except (ConnectionError, TimeoutError) as e:
                last_exception = e
                logger.debug(f"Attempt {attempt + 1}/{self.MAX_RETRIES} for {symbol}: Network error")
                
                if attempt < self.MAX_RETRIES - 1:
                    wait_time = self.BACKOFF_BASE ** attempt
                    time.sleep(wait_time)
                    continue
                else:
                    raise
        
        # All retries exhausted
        logger.warning(f"Giving up on {symbol} after {self.MAX_RETRIES} attempts. Last error: {last_exception}")
        
        if last_exception:
            raise last_exception
        else:
            raise DataError(f"Failed to fetch {symbol} after {self.MAX_RETRIES} attempts")
    
    def _fetch_bars(self, symbol: str, start: datetime, end: datetime) -> pd.DataFrame:
        """
        Raw fetch from Alpaca API.
        
        Args:
            symbol: Stock ticker symbol
            start: Start datetime
            end: End datetime
            
        Returns:
            DataFrame with OHLCV data
            
        Raises:
            DataError: If response shape is unexpected
        """
        request = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=TimeFrame.Day,
            start=start,
            end=end,
            adjustment=Adjustment.ALL,  # Use adjusted prices
            feed=self.feed,
            asof=None,
            page_limit=None
        )
        
        bars = self.client.get_stock_bars(request)
        
        # Handle different response shapes from Alpaca SDK
        if hasattr(bars, 'df'):
            df = bars.df
        elif isinstance(bars, dict) and symbol in bars:
            df = bars[symbol]
        else:
            raise DataError(f"Unexpected response shape from Alpaca SDK for {symbol}")
        
        # Ensure timezone-aware index in the configured timezone
        if df.index.tz is None:
            df.index = df.index.tz_localize('UTC').tz_convert(self.timezone)
        elif df.index.tz != self.timezone:
            df.index = df.index.tz_convert(self.timezone)
        
        return df
    
    def _validate_dataframe(self, df: pd.DataFrame) -> bool:
        """
        Validate that DataFrame has expected OHLCV columns.
        
        Args:
            df: DataFrame to validate
            
        Returns:
            True if valid, False otherwise
        """
        if df.empty:
            return True  # Empty is valid, will be handled elsewhere
        
        required_columns = ['open', 'high', 'low', 'close', 'volume']
        return all(col in df.columns for col in required_columns)
    
    def _trim_to_session(self, df: pd.DataFrame, last_session: date) -> pd.DataFrame:
        """
        Trim DataFrame to last complete session.
        
        Args:
            df: DataFrame with time series data
            last_session: Date of last complete session
            
        Returns:
            Trimmed DataFrame
        """
        if df.empty:
            return df
        
        # Keep only rows up to and including the last complete session
        mask = df.index.date <= last_session
        trimmed = df[mask]
        
        if len(trimmed) < len(df):
            logger.debug(f"Trimmed {len(df) - len(trimmed)} bars after session {last_session}")
        
        return trimmed