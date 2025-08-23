"""Scanner wrapper with single active run management."""

import asyncio
import uuid
import time
import logging
import pandas as pd
from datetime import datetime
from typing import Dict, Any, Optional, Callable, List
from pathlib import Path
import sys
import json
import yaml

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from swingtrading.scanner import Scanner
from swingtrading.data_provider import DataProvider
from swingtrading.rate_limiter import TokenBucket
from swingtrading.cache_manager import CacheManager
from swingtrading.config_validator import validate_config
from swingtrading.exceptions import DataError, ConfigError

from .models import RunState, ScanResult, ScanMetadata, ProgressUpdate

logger = logging.getLogger(__name__)


class ScannerWrapper:
    """Wrapper around Scanner with run management."""
    
    def __init__(self):
        self.active_run: Optional[Dict[str, Any]] = None
        self.run_history: List[Dict[str, Any]] = []
        self.max_history = 5
        self.config_path = Path(__file__).parent.parent / 'config.yaml'
        self.base_config = self._load_config()
        
    def _load_config(self) -> Dict[str, Any]:
        """Load base configuration."""
        with open(self.config_path, 'r') as f:
            config = yaml.safe_load(f)
        return validate_config(config)
    
    def get_config_no_secrets(self) -> Dict[str, Any]:
        """Get configuration without secrets."""
        config = self.base_config.copy()
        # Remove sensitive fields
        if 'data' in config:
            config['data'].pop('api_key_env', None)
            config['data'].pop('api_secret_env', None)
            config['data'].pop('base_url', None)
        return config
    
    def apply_overrides(self, config: Dict[str, Any], overrides: Dict[str, Any]) -> Dict[str, Any]:
        """Apply runtime overrides to config."""
        config = config.copy()
        
        # Universe override
        if overrides.get('tickers'):
            config['universe']['tickers'] = overrides['tickers']
        
        # Feed override
        if overrides.get('feed'):
            config['data']['feed'] = overrides['feed']
        
        # Filter overrides
        if overrides.get('min_price') is not None:
            config['filters']['min_price'] = overrides['min_price']
        if overrides.get('max_gap_percent') is not None:
            config['filters']['max_gap_percent'] = overrides['max_gap_percent']
        if overrides.get('min_atr_ratio') is not None:
            config['filters']['min_atr_ratio'] = overrides['min_atr_ratio']
        if overrides.get('min_dollar_volume') is not None:
            config['filters']['min_dollar_volume_10d_avg'] = overrides['min_dollar_volume']
        
        # Indicator overrides
        if overrides.get('atr_period') is not None:
            config['indicators']['atr_period'] = overrides['atr_period']
        if overrides.get('rsi_period') is not None:
            config['indicators']['rsi_period'] = overrides['rsi_period']
        if overrides.get('sma_short') is not None:
            config['indicators']['sma_short'] = overrides['sma_short']
        if overrides.get('sma_long') is not None:
            config['indicators']['sma_long'] = overrides['sma_long']
        
        # Scoring weights (already normalized in model)
        if overrides.get('weights'):
            config['scoring']['weights'] = overrides['weights']
        
        # Performance overrides
        if overrides.get('max_workers') is not None:
            config['data']['max_workers'] = overrides['max_workers']
        if overrides.get('rate_limit_per_minute') is not None:
            config['data']['rate_limit_per_minute'] = overrides['rate_limit_per_minute']
        if overrides.get('task_timeout') is not None:
            config['data']['task_timeout'] = overrides['task_timeout']
        if overrides.get('rate_limit_start_full') is not None:
            config['data']['rate_limit_start_full'] = overrides['rate_limit_start_full']
        
        # Regime bypass
        if overrides.get('bypass_regime'):
            config['regime']['check_spy'] = False
        
        return config
    
    async def start_scan(self, overrides: Dict[str, Any], 
                         progress_callback: Optional[Callable] = None) -> str:
        """Start a new scan with single active run enforcement."""
        # Cancel any active run
        if self.active_run and self.active_run['state'] == RunState.RUNNING:
            await self.cancel_scan(self.active_run['run_id'])
        
        # Create new run
        run_id = str(uuid.uuid4())
        self.active_run = {
            'run_id': run_id,
            'state': RunState.CREATED,
            'started_at': datetime.now(),
            'progress': {'done': 0, 'total': 0, 'partial_results': 0},
            'results': [],
            'metadata': None,
            'error': None,
            'cancel_flag': False
        }
        
        # Apply overrides to config
        config = self.apply_overrides(self.base_config, overrides)
        
        # Start scan in background
        asyncio.create_task(self._run_scan(run_id, config, progress_callback))
        
        return run_id
    
    async def _run_scan(self, run_id: str, config: Dict[str, Any], 
                       progress_callback: Optional[Callable] = None):
        """Run the actual scan."""
        if self.active_run['run_id'] != run_id:
            return
        
        try:
            self.active_run['state'] = RunState.RUNNING
            start_time = time.time()
            
            # Initialize components
            rate_limiter = TokenBucket(
                tokens_per_minute=config['data']['rate_limit_per_minute'],
                start_full=config['data'].get('rate_limit_start_full', False)
            )
            
            data_provider = DataProvider(config, rate_limiter)
            cache_manager = CacheManager(config)
            scanner = Scanner(config, data_provider, cache_manager)
            
            # Get universe
            tickers = config['universe']['tickers']
            self.active_run['progress']['total'] = len(tickers)
            
            # Send initial progress
            if progress_callback:
                await progress_callback(self._create_progress_update())
            
            # Scan each ticker
            results = []
            for i, ticker in enumerate(tickers):
                # Check cancel flag
                if self.active_run.get('cancel_flag'):
                    self.active_run['state'] = RunState.CANCELED
                    break
                
                try:
                    # Update current ticker
                    self.active_run['current_ticker'] = ticker
                    
                    # Scan ticker
                    result = await asyncio.to_thread(scanner.scan_ticker, ticker)
                    if result is not None:
                        results.append(result)
                        self.active_run['progress']['partial_results'] = len(results)
                    
                except Exception as e:
                    logger.warning(f"Error scanning {ticker}: {e}")
                
                # Update progress
                self.active_run['progress']['done'] = i + 1
                
                # Send progress update (throttled)
                if progress_callback and (i % 2 == 0 or i == len(tickers) - 1):
                    await progress_callback(self._create_progress_update())
            
            # Process results
            if self.active_run['state'] != RunState.CANCELED:
                # Convert to DataFrame and calculate scores
                if results:
                    df = pd.DataFrame([r for r in results if r is not None])
                    df = scanner.calculate_scores(df)
                    
                    # Convert back to ScanResult objects
                    self.active_run['results'] = [
                        ScanResult(**row.to_dict()) 
                        for _, row in df.iterrows()
                    ]
                
                # Create metadata
                self.active_run['metadata'] = ScanMetadata(
                    generated_at=datetime.now(),
                    last_session=str(data_provider.get_last_complete_session()),
                    feed=config['data']['feed'],
                    regime_status={
                        'spy_rsi': scanner.last_spy_rsi or 0,
                        'threshold': config['regime']['spy_rsi_threshold']
                    },
                    filters=config['filters'],
                    scoring_weights=config['scoring']['weights'],
                    universe_size=len(tickers),
                    run_time_seconds=time.time() - start_time
                )
                
                self.active_run['state'] = RunState.DONE
            
            # Final progress update
            if progress_callback:
                await progress_callback(self._create_progress_update())
            
            # Add to history
            self._add_to_history()
            
        except ConfigError as e:
            await self._handle_error(2, "Configuration Error", str(e), progress_callback)
        except DataError as e:
            await self._handle_error(4, "Data Error", str(e), progress_callback)
        except Exception as e:
            await self._handle_error(1, "Unexpected Error", str(e), progress_callback)
    
    async def _handle_error(self, code: int, title: str, detail: str, 
                           progress_callback: Optional[Callable]):
        """Handle scan error."""
        self.active_run['state'] = RunState.ERROR
        self.active_run['error'] = {
            'code': code,
            'title': title,
            'detail': detail,
            'logs': []  # Would capture last log lines in production
        }
        
        if progress_callback:
            await progress_callback(self._create_progress_update())
    
    def _create_progress_update(self) -> ProgressUpdate:
        """Create progress update from active run."""
        if not self.active_run:
            return None
        
        elapsed = (datetime.now() - self.active_run['started_at']).total_seconds() * 1000
        
        return ProgressUpdate(
            run_id=self.active_run['run_id'],
            state=self.active_run['state'],
            progress=self.active_run['progress'],
            started_at=self.active_run['started_at'],
            elapsed_ms=int(elapsed),
            current_ticker=self.active_run.get('current_ticker'),
            error=self.active_run.get('error')
        )
    
    async def cancel_scan(self, run_id: str) -> bool:
        """Cancel an active scan."""
        if self.active_run and self.active_run['run_id'] == run_id:
            if self.active_run['state'] == RunState.RUNNING:
                self.active_run['cancel_flag'] = True
                self.active_run['state'] = RunState.CANCELING
                
                # Wait briefly for cancellation
                await asyncio.sleep(0.5)
                
                if self.active_run['state'] != RunState.CANCELED:
                    self.active_run['state'] = RunState.CANCELED
                
                return True
        return False
    
    def get_run_status(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a run."""
        if self.active_run and self.active_run['run_id'] == run_id:
            return self.active_run
        
        # Check history
        for run in self.run_history:
            if run['run_id'] == run_id:
                return run
        
        return None
    
    def get_results(self, run_id: str) -> Optional[List[ScanResult]]:
        """Get results of a run."""
        run = self.get_run_status(run_id)
        if run:
            return run.get('results', [])
        return None
    
    def get_metadata(self, run_id: str) -> Optional[ScanMetadata]:
        """Get metadata of a run."""
        run = self.get_run_status(run_id)
        if run:
            return run.get('metadata')
        return None
    
    def _add_to_history(self):
        """Add completed run to history."""
        if self.active_run and self.active_run['state'] in [RunState.DONE, RunState.ERROR]:
            # Create history entry
            entry = {
                'run_id': self.active_run['run_id'],
                'timestamp': self.active_run['started_at'],
                'results_count': len(self.active_run.get('results', [])),
                'top_symbols': [r.symbol for r in self.active_run.get('results', [])[:3]],
                'feed': self.active_run.get('metadata', {}).feed if self.active_run.get('metadata') else 'unknown',
                'runtime_seconds': self.active_run.get('metadata', {}).run_time_seconds if self.active_run.get('metadata') else 0
            }
            
            self.run_history.insert(0, entry)
            
            # Trim history
            if len(self.run_history) > self.max_history:
                self.run_history = self.run_history[:self.max_history]
    
    def get_history(self) -> List[Dict[str, Any]]:
        """Get run history."""
        return self.run_history
    
    def export_csv(self, run_id: str) -> Optional[str]:
        """Export results to CSV."""
        results = self.get_results(run_id)
        if results:
            df = pd.DataFrame([r.dict() for r in results])
            csv_path = Path(f"scan_results_{run_id[:8]}.csv")
            df.to_csv(csv_path, index=False)
            return str(csv_path)
        return None
    
    def generate_cli_command(self, run_id: str, overrides: Dict[str, Any]) -> str:
        """Generate CLI command for current settings."""
        cmd_parts = ["python -m swingtrading.main scan"]
        
        # Add overrides as CLI args
        if overrides.get('min_price'):
            cmd_parts.append(f"--min-price {overrides['min_price']}")
        if overrides.get('max_gap_percent'):
            cmd_parts.append(f"--max-gap {overrides['max_gap_percent']}")
        if overrides.get('feed'):
            cmd_parts.append(f"--feed {overrides['feed']}")
        if overrides.get('tickers'):
            cmd_parts.append(f"--universe {','.join(overrides['tickers'])}")
        
        return " \\\n  ".join(cmd_parts)