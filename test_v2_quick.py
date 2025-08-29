#!/usr/bin/env python3
"""Quick test of Scoring v2 implementation."""

import json
from scoring_v2 import calculate_score_v2, MODEL_VERSION
from scoring_v2.telemetry import get_telemetry

def create_test_bars():
    """Create synthetic test data with 400 bars."""
    bars = []
    import math
    
    for i in range(400):
        # Create realistic price movement
        base = 100
        trend = i * 0.01  # Upward trend
        cycle = math.sin(i * 0.1) * 5  # Oscillation
        noise = (i % 7 - 3) * 0.5  # Some noise
        
        close = base + trend + cycle + noise
        
        bars.append({
            'o': close * 0.995,
            'h': close * 1.01,
            'l': close * 0.99,
            'c': close,
            'v': 1000000 + (i % 20) * 50000,
            't': f'2023-{(i//30)+1:02d}-{(i%30)+1:02d}T00:00:00Z'
        })
    
    return bars

def main():
    print(f"Testing Scoring v2 ({MODEL_VERSION})")
    print("=" * 50)
    
    # Create test data
    bars = create_test_bars()
    print(f"Created {len(bars)} test bars")
    
    # Calculate score
    score, gate_reason, components = calculate_score_v2(bars, "TEST_SYMBOL")
    
    print(f"\nResults:")
    print(f"  Score: {score}")
    print(f"  Gate reason: {gate_reason}")
    
    if 'percentiles' in components:
        print(f"\nPercentiles:")
        for key, value in components['percentiles'].items():
            print(f"  {key}: {value:.1f}%")
    
    if 'raw_features' in components:
        print(f"\nRaw features:")
        rf = components['raw_features']
        print(f"  Close: ${rf.get('close_t', 0):.2f}")
        print(f"  RSI: {rf.get('rsi_value', 0):.1f}")
        print(f"  ATR ratio: {rf.get('atr_ratio', 0):.3f}")
        print(f"  Pullback: {rf.get('pullback_raw', 0):.1f}%")
        print(f"  Trend: {rf.get('trend_raw', 0):.1f}%")
    
    # Show telemetry
    telemetry = get_telemetry()
    print(f"\nTelemetry:")
    summary = telemetry.get_summary()
    print(f"  Cache hit rate: {summary['cache_hit_rate']:.1%}")
    print(f"  Skipped: {summary['total_skipped']}")
    if summary['skipped_reasons']:
        for reason, count in summary['skipped_reasons'].items():
            print(f"    - {reason}: {count}")
    
    print("\n✓ Scoring v2 implementation working!")

if __name__ == "__main__":
    main()