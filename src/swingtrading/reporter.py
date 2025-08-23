"""Reporting module for displaying and exporting scan results."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path

import pandas as pd
from rich.console import Console
from rich.table import Table

logger = logging.getLogger(__name__)


class Reporter:
    """
    Handles result display and export functionality.
    
    This class is responsible for:
    - Displaying results in the console
    - Exporting results to CSV
    - Generating metadata for the scan run
    """
    
    def __init__(
        self,
        config: Dict[str, Any],
        data_provider: Any,  # Avoid circular import
        regime_status: Dict[str, Any]
    ):
        """
        Initialize the reporter.
        
        Args:
            config: Validated configuration dictionary
            data_provider: DataProvider instance for metadata
            regime_status: Regime filter status information
        """
        self.config = config
        self.data_provider = data_provider
        self.regime_status = regime_status
        self.console = Console()
    
    def display_results(self, df: pd.DataFrame) -> None:
        """
        Display results table in the console.
        
        This is the main display contract for showing scan results
        to the user in a formatted table.
        
        Args:
            df: DataFrame with scan results
        """
        if df.empty:
            self.console.print("[yellow]No results to display[/yellow]")
            return
        
        # Calculate volume ratios for display
        vol_ratios = []
        if 'volume_avg_10d' in df.columns:
            for _, row in df.iterrows():
                if row.get('volume_avg_10d', 0) > 0:
                    ratio = row['volume'] / row['volume_avg_10d']
                    vol_ratios.append(f"{ratio:.1f}x")
                else:
                    vol_ratios.append('N/A')
        else:
            logger.warning("volume_avg_10d not available for display")
            vol_ratios = ['N/A'] * len(df)
        
        # Create rich table
        table = Table(title="Scan Results", show_header=True, header_style="bold cyan")
        
        # Add columns
        table.add_column("Symbol", style="cyan", no_wrap=True)
        table.add_column("Price", justify="right")
        table.add_column("Score", justify="right", style="green")
        table.add_column("RSI", justify="right")
        table.add_column("Gap%", justify="right")
        table.add_column("Vol Ratio", justify="right")
        
        # Add rows (maximum 20 for display)
        display_limit = min(20, len(df))
        for i in range(display_limit):
            row = df.iloc[i]
            
            # Format values for display
            symbol = row.get('symbol', 'N/A')
            price = f"${row['close']:.2f}" if 'close' in row else 'N/A'
            score = f"{row['score']:.2f}" if 'score' in row else 'N/A'
            rsi = f"{row.get('rsi14', 0):.1f}"
            gap = f"{row.get('gap_percent', 0):.1f}"
            vol = vol_ratios[i] if i < len(vol_ratios) else 'N/A'
            
            table.add_row(symbol, price, score, rsi, gap, vol)
        
        # Display table
        self.console.print(table)
        
        # Show message if more results exist
        if len(df) > display_limit:
            self.console.print(
                f"\n[dim]Showing top {display_limit} of {len(df)} results. "
                f"See CSV export for complete list.[/dim]"
            )
    
    def csv_export(self, df: pd.DataFrame, filepath: str) -> None:
        """
        Export results to CSV with full precision.
        
        The session_date will be used as the index, and all numeric
        values are written with full precision (no rounding).
        
        Args:
            df: DataFrame with scan results
            filepath: Path for the CSV file
            
        Raises:
            ValueError: If required columns are missing
        """
        if df.empty:
            logger.warning("No results to export")
            return
        
        # Set index name
        df.index.name = 'session_date'
        
        # Get configured columns (excluding session_date since it's the index)
        configured_columns = self.config['output']['csv_columns']
        columns_to_export = [
            col for col in configured_columns
            if col != 'session_date' and col in df.columns
        ]
        
        # Check for missing columns
        missing_columns = [
            col for col in configured_columns
            if col != 'session_date' and col not in df.columns
        ]
        
        if missing_columns:
            # Log warning but continue with available columns
            logger.warning(f"Missing columns for CSV export: {missing_columns}")
            
            # For critical missing columns, raise error
            critical_columns = ['symbol', 'close', 'score']
            critical_missing = [col for col in critical_columns if col not in df.columns]
            if critical_missing:
                raise ValueError(f"Critical columns missing for CSV export: {critical_missing}")
        
        # Select columns for export
        df_export = df[columns_to_export]
        
        # Export with full precision (no float_format)
        df_export.to_csv(filepath, index=True)
        
        logger.info(f"Exported {len(df_export)} results to {filepath}")
    
    def generate_metadata(self) -> Dict[str, Any]:
        """
        Generate metadata for the scan run.
        
        This includes information about when the scan was run,
        what configuration was used, and the market regime status.
        
        Returns:
            Dictionary with scan metadata
        """
        metadata = {
            'generated_at': datetime.now().isoformat(),
            'version': '1.0.0',
            'last_session': None,
            'regime_status': self.regime_status,
            'feed': self.config['data']['feed'],
            'filters': self.config['filters'],
            'scoring_weights': self.config['scoring']['weights'],
            'universe_size': len(self.config['universe']['tickers']),
        }
        
        # Add last session date if available
        if hasattr(self.data_provider, '_cached_last_session'):
            if self.data_provider._cached_last_session:
                metadata['last_session'] = self.data_provider._cached_last_session.isoformat()
        
        return metadata
    
    def save_metadata(self, filepath: str) -> None:
        """
        Save metadata to a JSON file.
        
        Args:
            filepath: Path for the JSON file
        """
        metadata = self.generate_metadata()
        
        with open(filepath, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        logger.info(f"Saved metadata to {filepath}")
    
    def print_summary(self, df: pd.DataFrame, filter_stats: Dict[str, int]) -> None:
        """
        Print a summary of the scan results.
        
        Args:
            df: DataFrame with scan results
            filter_stats: Dictionary with rejection statistics
        """
        self.console.print("\n[bold]Scan Summary[/bold]")
        self.console.print(f"Stocks scanned: {sum(filter_stats.values()) + len(df)}")
        self.console.print(f"Passed filters: {len(df)}")
        
        if filter_stats:
            # Sort rejection reasons by count
            sorted_reasons = sorted(filter_stats.items(), key=lambda x: x[1], reverse=True)
            
            # Show top 3 rejection reasons
            top_reasons = sorted_reasons[:3]
            if top_reasons:
                self.console.print("\n[bold]Top rejection reasons:[/bold]")
                for reason, count in top_reasons:
                    # Make reason more readable
                    display_reason = reason.replace('_', ' ').title()
                    self.console.print(f"  • {display_reason}: {count} tickers")
        
        if not df.empty:
            # Show score statistics
            self.console.print(f"\n[bold]Score Statistics:[/bold]")
            self.console.print(f"  • Highest: {df['score'].max():.2f}")
            self.console.print(f"  • Average: {df['score'].mean():.2f}")
            self.console.print(f"  • Lowest: {df['score'].min():.2f}")
    
    def export_all(
        self,
        df: pd.DataFrame,
        csv_path: str = "scan_results.csv",
        metadata_path: str = "scan_metadata.json"
    ) -> None:
        """
        Export both CSV results and metadata.
        
        Convenience method to export all outputs at once.
        
        Args:
            df: DataFrame with scan results
            csv_path: Path for CSV file
            metadata_path: Path for metadata JSON file
        """
        # Export CSV
        self.csv_export(df, csv_path)
        
        # Export metadata
        self.save_metadata(metadata_path)
        
        # Print paths
        self.console.print(f"\n[green]✓ Results exported to {csv_path}[/green]")
        self.console.print(f"[green]✓ Metadata exported to {metadata_path}[/green]")