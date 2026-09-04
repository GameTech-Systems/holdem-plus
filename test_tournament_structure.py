"""
Tests for tournament_structure.py.

Run with: pytest -v test_tournament_structure.py
"""

import pytest

from tournament_structure import (
    BlindClock,
    BlindLevel,
    chips_in_big_blinds,
    chop_evenly,
    generate_custom_schedule,
    generate_default_schedule,
    payout_curve,
    winner_take_all,
)


# ---------------------------------------------------------------------------
# generate_default_schedule -- matches the source spec exactly
# ---------------------------------------------------------------------------

def test_first_five_levels_match_source_spec_exactly():
    schedule = generate_default_schedule(num_levels=5)
    blinds = [(lvl.small_blind, lvl.big_blind) for lvl in schedule]
    assert blinds == [(1, 2), (2, 4), (3, 6), (4, 8), (5, 10)]


def test_first_five_levels_are_fifteen_minutes_each():
    schedule = generate_default_schedule(num_levels=5)
    assert all(lvl.duration_seconds == 900 for lvl in schedule)


def test_level_six_onward_doubles_the_previous_level():
    schedule = generate_default_schedule(num_levels=9)
    blinds = [(lvl.small_blind, lvl.big_blind) for lvl in schedule]
    assert blinds[5:] == [(10, 20), (20, 40), (40, 80), (80, 160)]


def test_level_numbers_are_sequential_starting_at_one():
    schedule = generate_default_schedule(num_levels=8)
    assert [lvl.level_number for lvl in schedule] == list(range(1, 9))


def test_default_schedule_requires_at_least_one_level():
    with pytest.raises(ValueError):
        generate_default_schedule(num_levels=0)


def test_default_schedule_shorter_than_fixed_steps_still_correct():
    schedule = generate_default_schedule(num_levels=3)
    blinds = [(lvl.small_blind, lvl.big_blind) for lvl in schedule]
    assert blinds == [(1, 2), (2, 4), (3, 6)]


# ---------------------------------------------------------------------------
# generate_custom_schedule -- the other stake levels / speed rounds / antes
# ---------------------------------------------------------------------------

def test_custom_schedule_with_fixed_increment_growth():
    schedule = generate_custom_schedule(
        starting_small_blind=100,
        starting_big_blind=200,
        num_levels=4,
        growth="increment",
        increment=100,
    )
    blinds = [(lvl.small_blind, lvl.big_blind) for lvl in schedule]
    assert blinds == [(100, 200), (200, 300), (300, 400), (400, 500)]


def test_custom_schedule_speed_round_shorter_duration():
    schedule = generate_custom_schedule(
        starting_small_blind=1,
        starting_big_blind=2,
        num_levels=3,
        level_duration_seconds=300,  # 5-minute speed levels
    )
    assert all(lvl.duration_seconds == 300 for lvl in schedule)


def test_custom_schedule_with_antes():
    schedule = generate_custom_schedule(
        starting_small_blind=100,
        starting_big_blind=200,
        num_levels=3,
        ante_schedule={2: 25, 3: 50},
    )
    antes = [lvl.ante for lvl in schedule]
    assert antes == [0, 25, 50]


def test_custom_schedule_rejects_missing_increment():
    with pytest.raises(ValueError):
        generate_custom_schedule(
            starting_small_blind=1,
            starting_big_blind=2,
            num_levels=3,
            growth="increment",
        )


def test_custom_schedule_rejects_unknown_growth_mode():
    with pytest.raises(ValueError):
        generate_custom_schedule(
            starting_small_blind=1,
            starting_big_blind=2,
            num_levels=3,
            growth="exponential",
        )


# ---------------------------------------------------------------------------
# BlindClock
# ---------------------------------------------------------------------------

@pytest.fixture
def default_clock() -> BlindClock:
    return BlindClock(schedule=generate_default_schedule(num_levels=6))


def test_level_at_start_of_tournament(default_clock):
    level = default_clock.level_at(0)
    assert (level.small_blind, level.big_blind) == (1, 2)


def test_level_at_boundary_transitions_to_next_level(default_clock):
    just_before = default_clock.level_at(899)
    at_boundary = default_clock.level_at(900)
    assert (just_before.small_blind, just_before.big_blind) == (1, 2)
    assert (at_boundary.small_blind, at_boundary.big_blind) == (2, 4)


