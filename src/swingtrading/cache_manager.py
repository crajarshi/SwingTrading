"""Cache management for storing and retrieving market data."""

import threading
import logging
from datetime import date
from pathlib import Path
from typing import Optional, Dict

import pandas as pd
import pytz

logger = logging.getLogger(__name__)


class CacheManager:
    """
    Manages local cache of market data using Parquet files.
    
    Features:
    - Per-symbol file locking for thread safety
    - Atomic writes to prevent corruption
    - Timezone-aware data handling
    - Session-based freshness checking
    """
    
    def __init__(self, cache_dir: str, timezone: str):
        """
        Initialize the cache manager.
        
        Args:
            cache_dir: Directory path for cache files
            timezone: Timezone string (e.g., 'America/New_York')
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Per-symbol locks for thread safety
        self._locks: Dict[str, threading.Lock] = {}
        self._lock_mutex = threading.Lock()
        
        # Timezone from config (ensures consistency with DataProvider)
        self.timezone = pytz.timezone(timezone)
        
        logger.debug(f"Cache manager initialized with directory: {self.cache_dir}")
    
    def _get_lock(self, symbol: str) -> threading.Lock:
        """
        Get or create a lock for a specific symbol.
        
        Args:
            symbol: Stock ticker symbol
            
        Returns:
            Lock object for the symbol
        """
        with self._lock_mutex:
            if symbol not in self._locks:
                self._locks[symbol] = threading.Lock()
            return self._locks[symbol]
    
    def read(self, symbol: str) -> pd.DataFrame:
        """
        Read cached data for a symbol.
        
        Args:
            symbol: Stock ticker symbol
            
        Returns:
            DataFrame with cached data, or empty DataFrame if no cache exists
        """
        filepath = self.cache_dir / f"{symbol}.parquet"
        
        if not filepath.exists():
            logger.debug(f"No cache found for {symbol}")
            return pd.DataFrame()
        
        try:
            df = pd.read_parquet(filepath)
            
            # Ensure timezone-aware index
            if df.index.tz is None:
                df.index = df.index.tz_localize('UTC').tz_convert(self.timezone)
            elif df.index.tz != self.timezone:
                df.index = df.index.tz_convert(self.timezone)
            
            logger.debug(f"Loaded {len(df)} cached bars for {symbol}")
            return df
            
        except Exception as e:
            logger.warning(f"Error reading cache for {symbol}: {e}")
            return pd.DataFrame()
    
    def write(self, symbol: str, df: pd.DataFrame) -> None:
        """
        Write data to cache with atomic operation.
        
        Uses a temporary file and atomic rename to prevent
        partial writes from corrupting the cache.
        
        Args:
            symbol: Stock ticker symbol
            df: DataFrame to cache
        """
        if df.empty:
            logger.debug(f"Skipping cache write for {symbol} (empty data)")
            return
        
        lock = self._get_lock(symbol)
        
        with lock:
            filepath = self.cache_dir / f"{symbol}.parquet"
            temp_path = filepath.with_suffix('.tmp')
            
            try:
                # Write to temporary file first
                df.to_parquet(temp_path, compression='snappy')
                
                # Atomic rename (on same filesystem)
                temp_path.replace(filepath)
                
                logger.debug(f"Cached {len(df)} bars for {symbol}")
                
            except Exception as e:
                logger.error(f"Error writing cache for {symbol}: {e}")
                
                # Clean up temporary file on failure
                if temp_path.exists():
                    try:
                        temp_path.unlink()
                    except:
                        pass  # Best effort cleanup
                
                raise
    
    def is_cache_current(self, symbol: str, last_session: date) -> bool:
        """
        Check if cached data is current for the last complete session.
        
        Cache is considered current if its last date equals the
        last complete trading session.
        
        Args:
            symbol: Stock ticker symbol
            last_session: Date of last complete trading session
            
        Returns:
            True if cache is current, False otherwise
        """
        cached_df = self.read(symbol)
        
        if cached_df.empty:
            return False
        
        # Get the last date in cache
        cache_last_date = cached_df.index[-1].date()
        
        # Cache is current if it includes the last complete session
        is_current = cache_last_date == last_session
        
        logger.debug(
            f"Cache for {symbol}: last_date={cache_last_date}, "
            f"session={last_session}, current={is_current}"
        )
        
        return is_current
    
    def trim_to_session(self, df: pd.DataFrame, last_session: date) -> pd.DataFrame:
        """
        Trim DataFrame to last complete session.
        
        This method is used by tests and can be used to ensure
        data doesn't include incomplete sessions.
        
        Args:
            df: DataFrame with time series data
            last_session: Date of last complete session
            
        Returns:
            Trimmed DataFrame
        """
        if df.empty:
            return df
        
        # Keep only data up to and including last session
        mask = df.index.date <= last_session
        return df[mask]
    
    def dedupe_by_date(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Deduplicate DataFrame keeping last entry per date.
        
        This handles cases where the same date might have multiple
        entries due to data corrections or timezone issues.
        
        Args:
            df: DataFrame to deduplicate
            
        Returns:
            Deduplicated DataFrame
        """
        if df.empty:
            return df
        
        # Create a copy to avoid modifying original
        df = df.copy()
        
        # Add temporary date column
        df['_date'] = df.index.date
        
        # Keep last row per date
        df = df.drop_duplicates(subset=['_date'], keep='last')
        
        # Remove helper column and sort by index
        df = df.drop(columns=['_date']).sort_index()
        
        return df
    
    def merge_with_cache(self, symbol: str, new_df: pd.DataFrame, last_session: date) -> pd.DataFrame:
        """
        Merge new data with existing cache.
        
        This method combines cached and new data, deduplicates by date,
        and trims to the last complete session.
        
        Args:
            symbol: Stock ticker symbol
            new_df: New data to merge
            last_session: Date of last complete session
            
        Returns:
            Merged and cleaned DataFrame
        """
        cached_df = self.read(symbol)
        
        if not cached_df.empty:
            # Combine cache and new data
            combined = pd.concat([cached_df, new_df])
            
            # Deduplicate by date
            combined = self.dedupe_by_date(combined)
            
            # Trim to last complete session
            combined = self.trim_to_session(combined, last_session)
            
            logger.debug(
                f"Merged cache for {symbol}: "
                f"{len(cached_df)} cached + {len(new_df)} new = {len(combined)} total"
            )
            
            return combined
        else:
            # No cache, just trim new data
            trimmed = self.trim_to_session(new_df, last_session)
            logger.debug(f"No cache for {symbol}, using {len(trimmed)} new bars")
            return trimmed
    
    def clear_cache(self, symbol: Optional[str] = None) -> None:
        """
        Clear cache for a specific symbol or all symbols.
        
        Args:
            symbol: Specific symbol to clear, or None to clear all
        """
        if symbol:
            # Clear specific symbol
            filepath = self.cache_dir / f"{symbol}.parquet"
            if filepath.exists():
                lock = self._get_lock(symbol)
                with lock:
                    filepath.unlink()
                    logger.info(f"Cleared cache for {symbol}")
        else:
            # Clear all cache files
            for filepath in self.cache_dir.glob("*.parquet"):
                symbol = filepath.stem
                lock = self._get_lock(symbol)
                with lock:
                    filepath.unlink()
            
            logger.info("Cleared all cache files")
    
    def get_cache_stats(self) -> Dict[str, int]:
        """
        Get statistics about cached data.
        
        Returns:
            Dictionary with cache statistics
        """
        stats = {
            'total_files': 0,
            'total_bars': 0,
            'total_size_bytes': 0
        }
        
        for filepath in self.cache_dir.glob("*.parquet"):
            stats['total_files'] += 1
            stats['total_size_bytes'] += filepath.stat().st_size
            
            try:
                df = pd.read_parquet(filepath)
                stats['total_bars'] += len(df)
            except:
                pass  # Skip corrupted files
        
        return stats