"""Tests for configuration validation."""

import pytest
from swingtrading.config_validator import validate_config
from swingtrading.exceptions import ConfigError


def test_universe_normalization():
    """Test that tickers are uppercased and deduplicated while preserving order."""
    config = {
        'universe': {
            'tickers': ['aapl', 'MSFT', 'googl', 'aapl', 'NVDA']
        },
        'data': {
            'api_key_env': 'KEY',
            'api_secret_env': 'SECRET',
            'base_url': 'https://test.com',
            'feed': 'iex',
            'timezone': 'America/New_York',
            'days_history': 252,
            'min_bars_required': 100,
            'rate_limit_per_minute': 190,
            'max_workers': 10,
            'task_timeout': 30
        },
        'filters': {},
        'indicators': {
            'atr_period': 20,
            'rsi_period': 14,
            'sma_short': 20,
            'sma_long': 50,
            'volume_avg_period': 10
        },
        'scoring': {
            'weights': {
                'pullback_proximity': 0.30,
                'trend_strength': 0.25,
                'rsi_headroom': 0.25,
                'volume_ratio': 0.20
            }
        },
        'output': {
            'csv_columns': ['symbol', 'close', 'score']
        },
        'regime': {
            'check_spy': True,
            'spy_rsi_threshold': 30
        }
    }
    
    validated = validate_config(config)
    
    # Should be uppercased, deduplicated, order preserved
    expected = ['AAPL', 'MSFT', 'GOOGL', 'NVDA']
    assert validated['universe']['tickers'] == expected


def test_weight_validation():
    """Test that negative weights are rejected."""
    config = {
        'universe': {'tickers': ['SPY']},
        'data': {
            'api_key_env': 'KEY',
            'api_secret_env': 'SECRET',
            'base_url': 'https://test.com',
            'feed': 'iex',
            'timezone': 'America/New_York',
            'days_history': 252,
            'min_bars_required': 100,
            'rate_limit_per_minute': 190,
            'max_workers': 10,
            'task_timeout': 30
        },
        'filters': {},
        'indicators': {
            'atr_period': 20,
            'rsi_period': 14,
            'sma_short': 20,
            'sma_long': 50,
            'volume_avg_period': 10
        },
        'scoring': {
            'weights': {
                'pullback_proximity': -0.30,  # Negative weight
                'trend_strength': 0.25,
                'rsi_headroom': 0.25,
                'volume_ratio': 0.20
            }
        },
        'output': {
            'csv_columns': ['symbol', 'close', 'score']
        },
        'regime': {}
    }
    
    with pytest.raises(ConfigError, match="cannot be negative"):
        validate_config(config)


def test_min_bars_auto_adjustment():
    """Test that min_bars_required is auto-adjusted when too low."""
    config = {
        'universe': {'tickers': ['SPY']},
        'data': {
            'api_key_env': 'KEY',
            'api_secret_env': 'SECRET',
            'base_url': 'https://test.com',
            'feed': 'iex',
            'timezone': 'America/New_York',
            'days_history': 252,
            'min_bars_required': 10,  # Too low
            'rate_limit_per_minute': 190,
            'max_workers': 10,
            'task_timeout': 30
        },
        'filters': {},
        'indicators': {
            'atr_period': 20,
            'rsi_period': 14,
            'sma_short': 20,
            'sma_long': 50,  # Requires at least 50 bars
            'volume_avg_period': 10
        },
        'scoring': {
            'weights': {
                'pullback_proximity': 0.30,
                'trend_strength': 0.25,
                'rsi_headroom': 0.25,
                'volume_ratio': 0.20
            }
        },
        'output': {
            'csv_columns': ['symbol', 'close', 'score']
        },
        'regime': {}
    }
    
    validated = validate_config(config)
    
    # Should be adjusted to at least 50 (sma_long)
    assert validated['data']['min_bars_required'] >= 50


def test_invalid_feed():
    """Test that invalid feed is rejected."""
    config = {
        'universe': {'tickers': ['SPY']},
        'data': {
            'api_key_env': 'KEY',
            'api_secret_env': 'SECRET',
            'base_url': 'https://test.com',
            'feed': 'invalid_feed',  # Invalid
            'timezone': 'America/New_York',
            'days_history': 252,
            'min_bars_required': 100,
            'rate_limit_per_minute': 190,
            'max_workers': 10,
            'task_timeout': 30
        },
        'filters': {},
        'indicators': {
            'atr_period': 20,
            'rsi_period': 14,
            'sma_short': 20,
            'sma_long': 50,
            'volume_avg_period': 10
        },
        'scoring': {
            'weights': {
                'pullback_proximity': 0.30,
                'trend_strength': 0.25,
                'rsi_headroom': 0.25,
                'volume_ratio': 0.20
            }
        },
        'output': {
            'csv_columns': ['symbol', 'close', 'score']
        },
        'regime': {}
    }
    
    with pytest.raises(ConfigError, match="Invalid feed"):
        validate_config(config)


def test_missing_required_section():
    """Test that missing required sections are caught."""
    config = {
        'universe': {'tickers': ['SPY']},
        'data': {
            'api_key_env': 'KEY',
            'api_secret_env': 'SECRET',
            'base_url': 'https://test.com',
            'feed': 'iex',
            'timezone': 'America/New_York',
            'days_history': 252,
            'min_bars_required': 100,
            'rate_limit_per_minute': 190,
            'max_workers': 10,
            'task_timeout': 30
        },
        # Missing filters, indicators, scoring, output, regime
    }
    
    with pytest.raises(ConfigError, match="Missing required configuration section"):
        validate_config(config)