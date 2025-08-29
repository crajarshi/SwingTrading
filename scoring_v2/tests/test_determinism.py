"""Determinism tests for Scoring v2."""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from scoring_v2.scoring import calculate_score_v2
import random


def generate_test_bars(num_bars=400):
    """Generate consistent test data."""
    random.seed(42)  # Fixed seed for reproducibility
    bars = []
    base_price = 100.0
    
    for i in range(num_bars):
        # Generate deterministic price movement
        change = (i % 20 - 10) / 100.0  # Oscillating pattern
        close = base_price * (1 + change)
        
        bars.append({
            'o': close * 0.99,
            'h': close * 1.01,
            'l': close * 0.98,
            'c': close,
            'v': 1000000 + i * 1000,
            't': f'2023-{(i//30)+1:02d}-{(i%30)+1:02d}T00:00:00Z'
        })
        
        base_price = close
    
    return bars


def test_determinism():
    """Test that same inputs produce identical scores."""
    print("Testing determinism...")
    
    # Generate test data
    bars = generate_test_bars(400)
    
    # Run scoring 100 times
    scores = []
    for i in range(100):
        score, reason, components = calculate_score_v2(bars, "TEST")
        scores.append(score)
    
    # Check all scores are identical
    if len(set(scores)) == 1:
        print(f"✓ Determinism test PASSED - All 100 iterations produced score: {scores[0]}")
        return True
    else:
        print(f"✗ Determinism test FAILED - Got different scores: {set(scores)}")
        return False


def test_boundary_gates():
    """Test that values exactly on gate thresholds pass."""
    print("\nTesting gate boundaries...")
    
    from scoring_v2.gates import evaluate_gates
    
    test_cases = [
        # ATR ratio exactly at boundaries (should pass)
        {"atr_ratio": 0.005, "close_t": 100, "sma50": 100, "pullback": 10, "expect": True},
        {"atr_ratio": 0.08, "close_t": 100, "sma50": 100, "pullback": 10, "expect": True},
        
        # Close exactly at SMA50 (should pass)
        {"atr_ratio": 0.02, "close_t": 100, "sma50": 100, "pullback": 10, "expect": True},
        
        # Pullback exactly at boundaries (should pass)
        {"atr_ratio": 0.02, "close_t": 100, "sma50": 100, "pullback": 5, "expect": True},
        {"atr_ratio": 0.02, "close_t": 100, "sma50": 100, "pullback": 20, "expect": True},
        
        # Outside boundaries (should fail)
        {"atr_ratio": 0.004, "close_t": 100, "sma50": 100, "pullback": 10, "expect": False},
        {"atr_ratio": 0.09, "close_t": 100, "sma50": 100, "pullback": 10, "expect": False},
        {"atr_ratio": 0.02, "close_t": 99, "sma50": 100, "pullback": 10, "expect": False},
        {"atr_ratio": 0.02, "close_t": 100, "sma50": 100, "pullback": 4, "expect": False},
        {"atr_ratio": 0.02, "close_t": 100, "sma50": 100, "pullback": 21, "expect": False},
    ]
    
    all_pass = True
    for i, test in enumerate(test_cases):
        passed, reason = evaluate_gates(
            test["atr_ratio"],
            test["close_t"],
            test["sma50"],
            test["pullback"]
        )
        
        if passed == test["expect"]:
            print(f"  ✓ Case {i+1}: Correct - {'Passed' if passed else f'Failed ({reason})'}")
        else:
            print(f"  ✗ Case {i+1}: Wrong - Expected {'pass' if test['expect'] else 'fail'}, got {'pass' if passed else f'fail ({reason})'}")
            all_pass = False
    
    if all_pass:
        print("✓ Gate boundary test PASSED")
    else:
        print("✗ Gate boundary test FAILED")
    
    return all_pass


def test_formatting():
    """Test output formatting requirements."""
    print("\nTesting formatting...")
    
    from scoring_v2.scoring import format_score_output
    
    # Test with valid score (already rounded in practice)
    output = format_score_output(
        score=45.68,  # Score should already be rounded by calculate_score_v2
        gate_reason=None,
        components={
            "percentiles": {
                "pullback_pct": 65.432,
                "trend_pct": 43.21,
                "rsi_room_pct": 78.9,
                "volume_uplift_pct": 12.345
            },
            "raw_features": {
                "close_t": 123.456,
                "rsi_value": 45.678,
                "volume_t": 1234567,
                "vol_avg_10_t_minus_1": 987654.321
            }
        }
    )
    
    checks = [
        ("Score is 2dp", output["score"] == 45.68),
        ("Close is 2dp", output["close"] == 123.46),
        ("RSI is 1dp", output["rsi14"] == 45.7),
        ("Pullback pct is 1dp", output["pullback_pct"] == 65.4),
        ("Volume avg is rounded", output["volume_avg_10d"] == 987654),
    ]
    
    # Test with null score (gate failed)
    null_output = format_score_output(
        score=None,
        gate_reason="gate_atr_ratio",
        components={}
    )
    
    checks.append(("Null score is None", null_output["score"] is None))
    checks.append(("Gate reason present", null_output["gate_failed"] == "gate_atr_ratio"))
    
    all_pass = True
    for check_name, result in checks:
        if result:
            print(f"  ✓ {check_name}")
        else:
            print(f"  ✗ {check_name}")
            all_pass = False
    
    if all_pass:
        print("✓ Formatting test PASSED")
    else:
        print("✗ Formatting test FAILED")
    
    return all_pass


if __name__ == "__main__":
    print("=== Scoring v2 Tests ===\n")
    
    results = []
    results.append(test_determinism())
    results.append(test_boundary_gates())
    results.append(test_formatting())
    
    print("\n=== Summary ===")
    if all(results):
        print("✓ All tests PASSED")
        sys.exit(0)
    else:
        print("✗ Some tests FAILED")
        sys.exit(1)