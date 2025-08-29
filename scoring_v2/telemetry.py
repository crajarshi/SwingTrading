"""Telemetry tracking for monitoring and performance."""

import time
from typing import Dict, Any, Optional
from collections import defaultdict


class TelemetryTracker:
    """Track cache hits, API calls, and skip reasons."""
    
    def __init__(self):
        self.cache_hits = 0
        self.cache_misses = 0
        self.api_calls = 0
        self.api_total_ms = 0.0
        self.compute_times = []
        self.skip_reasons = defaultdict(int)
        self.start_time = time.time()
    
    def track_cache_hit(self, symbol: str, hit: bool):
        """Track cache hit/miss."""
        if hit:
            self.cache_hits += 1
        else:
            self.cache_misses += 1
    
    def track_api_call(self, symbol: str, duration_ms: float):
        """Track API call and duration."""
        self.api_calls += 1
        self.api_total_ms += duration_ms
    
    def track_compute_time(self, symbol: str, duration_ms: float):
        """Track computation time per symbol."""
        self.compute_times.append((symbol, duration_ms))
    
    def track_skip(self, symbol: str, reason: str):
        """Track skipped symbol and reason."""
        self.skip_reasons[reason] += 1
    
    def get_cache_hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total = self.cache_hits + self.cache_misses
        if total == 0:
            return 0.0
        return self.cache_hits / total
    
    def get_avg_compute_ms(self) -> float:
        """Get average computation time per symbol."""
        if not self.compute_times:
            return 0.0
        return sum(t[1] for t in self.compute_times) / len(self.compute_times)
    
    def get_summary(self) -> Dict[str, Any]:
        """Get telemetry summary.
        
        Returns:
            Dict with all telemetry metrics
        """
        elapsed = time.time() - self.start_time
        
        return {
            "cache_hit_rate": self.get_cache_hit_rate(),
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "api_calls": self.api_calls,
            "api_avg_ms": self.api_total_ms / self.api_calls if self.api_calls > 0 else 0,
            "avg_compute_ms": self.get_avg_compute_ms(),
            "total_symbols": len(self.compute_times),
            "skipped_reasons": dict(self.skip_reasons),
            "total_skipped": sum(self.skip_reasons.values()),
            "elapsed_seconds": elapsed
        }
    
    def log_summary(self, verbose: bool = False) -> str:
        """Generate log summary.
        
        Args:
            verbose: Include detailed breakdown
        
        Returns:
            Formatted summary string
        """
        summary = self.get_summary()
        
        lines = [
            "=== Telemetry Summary ===",
            f"Cache hit rate: {summary['cache_hit_rate']:.1%} ({summary['cache_hits']}/{summary['cache_hits'] + summary['cache_misses']})",
            f"API calls: {summary['api_calls']}",
            f"Avg compute: {summary['avg_compute_ms']:.1f}ms/symbol",
            f"Total symbols: {summary['total_symbols']}",
            f"Skipped: {summary['total_skipped']}"
        ]
        
        if summary['skipped_reasons'] and verbose:
            lines.append("Skip reasons:")
            for reason, count in sorted(summary['skipped_reasons'].items()):
                lines.append(f"  - {reason}: {count}")
        
        lines.append(f"Total time: {summary['elapsed_seconds']:.1f}s")
        
        return "\n".join(lines)


# Global telemetry instance
_telemetry = None


def get_telemetry() -> TelemetryTracker:
    """Get or create global telemetry instance."""
    global _telemetry
    if _telemetry is None:
        _telemetry = TelemetryTracker()
    return _telemetry


def reset_telemetry():
    """Reset global telemetry instance."""
    global _telemetry
    _telemetry = TelemetryTracker()