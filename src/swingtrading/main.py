"""Main CLI entry point for the SwingTrading scanner."""

import sys
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

import yaml
import typer
from rich.console import Console
from dotenv import load_dotenv

# Relative imports for package
from .config_validator import validate_config
from .rate_limiter import TokenBucket
from .data_provider import DataProvider
from .cache_manager import CacheManager
from .scanner import Scanner
from .reporter import Reporter
from .exceptions import (
    ExceptionMapper,
    ConfigError,
    DataError,
    EXIT_SUCCESS,
    EXIT_GENERAL_ERROR,
    EXIT_CONFIG_ERROR,
    EXIT_NETWORK_ERROR,
    EXIT_DATA_ERROR
)

# Load environment variables
load_dotenv()

# Initialize Typer app
app = typer.Typer(
    name="swing-scan",
    help="Production-ready swing trading scanner for market analysis.",
    add_completion=False
)

# Initialize console for output
console = Console()

# Configure logging
def setup_logging(debug: bool = False):
    """Configure logging based on debug flag."""
    level = logging.DEBUG if debug else logging.INFO
    
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Reduce noise from third-party libraries
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('alpaca').setLevel(logging.WARNING)


def load_config(filepath: str) -> dict:
    """
    Load and validate configuration file.
    
    Args:
        filepath: Path to configuration YAML file
        
    Returns:
        Validated configuration dictionary
        
    Raises:
        ConfigError: If configuration is invalid
    """
    try:
        with open(filepath, 'r') as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        raise ConfigError(f"Configuration file not found: {filepath}")
    except yaml.YAMLError as e:
        raise ConfigError(f"Invalid YAML in configuration file: {e}")
    
    # Validate and normalize configuration
    config = validate_config(config)
    
    return config


def print_header(config: dict, regime_status: dict, ignore_regime: bool):
    """Print scan header with configuration information."""
    
    # Effective price floor
    min_price = config['filters'].get('min_price', 0)
    penny = config['filters'].get('penny_threshold', 0)
    effective = max(min_price, penny)
    console.print(f"\n[bold]Configuration:[/bold]")
    console.print(f"  • Effective min price: ${effective:.2f} (max of ${min_price:.2f}, ${penny:.2f})")
    
    # Rate limiting info
    rpm = config['data']['rate_limit_per_minute']
    workers = config['data']['max_workers']
    start_full = config['data'].get('rate_limit_start_full', False)
    console.print(f"  • Rate limit: {rpm} requests/min, {workers} workers")
    console.print(f"  • Token bucket: {'Starting full' if start_full else 'Starting empty (safer)'}")
    
    # Data feed
    console.print(f"  • Data feed: {config['data']['feed'].upper()}")
    console.print(f"  • Timezone: {config['data']['timezone']}")
    
    # Regime status
    if ignore_regime:
        console.print("\n[bold yellow]⚠️  REGIME FILTER BYPASSED[/bold yellow]")
    elif regime_status:
        spy_rsi = regime_status.get('spy_rsi', 'N/A')
        threshold = regime_status.get('threshold', 30)
        
        if isinstance(spy_rsi, (int, float)):
            status = "ACTIVE" if spy_rsi >= threshold else "BLOCKED"
            console.print(f"\n[bold]Market Regime:[/bold]")
            console.print(f"  • SPY RSI: {spy_rsi:.1f}")
            console.print(f"  • Threshold: {threshold}")
            console.print(f"  • Status: {status}")


