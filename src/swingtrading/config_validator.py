"""Configuration validation and normalization for SwingTrading scanner."""

import logging
from typing import Dict, Any, List

from .exceptions import ConfigError

logger = logging.getLogger(__name__)


def validate_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate and normalize the configuration.
    
    This function checks all required fields, validates ranges,
    normalizes tickers, and auto-adjusts certain parameters.
    
    Args:
        config: Raw configuration dictionary
        
    Returns:
        Validated and normalized configuration
        
    Raises:
        ConfigError: If configuration is invalid
    """
    # Check required top-level sections
    required_sections = ['universe', 'data', 'filters', 'indicators', 'scoring', 'output', 'regime']
    for section in required_sections:
        if section not in config:
            raise ConfigError(f"Missing required configuration section: {section}")
    
    # Validate and normalize universe
    config = _validate_universe(config)
    
    # Validate data settings
    config = _validate_data_settings(config)
    
    # Validate filters
    config = _validate_filters(config)
    
    # Validate indicators
    config = _validate_indicators(config)
    
    # Validate scoring weights
    config = _validate_scoring(config)
    
    # Validate output settings
    config = _validate_output(config)
    
    # Validate regime settings
    config = _validate_regime(config)
    
    return config


def _validate_universe(config: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and normalize universe settings."""
    if 'tickers' not in config['universe']:
        raise ConfigError("Missing 'tickers' in universe configuration")
    
    tickers = config['universe']['tickers']
    if not isinstance(tickers, list):
        raise ConfigError("Universe tickers must be a list")
    
    if not tickers:
        raise ConfigError("Universe tickers list cannot be empty")
    
    # Normalize tickers: uppercase and deduplicate while preserving order
    seen = set()
    normalized = []
    for ticker in tickers:
        if not isinstance(ticker, str):
            raise ConfigError(f"Ticker must be a string, got {type(ticker)}")
        
        ticker_upper = ticker.upper().strip()
        if not ticker_upper:
            raise ConfigError("Ticker cannot be empty")
        
        if ticker_upper not in seen:
            seen.add(ticker_upper)
            normalized.append(ticker_upper)
    
    config['universe']['tickers'] = normalized
    logger.debug(f"Normalized {len(tickers)} tickers to {len(normalized)} unique tickers")
    
    return config


def _validate_data_settings(config: Dict[str, Any]) -> Dict[str, Any]:
    """Validate data configuration settings."""
    data = config['data']
    
    # Required fields
    required_fields = [
        'api_key_env', 'api_secret_env', 'base_url', 'feed', 'timezone',
        'days_history', 'min_bars_required', 'rate_limit_per_minute',
        'max_workers', 'task_timeout'
    ]
    
    for field in required_fields:
        if field not in data:
            raise ConfigError(f"Missing required data field: {field}")
    
    # Validate feed
    valid_feeds = ['iex', 'sip', 'otc']
    if data['feed'].lower() not in valid_feeds:
        raise ConfigError(f"Invalid feed: {data['feed']}. Must be one of {valid_feeds}")
    
    # Validate numeric ranges
    if data['days_history'] < 1:
        raise ConfigError("days_history must be at least 1")
    
    if data['rate_limit_per_minute'] < 1 or data['rate_limit_per_minute'] > 200:
        raise ConfigError("rate_limit_per_minute must be between 1 and 200")
    
    if data['max_workers'] < 1:
        raise ConfigError("max_workers must be at least 1")
    
    if data['task_timeout'] < 1:
        raise ConfigError("task_timeout must be at least 1 second")
    
    # Set default for rate_limit_start_full if not present
    if 'rate_limit_start_full' not in data:
        data['rate_limit_start_full'] = False
    
    return config


