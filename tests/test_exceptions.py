"""Tests for exception mapping."""

import pytest
from concurrent.futures import TimeoutError as FuturesTimeoutError

from swingtrading.exceptions import (
    ExceptionMapper,
    ConfigError,
    DataError,
    EXIT_SUCCESS,
    EXIT_GENERAL_ERROR,
    EXIT_CONFIG_ERROR,
    EXIT_NETWORK_ERROR,
    EXIT_DATA_ERROR
)


def test_config_error_mapping():
    """Test that ConfigError maps to EXIT_CONFIG_ERROR."""
    error = ConfigError("Invalid configuration")
    exit_code = ExceptionMapper.map_to_exit_code(error)
    assert exit_code == EXIT_CONFIG_ERROR


def test_data_error_mapping():
    """Test that DataError maps to EXIT_DATA_ERROR."""
    error = DataError("No data available")
    exit_code = ExceptionMapper.map_to_exit_code(error)
    assert exit_code == EXIT_DATA_ERROR


def test_futures_timeout_mapping():
    """Test that concurrent.futures.TimeoutError maps to EXIT_NETWORK_ERROR."""
    error = FuturesTimeoutError("Task timed out")
    exit_code = ExceptionMapper.map_to_exit_code(error)
    assert exit_code == EXIT_NETWORK_ERROR


def test_connection_error_mapping():
    """Test that ConnectionError maps to EXIT_NETWORK_ERROR."""
    error = ConnectionError("Network connection failed")
    exit_code = ExceptionMapper.map_to_exit_code(error)
    assert exit_code == EXIT_NETWORK_ERROR


def test_timeout_error_mapping():
    """Test that built-in TimeoutError maps to EXIT_NETWORK_ERROR."""
    error = TimeoutError("Request timed out")
    exit_code = ExceptionMapper.map_to_exit_code(error)
    assert exit_code == EXIT_NETWORK_ERROR


def test_value_error_invalid_feed():
    """Test that ValueError with 'Invalid feed' maps to EXIT_CONFIG_ERROR."""
    error = ValueError("Invalid feed: xyz")
    exit_code = ExceptionMapper.map_to_exit_code(error)
    assert exit_code == EXIT_CONFIG_ERROR


def test_value_error_unexpected_response():
    """Test that ValueError with 'Unexpected response shape' maps to EXIT_DATA_ERROR."""
    error = ValueError("Unexpected response shape from SDK")
    exit_code = ExceptionMapper.map_to_exit_code(error)
    assert exit_code == EXIT_DATA_ERROR


def test_generic_value_error():
    """Test that generic ValueError maps to EXIT_CONFIG_ERROR."""
    error = ValueError("Some other error")
    exit_code = ExceptionMapper.map_to_exit_code(error)
    assert exit_code == EXIT_CONFIG_ERROR


def test_key_error_mapping():
    """Test that KeyError maps to EXIT_CONFIG_ERROR."""
    error = KeyError("missing_key")
    exit_code = ExceptionMapper.map_to_exit_code(error)
    assert exit_code == EXIT_CONFIG_ERROR


def test_generic_exception_mapping():
    """Test that generic exceptions map to EXIT_GENERAL_ERROR."""
    error = RuntimeError("Unexpected error")
    exit_code = ExceptionMapper.map_to_exit_code(error)
    assert exit_code == EXIT_GENERAL_ERROR


def test_alpaca_import_handling():
    """Test that mapper handles missing Alpaca imports gracefully."""
    # This should not raise even if Alpaca is not installed
    error = RuntimeError("Some error")
    exit_code = ExceptionMapper.map_to_exit_code(error)
    assert exit_code == EXIT_GENERAL_ERROR