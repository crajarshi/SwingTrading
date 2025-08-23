"""Pydantic models for API request/response."""

from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field, validator
from datetime import datetime
from enum import Enum


class RunState(str, Enum):
    """Scan run states."""
    CREATED = "created"
    RUNNING = "running"
    CANCELING = "canceling"
    CANCELED = "canceled"
    DONE = "done"
    ERROR = "error"


class ScanRequest(BaseModel):
    """Scan request with parameter overrides."""
    # Quick controls
    tickers: Optional[List[str]] = None
    feed: Optional[str] = Field(None, pattern="^(iex|sip)$")
    bypass_regime: bool = False
    sort_by: str = Field("score", pattern="^(score|rsi14|gap_percent)$")
    
    # Filters
    min_price: Optional[float] = Field(None, ge=0)
    max_gap_percent: Optional[float] = Field(None, ge=0, le=100)
    min_atr_ratio: Optional[float] = Field(None, ge=0, le=1)
    min_dollar_volume: Optional[float] = Field(None, ge=0)
    
    # Indicators
    atr_period: Optional[int] = Field(None, ge=5, le=50)
    rsi_period: Optional[int] = Field(None, ge=5, le=30)
    sma_short: Optional[int] = Field(None, ge=5, le=50)
    sma_long: Optional[int] = Field(None, ge=20, le=200)
    
    # Scoring weights (must sum to 100)
    weights: Optional[Dict[str, float]] = None
    
    # Performance
    max_workers: Optional[int] = Field(None, ge=1, le=20)
    rate_limit_per_minute: Optional[int] = Field(None, ge=10, le=200)
    task_timeout: Optional[int] = Field(None, ge=5, le=120)
    rate_limit_start_full: Optional[bool] = None
    
    @validator('weights')
    def validate_weights(cls, v):
        if v is not None:
            total = sum(v.values())
            if abs(total - 100) > 0.01:  # Allow small floating point error
                # Auto-normalize
                normalized = {k: (val / total) * 100 for k, val in v.items()}
                return normalized
        return v
    
    @validator('tickers')
    def dedupe_tickers(cls, v):
        if v is not None:
            # Preserve order, dedupe case-insensitively
            seen = set()
            result = []
            for ticker in v:
                upper = ticker.upper()
                if upper not in seen:
                    seen.add(upper)
                    result.append(upper)
            return result
        return v


class ProgressUpdate(BaseModel):
    """WebSocket progress update."""
    run_id: str
    state: RunState
    progress: Dict[str, int]  # done, total, partial_results
    started_at: datetime
    elapsed_ms: int
    current_ticker: Optional[str] = None
    error: Optional[Dict[str, Any]] = None


class ScanResult(BaseModel):
    """Individual scan result."""
    symbol: str
    close: float
    score: float
    rsi14: float
    gap_percent: float
    volume: int
    volume_avg_10d: float
    dollar_volume_10d_avg: float
    atr20: float
    sma20: Optional[float] = None
    sma50: Optional[float] = None
    high20: Optional[float] = None
    
    @property
    def volume_ratio(self) -> float:
        """Calculate volume ratio."""
        if self.volume_avg_10d > 0:
            return self.volume / self.volume_avg_10d
        return 0
    
    @property
    def trend_vs_sma50(self) -> Optional[float]:
        """Calculate trend vs SMA50."""
        if self.sma50:
            return ((self.close - self.sma50) / self.sma50) * 100
        return None
    
    @property
    def pullback_from_high20(self) -> Optional[float]:
        """Calculate pullback from 20-day high."""
        if self.high20:
            return ((self.high20 - self.close) / self.high20) * 100
        return None


class ScanMetadata(BaseModel):
    """Scan metadata."""
    generated_at: datetime
    last_session: str
    feed: str
    regime_status: Dict[str, float]
    filters: Dict[str, Any]
    scoring_weights: Dict[str, float]
    universe_size: int
    run_time_seconds: Optional[float] = None


class ScanResponse(BaseModel):
    """Complete scan response."""
    run_id: str
    state: RunState
    results: List[ScanResult]
    metadata: ScanMetadata
    filter_stats: Optional[Dict[str, int]] = None


class ErrorResponse(BaseModel):
    """Error response."""
    code: int
    title: str
    detail: str
    logs: Optional[List[str]] = None


class ConfigResponse(BaseModel):
    """Configuration response (no secrets)."""
    universe: List[str]
    data: Dict[str, Any]
    filters: Dict[str, Any]
    indicators: Dict[str, int]
    scoring: Dict[str, float]
    
    class Config:
        schema_extra = {
            "example": {
                "universe": ["AAPL", "MSFT", "GOOGL"],
                "data": {
                    "feed": "iex",
                    "timezone": "America/New_York",
                    "days_history": 252,
                    "min_bars_required": 100
                },
                "filters": {
                    "min_price": 5.0,
                    "max_gap_percent": 15.0,
                    "min_atr_ratio": 0.01,
                    "min_dollar_volume_10d_avg": 5000000
                },
                "indicators": {
                    "atr_period": 20,
                    "rsi_period": 14,
                    "sma_short": 20,
                    "sma_long": 50
                },
                "scoring": {
                    "pullback_proximity": 0.30,
                    "trend_strength": 0.25,
                    "rsi_headroom": 0.25,
                    "volume_ratio": 0.20
                }
            }
        }


class HistoryEntry(BaseModel):
    """Scan history entry."""
    run_id: str
    timestamp: datetime
    results_count: int
    top_symbols: List[str]
    feed: str
    runtime_seconds: float