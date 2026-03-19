"""Tests for trust score computation."""

from server.scoring import compute_trust_signals, compute_overall_score


def test_perfect_agent():
    signals = compute_trust_signals(
        total_records=100,
        total_batches=5,
        flag_counts={"hedged": 0, "high_latency": 0, "error": 0, "retried": 0, "incomplete": 0, "human_review": 0},
    )
    assert signals["reliability"] == 1.0
    assert signals["efficiency"] == 1.0
    assert signals["transparency"] == 1.0


def test_error_heavy_agent():
    signals = compute_trust_signals(
        total_records=100,
        total_batches=10,
        flag_counts={"hedged": 0, "high_latency": 0, "error": 50, "retried": 0, "incomplete": 0, "human_review": 0},
    )
    assert signals["reliability"] == 0.5


def test_slow_agent():
    signals = compute_trust_signals(
        total_records=100,
        total_batches=10,
        flag_counts={"hedged": 0, "high_latency": 30, "error": 0, "retried": 20, "incomplete": 0, "human_review": 0},
    )
    assert signals["efficiency"] == 0.5


def test_zero_records():
    signals = compute_trust_signals(total_records=0, total_batches=0, flag_counts={})
    assert signals["reliability"] == 1.0
    assert signals["authority"] == 0.0
    assert signals["transparency"] == 0.0


def test_authority_scales():
    s10 = compute_trust_signals(total_records=10, total_batches=1, flag_counts={})
    s1000 = compute_trust_signals(total_records=1000, total_batches=100, flag_counts={})
    assert s1000["authority"] > s10["authority"]


def test_overall_score():
    signals = {"reliability": 1.0, "transparency": 1.0, "efficiency": 1.0, "authority": 1.0}
    assert compute_overall_score(signals) == 1.0

    signals2 = {"reliability": 0.5, "transparency": 0.5, "efficiency": 0.5, "authority": 0.5}
    assert compute_overall_score(signals2) == 0.5
