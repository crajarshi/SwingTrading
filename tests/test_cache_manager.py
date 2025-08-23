"""Tests for cache management."""

import tempfile
from datetime import datetime, date, timedelta
from pathlib import Path

import pandas as pd
import pytz
import pytest

from swingtrading.cache_manager import CacheManager


@pytest.fixture
def temp_cache_dir():
    """Create a temporary directory for cache testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def cache_manager(temp_cache_dir):
    """Create a cache manager with temporary directory."""
    return CacheManager(temp_cache_dir, 'America/New_York')


def test_cache_read_empty(cache_manager):
    """Test reading non-existent cache returns empty DataFrame."""
    df = cache_manager.read('NONEXISTENT')
    assert df.empty


def test_cache_write_and_read(cache_manager):
    """Test writing and reading cache."""
    # Create test data
    tz = pytz.timezone('America/New_York')
    dates = pd.date_range('2024-01-01', periods=5, tz=tz)
    df = pd.DataFrame({
        'open': [100, 101, 102, 103, 104],
        'high': [105, 106, 107, 108, 109],
        'low': [95, 96, 97, 98, 99],
        'close': [102, 103, 104, 105, 106],
        'volume': [1000, 1100, 1200, 1300, 1400]
    }, index=dates)
    
    # Write cache
    cache_manager.write('TEST', df)
    
    # Read back
    loaded = cache_manager.read('TEST')
    
    # Should be identical
    pd.testing.assert_frame_equal(df, loaded)


def test_cache_atomic_write(cache_manager, temp_cache_dir):
    """Test that cache write is atomic (no partial files on failure)."""
    # Create test data
    tz = pytz.timezone('America/New_York')
    dates = pd.date_range('2024-01-01', periods=5, tz=tz)
    df = pd.DataFrame({'close': [100, 101, 102, 103, 104]}, index=dates)
    
    # Mock to_parquet to fail
    original_to_parquet = pd.DataFrame.to_parquet
    
    def failing_to_parquet(self, path, **kwargs):
        # Create the temp file then fail
        path = Path(path)
        path.touch()
        raise Exception("Simulated write failure")
    
    pd.DataFrame.to_parquet = failing_to_parquet
    
    try:
        # Try to write (should fail)
        with pytest.raises(Exception, match="Simulated write failure"):
            cache_manager.write('TEST', df)
        
        # Check that no files remain
        cache_dir = Path(temp_cache_dir)
        parquet_files = list(cache_dir.glob('*.parquet'))
        tmp_files = list(cache_dir.glob('*.tmp'))
        
        assert len(parquet_files) == 0, "Final parquet file should not exist"
        assert len(tmp_files) == 0, "Temp file should be cleaned up"
        
    finally:
        # Restore original method
        pd.DataFrame.to_parquet = original_to_parquet


def test_cache_is_current(cache_manager):
    """Test cache freshness checking."""
    # Create test data
    tz = pytz.timezone('America/New_York')
    last_session = date(2024, 1, 15)
    
    # Create cache with data up to last session
    dates = pd.date_range('2024-01-10', '2024-01-15', tz=tz)
    df = pd.DataFrame({'close': range(len(dates))}, index=dates)
    cache_manager.write('TEST', df)
    
    # Should be current
    assert cache_manager.is_cache_current('TEST', last_session) == True
    
    # Should not be current for a later session
    assert cache_manager.is_cache_current('TEST', date(2024, 1, 16)) == False
    
    # Should not be current for non-existent symbol
    assert cache_manager.is_cache_current('NONEXISTENT', last_session) == False


def test_cache_dedupe_by_date(cache_manager):
    """Test deduplication by date keeps last entry."""
    tz = pytz.timezone('America/New_York')
    
    # Create data with duplicates on same date
    df = pd.DataFrame({
        'close': [100, 101, 102],
        'volume': [1000, 2000, 3000]
    }, index=pd.to_datetime([
        '2024-01-15 09:30:00',
        '2024-01-15 16:00:00',  # Same date, different time
        '2024-01-16 09:30:00'
    ]).tz_localize('UTC').tz_convert(tz))
    
    # Deduplicate
    result = cache_manager.dedupe_by_date(df)
    
    # Should have 2 rows (one per unique date)
    assert len(result) == 2
    
    # Should keep the last entry for 2024-01-15 (close=101)
    jan15_row = result[result.index.date == date(2024, 1, 15)]
    assert len(jan15_row) == 1
    assert jan15_row.iloc[0]['close'] == 101


def test_cache_trim_to_session(cache_manager):
    """Test trimming to last complete session."""
    tz = pytz.timezone('America/New_York')
    last_session = date(2024, 1, 15)
    
    # Create data extending beyond last session
    dates = pd.date_range('2024-01-10', '2024-01-17', tz=tz)
    df = pd.DataFrame({'close': range(len(dates))}, index=dates)
    
    # Trim to session
    trimmed = cache_manager.trim_to_session(df, last_session)
    
    # Should only include data up to last session
    assert trimmed.index[-1].date() == last_session
    assert all(d.date() <= last_session for d in trimmed.index)


def test_cache_timezone_consistency(cache_manager):
    """Test that timezone is preserved correctly."""
    # Create data in different timezone
    dates = pd.date_range('2024-01-01', periods=5, tz='Europe/London')
    df = pd.DataFrame({'close': [100, 101, 102, 103, 104]}, index=dates)
    
    # Write cache
    cache_manager.write('TEST', df)
    
    # Read back
    loaded = cache_manager.read('TEST')
    
    # Should be converted to America/New_York
    assert loaded.index.tz.zone == 'America/New_York'
    
    # Data should still be there
    assert len(loaded) == 5


def test_cache_thread_safety(cache_manager):
    """Test that per-symbol locks prevent race conditions."""
    import threading
    
    tz = pytz.timezone('America/New_York')
    writes_completed = []
    
    def write_data(symbol, value):
        dates = pd.date_range('2024-01-01', periods=5, tz=tz)
        df = pd.DataFrame({'close': [value] * 5}, index=dates)
        cache_manager.write(symbol, df)
        writes_completed.append(symbol)
    
    # Start multiple threads writing to same symbol
    threads = []
    for i in range(5):
        t = threading.Thread(target=write_data, args=('TEST', i))
        threads.append(t)
        t.start()
    
    # Wait for all to complete
    for t in threads:
        t.join()
    
    # All writes should complete
    assert len(writes_completed) == 5
    
    # File should exist and be readable
    df = cache_manager.read('TEST')
    assert not df.empty