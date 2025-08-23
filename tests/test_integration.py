"""Integration tests for the SwingTrading scanner."""

import subprocess
import sys
from pathlib import Path

import pytest


def test_cli_help():
    """Test that CLI help works."""
    result = subprocess.run(
        [sys.executable, '-m', 'swingtrading.main', '--help'],
        capture_output=True,
        text=True
    )
    
    assert result.returncode == 0
    assert 'swing trading scanner' in result.stdout.lower()
    assert '--ticker' in result.stdout
    assert '--debug' in result.stdout


def test_cli_version():
    """Test that version command works."""
    result = subprocess.run(
        [sys.executable, '-m', 'swingtrading.main', 'version'],
        capture_output=True,
        text=True
    )
    
    assert result.returncode == 0
    assert 'SwingTrading Scanner' in result.stdout
    assert '1.0.0' in result.stdout


def test_config_validation():
    """Test that invalid config is caught."""
    # Create a minimal invalid config
    import tempfile
    import yaml
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        # Write invalid config (missing required sections)
        yaml.dump({'invalid': 'config'}, f)
        config_path = f.name
    
    try:
        result = subprocess.run(
            [sys.executable, '-m', 'swingtrading.main', 'scan', '--config-file', config_path, '--dry-run'],
            capture_output=True,
            text=True
        )
        
        # Should fail with config error (exit code 2)
        assert result.returncode == 2
        assert 'Configuration error' in result.stderr or 'Missing required' in result.stderr
        
    finally:
        Path(config_path).unlink()


def test_dry_run():
    """Test that dry run validates without scanning."""
    # Check if config.yaml exists
    config_path = Path(__file__).parent.parent / 'config.yaml'
    if not config_path.exists():
        pytest.skip("config.yaml not found")
    
    result = subprocess.run(
        [sys.executable, '-m', 'swingtrading.main', 'scan', '--dry-run'],
        capture_output=True,
        text=True,
        cwd=config_path.parent
    )
    
    # Should succeed with dry run message
    assert result.returncode == 0
    assert 'dry run' in result.stdout.lower() or 'configuration valid' in result.stdout.lower()