def test_level_at_mid_tournament(default_clock):
    # Levels 1-4 = 4*900 = 3600s elapsed puts us into level 5 (5/10)
    level = default_clock.level_at(3600)
    assert (level.small_blind, level.big_blind) == (5, 10)


def test_level_at_past_end_of_schedule_holds_final_level(default_clock):
    far_future = 10 ** 7
    level = default_clock.level_at(far_future)
    last_scheduled = default_clock.schedule[-1]
    assert level == last_scheduled


def test_seconds_remaining_in_level_counts_down(default_clock):
    assert default_clock.seconds_remaining_in_level(0) == 900
    assert default_clock.seconds_remaining_in_level(300) == 600
    assert default_clock.seconds_remaining_in_level(899) == 1


def test_seconds_remaining_is_zero_past_schedule_end(default_clock):
    assert default_clock.seconds_remaining_in_level(10 ** 7) == 0


def test_next_level_preview(default_clock):
    upcoming = default_clock.next_level(0)
    assert (upcoming.small_blind, upcoming.big_blind) == (2, 4)


def test_next_level_is_none_at_final_scheduled_level(default_clock):
    last_level_start = sum(
        lvl.duration_seconds for lvl in default_clock.schedule[:-1]
    )
    assert default_clock.next_level(last_level_start) is None


def test_level_at_rejects_negative_elapsed_time(default_clock):
    with pytest.raises(ValueError):
        default_clock.level_at(-1)


# ---------------------------------------------------------------------------
# chips_in_big_blinds
# ---------------------------------------------------------------------------

def test_chips_in_big_blinds_at_starting_stack():
    """The source spec's 40-chip starting stack at the 1/2 opening level
    is 20 big blinds deep -- a standard, healthy starting depth."""
    level = BlindLevel(level_number=1, small_blind=1, big_blind=2)
    assert chips_in_big_blinds(40, level) == 20.0


def test_chips_in_big_blinds_gets_shallower_as_blinds_climb():
    level5 = BlindLevel(level_number=5, small_blind=5, big_blind=10)
    assert chips_in_big_blinds(40, level5) == 4.0


def test_chips_in_big_blinds_rejects_zero_big_blind():
    zero_bb_level = BlindLevel(level_number=1, small_blind=0, big_blind=0)
    with pytest.raises(ValueError):
        chips_in_big_blinds(40, zero_bb_level)


# ---------------------------------------------------------------------------
# Payout structures
# ---------------------------------------------------------------------------

def test_winner_take_all_gives_everything_to_first_place():
    payouts = winner_take_all(1000, ["p1", "p2", "p3"])
    assert payouts == {"p1": 1000}


def test_winner_take_all_requires_at_least_one_finisher():
    with pytest.raises(ValueError):
        winner_take_all(1000, [])


def test_chop_evenly_splits_without_remainder():
    payouts = chop_evenly(900, ["a", "b", "c"])
    assert payouts == {"a": 300, "b": 300, "c": 300}


def test_chop_evenly_distributes_remainder_in_order():
    payouts = chop_evenly(100, ["a", "b", "c"])
    assert sum(payouts.values()) == 100
    assert payouts["a"] == 34  # gets the first extra chip
    assert payouts["b"] == 33
    assert payouts["c"] == 33


def test_payout_curve_matches_percentages_and_sums_exactly():
    payouts = payout_curve(1000, ["p1", "p2", "p3"], [0.5, 0.3, 0.2])
    assert payouts == {"p1": 500, "p2": 300, "p3": 200}
    assert sum(payouts.values()) == 1000


def test_payout_curve_handles_rounding_without_losing_chips():
    # 1/3 splits don't divide evenly -- confirms no chips are lost or
    # invented due to floating point / integer rounding.
    payouts = payout_curve(1000, ["p1", "p2", "p3"], [1 / 3, 1 / 3, 1 / 3])
    assert sum(payouts.values()) == 1000


def test_payout_curve_rejects_percentages_not_summing_to_one():
    with pytest.raises(ValueError):
        payout_curve(1000, ["p1", "p2"], [0.5, 0.4])


def test_payout_curve_rejects_more_percentages_than_finishers():
    with pytest.raises(ValueError):
        payout_curve(1000, ["p1"], [0.5, 0.5])
