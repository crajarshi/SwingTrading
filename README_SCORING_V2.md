# Scoring v2 — What it is

A noise-reduced, end-of-day **setup score (0–100)** to surface **pullbacks in uptrends** with sufficient volatility and volume. It's a **ranking**, not a buy/sell signal. Pair with risk management.

## What's new vs v1

* Wilder-smoothed **RSI(14)** and **ATR(14)**
* **Time-series percentiles** (252-day) per symbol
* **Setup gates** (ATR ratio / uptrend / pullback band)
* **No look-ahead**: all rollings use **T-1** data

## Data prerequisites

* **≥366 trading days** per symbol
* Consistent feed (IEX vs SIP) for comparable results
* Partial-day guard: today's incomplete bar is excluded from rollings

---

## Exact scoring steps (T = today)

All rolling stats use **≤ T-1**. Today's close/volume only appear in numerators.

### 1. Indicators (on ≤ T-1)

* `RSI_smoothed(T-1) = EMA3( RSI_Wilder14(prices up to T-1) )`
* `ATR_ratio(T)   = ATR_Wilder14(OHLC up to T-1) / Close(T)`

### 2. Raw components at T

* **Pullback**: `(1 − Close(T) / High20(T-1)) × 100` → clamp [0, 100]
* **Trend**: `((Close(T) / SMA50(T-1)) − 1) × 100` → clamp [−50, 100]
* **RSI room**: `70 − RSI_smoothed(T-1)`
* **Volume uplift**: `ln( Volume(T) / VolAvg10(T-1) )`  *(VolAvg10 ends at T-1)*

### 3. Normalization (per symbol)

For each raw component:
* Build the **prior 252-day** series (strictly ≤ T-1)
* **Winsorize** at 1st/99th percentile (within that window)
* **Percentile rank**: `100 × (# ≤ current) / 252`
* Apply **EMA(3)** to the percentile time series; read the **last EMA value at T**

### 4. Gates (inclusive)

* `ATR_ratio ∈ [0.005, 0.08]` (0.5%–8%)
* `Close(T) ≥ SMA50(T-1)`
* `5% ≤ Pullback ≤ 20%`

Fail any → **score = null** with reason (`gate_atr_ratio`, `gate_trend_filter`, or `gate_pullback_band`).

### 5. Composite

* Equal weights (25% each) of the **four smoothed percentiles**
* Final score **rounded to 2 decimals**
* `model_version = "score_v2.0.0"`

---

## CSV & metadata fields

### CSV
`symbol, close, score, rsi14, gap_percent, volume, volume_avg_10d, pullback_pct, trend_pct, rsi_room_pct, volume_uplift_pct`

* Formatting: **2 dp** (price, score) • **1 dp + %** (percents) • **1 dp + x** (ratios)
* Null scores = empty cell (or `null`), not `0.00`

### Metadata
`generated_at, last_session, feed, regime_status.spy_rsi, model_version, cache_hit_rate, api_calls, avg_compute_ms, skipped_reasons`

---

## Performance targets

* 500 symbols ≤ **60s** (warm cache), ≤ **120s** cold (IEX)
* **≥90%** API reduction on second run (cache)

---

## Common skip reasons

* `insufficient_history` (<366 bars)
* `gate_atr_ratio`
* `gate_trend_filter`
* `gate_pullback_band`

---

## Risk management (recommended defaults)

* Initial stop: **1.5× ATR**
* Targets: **2–3× ATR**
* Max holding: **10 trading days**
* Position size: **inverse to ATR**

---

## Configuration

```json
{
  "gates": {
    "atr_ratio": [0.005, 0.08],
    "pullback_band": [0.05, 0.20],
    "trend_filter": 1.0
  },
  "weights": {
    "pullback": 0.25,
    "trend": 0.25,
    "rsi_room": 0.25,
    "volume": 0.25
  },
  "min_bars_required": 366,
  "model_version": "score_v2.0.0"
}
```

---

## FAQ

**Why not use provider RSI/ATR directly?**
We require **Wilder smoothing** and strict **T-1** contracts to avoid leakage and keep features consistent.

**Is the score predictive?**
It ranks **setup quality**. PnL depends on execution, costs, and risk rules. Validate on your universe.

**Why per-symbol percentiles?**
To compare a stock against **its own regime**. Sector/cross-section ranks can be an optional future layer.

---

## Implementation Details

### Module Structure
```
scoring_v2/
├── cache.py          # SQLite caching with 24hr TTL
├── indicators.py     # Wilder's RSI/ATR with T-1 exclusion
├── percentiles.py    # Winsorize→rank on 252-day window
├── gates.py         # Setup validation with frozen thresholds
├── scoring.py       # Main orchestrator
└── telemetry.py     # Performance tracking
```

### Key Guarantees

1. **No look-ahead**: Every rolling stat uses ≤ T-1 data
2. **Deterministic**: Same inputs → identical scores
3. **Percentile definition**: `100 × (# values ≤ current) / 252` with tie handling "≤"
4. **Gate inclusivity**: All boundaries inclusive (e.g., ATR = 0.005 passes)
5. **EMA placement**: Applied to time series of percentiles, not single values
6. **Volume shift**: VolAvg10(T-1) = mean(volumes[T-11:T-1])

### Testing Requirements

* **Determinism test**: 100 iterations with same input produce identical scores
* **No-leak test**: Changing T doesn't affect T-1 calculations
* **Boundary test**: Values exactly on gate thresholds pass
* **Format test**: 2dp prices/scores, 1dp%, null handling

---

## Acceptance Checklist

- [x] min_bars ≥ 366 enforced
- [x] Percentiles use prior 252 values (T excluded)
- [x] VolAvg10 shifted by 1 day
- [x] Gates applied in order with distinct failures
- [x] Model version in metadata/CSV
- [x] Telemetry: cache_hit_rate, api_calls, compute_ms
- [x] Deterministic outputs
- [x] Format: 2dp prices/scores, 1dp percentages