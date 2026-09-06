"""
Tests for analytics.py.

Run with: pytest -v test_analytics.py
"""

import random

import pytest

from analytics import (
    AnalyticsLog,
    HandRecord,
    build_hand_record,
    simulate_standard_holdem_baseline,
)
from orchestrator import HandResult
from poker_types import HandCategory, parse_cards


def _fold_result(payouts, folded=("loser",)) -> HandResult:
    """A hand that ended by folds -- no showdown, no revealed_hands."""
    return HandResult(
        payouts=payouts,
        refund=None,
        revealed_hands={},
        community_cards=[],
        pots=[],
        folded_players=list(folded),
        final_stacks={},
    )


def _showdown_result(payouts, revealed_hands, community_cards) -> HandResult:
    return HandResult(
        payouts=payouts,
        refund=None,
        revealed_hands=revealed_hands,
        community_cards=list(community_cards),
        pots=[],
        folded_players=[],
        final_stacks={},
    )


# ---------------------------------------------------------------------------
# build_hand_record
# ---------------------------------------------------------------------------

def test_build_hand_record_from_fold_hand_has_no_showdown_categories():
    result = _fold_result(payouts={"winner": 3}, folded=("loser",))
    record = build_hand_record(
        result, small_blind=1, big_blind=2, elapsed_seconds=120, num_dealt_in=2
    )
    assert record.went_to_showdown is False
    assert record.showdown_categories == ()
    assert record.pot_total == 3
    assert record.num_folded == 1


def test_build_hand_record_from_showdown_hand_computes_categories():
    community = parse_cards("Ah Kd 9c 4s 2h")
    revealed = {
        "winner": list(parse_cards("Ac Ad")),   # trips aces with the board
        "loser": list(parse_cards("7c 3d")),    # high card / nothing
    }
    result = _showdown_result(payouts={"winner": 20}, revealed_hands=revealed, community_cards=community)
    record = build_hand_record(
        result, small_blind=5, big_blind=10, elapsed_seconds=300, num_dealt_in=2
    )
    assert record.went_to_showdown is True
    assert len(record.showdown_categories) == 2
    assert HandCategory.TRIPS in record.showdown_categories


# ---------------------------------------------------------------------------
# AnalyticsLog
# ---------------------------------------------------------------------------

def test_empty_log_reports_nones_and_empty_distribution():
    log = AnalyticsLog()
    assert log.hands_per_hour() is None
    assert log.average_pot_in_big_blinds() is None
    assert log.showdown_frequency() is None
    assert log.category_distribution() == {}


def test_hands_per_hour_needs_at_least_two_records():
    log = AnalyticsLog()
    log.record_hand(HandRecord(1, 2, 0, 2, 0, 3, False, ()))
    assert log.hands_per_hour() is None  # only one data point, no interval yet


def test_hands_per_hour_computed_from_elapsed_span():
    log = AnalyticsLog()
    # 3 hands recorded over a 120-second span -> 2 intervals / 120s -> 60/hour
    log.record_hand(HandRecord(1, 2, 0, 2, 0, 3, False, ()))
    log.record_hand(HandRecord(1, 2, 60, 2, 0, 3, False, ()))
    log.record_hand(HandRecord(1, 2, 120, 2, 0, 3, False, ()))
    assert log.hands_per_hour() == pytest.approx(60.0)


def test_average_pot_in_big_blinds():
    log = AnalyticsLog()
    log.record_hand(HandRecord(1, 2, 0, 2, 0, 20, False, ()))   # 10 bb
    log.record_hand(HandRecord(1, 2, 10, 2, 0, 40, False, ()))  # 20 bb
    assert log.average_pot_in_big_blinds() == pytest.approx(15.0)


def test_showdown_frequency_mixes_folds_and_showdowns():
    log = AnalyticsLog()
    log.record_hand(HandRecord(1, 2, 0, 2, 1, 3, False, ()))                       # folded
    log.record_hand(HandRecord(1, 2, 10, 2, 0, 20, True, (HandCategory.PAIR,)))    # showdown
    log.record_hand(HandRecord(1, 2, 20, 2, 0, 20, True, (HandCategory.PAIR,)))    # showdown
    log.record_hand(HandRecord(1, 2, 30, 2, 1, 3, False, ()))                       # folded
    assert log.showdown_frequency() == pytest.approx(0.5)


def test_category_distribution_counts_per_revealed_hand_not_per_pot():
    log = AnalyticsLog()
    # a single 3-way showdown contributes 3 category data points
    log.record_hand(HandRecord(
        1, 2, 0, 3, 0, 30, True,
        (HandCategory.TWO_PAIR, HandCategory.PAIR, HandCategory.HIGH_CARD),
    ))
    dist = log.category_distribution()
    assert dist[HandCategory.TWO_PAIR.name] == pytest.approx(1 / 3)
    assert dist[HandCategory.PAIR.name] == pytest.approx(1 / 3)
    assert dist[HandCategory.HIGH_CARD.name] == pytest.approx(1 / 3)
    assert sum(dist.values()) == pytest.approx(1.0)


def test_record_feedback_tracks_thumbs():
    log = AnalyticsLog()
    log.record_feedback(True)
    log.record_feedback(True)
    log.record_feedback(False)
    assert log.thumbs_up == 2
    assert log.thumbs_down == 1


def test_summary_shape_has_all_expected_keys():
    log = AnalyticsLog()
    log.record_hand(HandRecord(1, 2, 0, 2, 0, 3, False, ()))
    summary = log.summary()
    for key in (
        "hands_recorded", "hands_per_hour", "average_pot_in_big_blinds",
        "showdown_frequency", "category_distribution", "player_feedback",
    ):
        assert key in summary


# ---------------------------------------------------------------------------
# simulate_standard_holdem_baseline
# ---------------------------------------------------------------------------

def test_baseline_rejects_non_positive_iteration_count():
    with pytest.raises(ValueError):
        simulate_standard_holdem_baseline(0)


def test_baseline_distribution_sums_to_one_and_covers_common_categories():
    dist = simulate_standard_holdem_baseline(2000, rng=random.Random(0))
    assert sum(dist.values()) == pytest.approx(1.0, abs=1e-9)
    # With 2000 iterations, pair and high card should reliably both appear --
    # they're the two most common 7-card categories by a wide margin.
    assert HandCategory.PAIR.name in dist
    assert HandCategory.HIGH_CARD.name in dist


def test_baseline_is_reproducible_with_a_seeded_rng():
    dist_a = simulate_standard_holdem_baseline(500, rng=random.Random(42))
    dist_b = simulate_standard_holdem_baseline(500, rng=random.Random(42))
    assert dist_a == dist_b