@app.command()
def scan(
    config_file: str = typer.Option(
        "config.yaml",
        "--config-file", "-c",
        help="Path to configuration file"
    ),
    ticker: Optional[str] = typer.Option(
        None,
        "--ticker", "-t",
        help="Single ticker override (ignores universe)"
    ),
    ignore_regime: bool = typer.Option(
        False,
        "--ignore-regime",
        help="Bypass regime filter"
    ),
    no_progress: bool = typer.Option(
        False,
        "--no-progress",
        help="Disable progress bar"
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Validate configuration only"
    ),
    debug: bool = typer.Option(
        False,
        "--debug", "-d",
        help="Enable debug logging"
    ),
    clear_cache: bool = typer.Option(
        False,
        "--clear-cache",
        help="Clear cache before scanning"
    )
):
    """
    Scan market for swing trading opportunities.
    
    This scanner fetches market data, applies technical filters,
    and scores stocks based on configurable criteria.
    """
    # Setup logging
    setup_logging(debug)
    logger = logging.getLogger(__name__)
    
    try:
        # Load configuration
        console.print(f"[dim]Loading configuration from {config_file}...[/dim]")
        config = load_config(config_file)
        
        # Get universe
        if ticker:
            # Single ticker override
            tickers = [ticker.upper()]
            console.print(f"\n[cyan]Single ticker mode: {ticker.upper()}[/cyan]")
        else:
            # Use configured universe
            tickers = config.get('universe', {}).get('tickers', [])
        
        # Validate non-empty universe
        if not tickers:
            console.print("[red]Error: Empty universe. Check universe.tickers in config or use --ticker[/red]")
            sys.exit(EXIT_SUCCESS)
        
        console.print(f"[cyan]Universe: {len(tickers)} ticker{'s' if len(tickers) > 1 else ''}[/cyan]")
        
        # Dry run - validate only
        if dry_run:
            console.print("\n[green]✓ Configuration valid[/green]")
            console.print("[yellow]Dry run complete (use without --dry-run to scan)[/yellow]")
            sys.exit(EXIT_SUCCESS)
        
        # Initialize rate limiter
        start_full = config['data'].get('rate_limit_start_full', False)
        rate_limiter = TokenBucket(
            config['data']['rate_limit_per_minute'],
            start_full=start_full
        )
        
        # Log throttling info for first run
        if not start_full:
            logger.info(
                "Rate limiter starting empty for safety. "
                "Initial requests will be throttled to prevent 429 errors."
            )
        
        # Initialize components
        console.print("[dim]Initializing components...[/dim]")
        
        data_provider = DataProvider(config, rate_limiter)
        cache_manager = CacheManager(
            config['cache']['directory'],
            config['data']['timezone']
        )
        
        # Clear cache if requested
        if clear_cache:
            console.print("[yellow]Clearing cache...[/yellow]")
            cache_manager.clear_cache()
        
        # Check regime filter
        regime_status = {}
        if not ignore_regime and config['regime']['check_spy']:
            console.print("\n[dim]Checking market regime...[/dim]")
            
            try:
                spy_data = data_provider.fetch_and_calculate("SPY")
                
                if not spy_data.empty:
                    spy_rsi = spy_data['rsi14'].iloc[-1]
                    regime_status = {
                        'spy_rsi': spy_rsi,
                        'threshold': config['regime']['spy_rsi_threshold']
                    }
                    
                    if spy_rsi < config['regime']['spy_rsi_threshold']:
                        console.print(
                            f"\n[yellow]Market regime filter active:[/yellow]\n"
                            f"SPY RSI ({spy_rsi:.1f}) < threshold ({config['regime']['spy_rsi_threshold']})\n"
                            f"[dim]Scan blocked. Use --ignore-regime to bypass.[/dim]"
                        )
                        sys.exit(EXIT_SUCCESS)
                    else:
                        console.print(f"[green]✓ Regime check passed (SPY RSI: {spy_rsi:.1f})[/green]")
            except Exception as e:
                logger.warning(f"Could not check regime: {e}")
                console.print("[yellow]Warning: Could not check market regime, continuing...[/yellow]")
        
        # Print header
        print_header(config, regime_status, ignore_regime)
        
        # Initialize scanner and reporter
        scanner = Scanner(config, data_provider, cache_manager, rate_limiter)
        reporter = Reporter(config, data_provider, regime_status)
        
        # Run scan
        console.print(f"\n[dim]Scanning {len(tickers)} tickers...[/dim]")
        
        with ThreadPoolExecutor(max_workers=config['data']['max_workers']) as executor:
            results = scanner.scan(tickers, executor, show_progress=not no_progress)
        
        # Process results
        if not results.empty:
            # Sort by score (descending) and symbol (ascending for ties)
            results = results.sort_values(['score', 'symbol'], ascending=[False, True])
            
            # Export results
            csv_path = 'scan_results.csv'
            metadata_path = 'scan_metadata.json'
            
            reporter.export_all(results, csv_path, metadata_path)
            
            # Display results
            console.print()
            reporter.display_results(results)
            
            # Print summary
            reporter.print_summary(results, scanner.filter_stats)
        else:
            console.print("\n[yellow]No tickers passed filters[/yellow]")
            
            # Still print rejection summary if available
            if scanner.filter_stats:
                reporter.print_summary(results, scanner.filter_stats)
        
        console.print("\n[green]✓ Scan complete[/green]")
        sys.exit(EXIT_SUCCESS)
        
    except ConfigError as e:
        console.print(f"\n[red]Configuration error: {e}[/red]")
        sys.exit(EXIT_CONFIG_ERROR)
        
    except DataError as e:
        console.print(f"\n[red]Data error: {e}[/red]")
        sys.exit(EXIT_DATA_ERROR)
        
    except KeyboardInterrupt:
        console.print("\n[yellow]Scan interrupted by user[/yellow]")
        sys.exit(EXIT_SUCCESS)
        
    except Exception as e:
        # Map exception to exit code
        exit_code = ExceptionMapper.map_to_exit_code(e)
        
        if debug:
            # In debug mode, show full traceback
            console.print_exception()
        else:
            # In normal mode, show simple error message
            console.print(f"\n[red]Error: {e}[/red]")
            console.print(f"[dim]Exit code: {exit_code}[/dim]")
            console.print("[dim]Run with --debug for more details[/dim]")
        
        sys.exit(exit_code)


@app.command()
def version():
    """Show version information."""
    from . import __version__
    console.print(f"SwingTrading Scanner v{__version__}")


if __name__ == "__main__":
    app()