def _validate_indicators(config: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and auto-adjust indicator settings."""
    indicators = config['indicators']
    
    # Required fields
    required_fields = ['atr_period', 'rsi_period', 'sma_short', 'sma_long', 'volume_avg_period']
    for field in required_fields:
        if field not in indicators:
            raise ConfigError(f"Missing required indicator: {field}")
        
        if indicators[field] < 1:
            raise ConfigError(f"Indicator period {field} must be at least 1")
    
    # Auto-adjust min_bars_required if needed
    requirements = {
        'sma_long': indicators['sma_long'],
        'atr_warmup': indicators['atr_period'] + 20,
        'rsi_warmup': indicators['rsi_period'] + 20,
    }
    
    min_needed = max(requirements.values())
    limiting_factor = max(requirements, key=requirements.get)
    
    if config['data']['min_bars_required'] < min_needed:
        old_value = config['data']['min_bars_required']
        config['data']['min_bars_required'] = min_needed
        logger.info(
            f"Adjusted min_bars_required from {old_value} to {min_needed} "
            f"(required by {limiting_factor})"
        )
    
    return config


def _validate_filters(config: Dict[str, Any]) -> Dict[str, Any]:
    """Validate filter settings."""
    filters = config['filters']
    
    # Validate price filters
    if 'min_price' not in filters:
        filters['min_price'] = 0.0
    if filters['min_price'] < 0:
        raise ConfigError("min_price cannot be negative")
    
    if 'penny_threshold' not in filters:
        filters['penny_threshold'] = 1.0
    if filters['penny_threshold'] < 0:
        raise ConfigError("penny_threshold cannot be negative")
    
    # Validate liquidity filter
    if 'min_dollar_volume_10d_avg' not in filters:
        filters['min_dollar_volume_10d_avg'] = 0
    if filters['min_dollar_volume_10d_avg'] < 0:
        raise ConfigError("min_dollar_volume_10d_avg cannot be negative")
    
    # Validate volatility filters
    if 'min_atr_ratio' not in filters:
        filters['min_atr_ratio'] = 0.0
    if not 0 <= filters['min_atr_ratio'] <= 1:
        raise ConfigError("min_atr_ratio must be between 0 and 1")
    
    if 'max_gap_percent' not in filters:
        filters['max_gap_percent'] = 100.0
    if filters['max_gap_percent'] < 0:
        raise ConfigError("max_gap_percent cannot be negative")
    
    # Validate leveraged ETF patterns
    if 'leveraged_etf_patterns' not in filters:
        filters['leveraged_etf_patterns'] = []
    elif not isinstance(filters['leveraged_etf_patterns'], list):
        raise ConfigError("leveraged_etf_patterns must be a list")
    
    return config


def _validate_scoring(config: Dict[str, Any]) -> Dict[str, Any]:
    """Validate scoring weights."""
    if 'weights' not in config['scoring']:
        raise ConfigError("Missing weights in scoring configuration")
    
    weights = config['scoring']['weights']
    required_weights = ['pullback_proximity', 'trend_strength', 'rsi_headroom', 'volume_ratio']
    
    for weight_name in required_weights:
        if weight_name not in weights:
            raise ConfigError(f"Missing scoring weight: {weight_name}")
        
        if weights[weight_name] < 0:
            raise ConfigError(f"Scoring weight {weight_name} cannot be negative")
    
    # Warn if weights don't sum to approximately 1.0
    weight_sum = sum(weights.values())
    if abs(weight_sum - 1.0) > 0.01:
        logger.warning(
            f"Scoring weights sum to {weight_sum:.3f} instead of 1.0. "
            "Weights will be normalized during scoring."
        )
    
    return config


def _validate_output(config: Dict[str, Any]) -> Dict[str, Any]:
    """Validate output settings."""
    if 'csv_columns' not in config['output']:
        raise ConfigError("Missing csv_columns in output configuration")
    
    csv_columns = config['output']['csv_columns']
    if not isinstance(csv_columns, list):
        raise ConfigError("csv_columns must be a list")
    
    if not csv_columns:
        raise ConfigError("csv_columns cannot be empty")
    
    # Ensure required columns are present
    required_columns = ['symbol', 'close', 'score']
    for col in required_columns:
        if col not in csv_columns:
            logger.warning(f"Adding required column '{col}' to csv_columns")
            csv_columns.append(col)
    
    return config


def _validate_regime(config: Dict[str, Any]) -> Dict[str, Any]:
    """Validate regime filter settings."""
    regime = config['regime']
    
    if 'check_spy' not in regime:
        regime['check_spy'] = True
    
    if 'spy_rsi_threshold' not in regime:
        regime['spy_rsi_threshold'] = 30
    
    if not 0 <= regime['spy_rsi_threshold'] <= 100:
        raise ConfigError("spy_rsi_threshold must be between 0 and 100")
    
    return config