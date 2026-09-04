"""
Tests for side_pots.py.

Run with: pytest -v test_side_pots.py
"""

import pytest

from hand_evaluator import evaluate_5
from poker_types import HandCategory, HandRank, parse_cards
from side_pots import (
    Pot,
    SidePotError,
    award_pots,
    compute_side_pots,
    return_uncalled_bet,
)


# ---------------------------------------------------------------------------
# return_uncalled_bet
# ---------------------------------------------------------------------------

def test_no_refund_when_top_two_contributions_match():
    contributions = {"p0": 300, "p1": 300, "p2": 100}
    adjusted, refund = return_uncalled_bet(contributions)
    assert refund is None
    assert adjusted == contributions


def test_refund_when_single_player_uniquely_highest():
    contributions = {"p0": 500, "p1": 300, "p2": 100}
    adjusted, refund = return_uncalled_bet(contributions)
    assert refund == ("p0", 200)
    assert adjusted == {"p0": 300, "p1": 300, "p2": 100}


def test_no_refund_with_fewer_than_two_contributors():
    contributions = {"p0": 500}
    adjusted, refund = return_uncalled_bet(contributions)
    assert refund is None
    assert adjusted == contributions


def test_no_refund_when_all_tied_for_highest():
    contributions = {"p0": 300, "p1": 300}
    adjusted, refund = return_uncalled_bet(contributions)
    assert refund is None
    assert adjusted == contributions


# ---------------------------------------------------------------------------
# compute_side_pots
# ---------------------------------------------------------------------------

def test_single_pot_no_all_ins():
    contributions = {"p0": 100, "p1": 100, "p2": 100}
    pots = compute_side_pots(contributions, folded_player_ids=set())
    assert len(pots) == 1
    assert pots[0].amount == 300
    assert set(pots[0].eligible_player_ids) == {"p0", "p1", "p2"}


def test_classic_two_tier_side_pot():
    """
    A all-in for 100, B and C both put in 300 (B all-in, C not).
    Main pot: 100 * 3 = 300, everyone eligible.
    Side pot: 200 * 2 = 400, only B and C eligible.
    """
    contributions = {"a": 100, "b": 300, "c": 300}
    pots = compute_side_pots(contributions, folded_player_ids=set())
    assert len(pots) == 2
    assert pots[0].amount == 300
    assert set(pots[0].eligible_player_ids) == {"a", "b", "c"}
    assert pots[1].amount == 400
    assert set(pots[1].eligible_player_ids) == {"b", "c"}
    assert sum(p.amount for p in pots) == sum(contributions.values())


def test_three_tier_side_pot_four_players():
    """Four different all-in amounts should produce four pot layers."""
    contributions = {"a": 50, "b": 150, "c": 300, "d": 300}
    pots = compute_side_pots(contributions, folded_player_ids=set())
    amounts = [p.amount for p in pots]
    eligibles = [set(p.eligible_player_ids) for p in pots]

    assert amounts == [200, 300, 300]
    # pot1: everyone contributed the first 50            -> 50*4
    # pot2: b,c,d contributed the next 100 (150-50)       -> 100*3
    # pot3: c,d contributed the final 150 (300-150)       -> 150*2
    assert eligibles == [
        {"a", "b", "c", "d"},
        {"b", "c", "d"},
        {"c", "d"},
    ]
    assert sum(amounts) == sum(contributions.values())


def test_folded_player_chips_count_toward_pot_but_not_eligible():
    contributions = {"a": 100, "b": 100, "c": 100}
    pots = compute_side_pots(contributions, folded_player_ids={"c"})
    assert len(pots) == 1
    assert pots[0].amount == 300  # c's chips still counted
    assert set(pots[0].eligible_player_ids) == {"a", "b"}  # but c can't win


def test_all_in_layer_with_only_folded_contributors_merges_into_prior_pot():
    """
    a and b both call 300 then fold; c is all-in for only 100 and stays in.
    The layer above 100 (the extra 200 from a and b) has zero eligible
    winners since both folded -- that dead money should still end up
    counted in a pot c is eligible for, not vanish from chip accounting.
    """
    contributions = {"a": 300, "b": 300, "c": 100}
    pots = compute_side_pots(contributions, folded_player_ids={"a", "b"})
    assert len(pots) == 1  # the empty upper layer merges into pot 1
    assert pots[0].amount == 700
    assert pots[0].eligible_player_ids == ["c"]
    assert sum(p.amount for p in pots) == sum(contributions.values())


def test_no_contributions_returns_no_pots():
    assert compute_side_pots({}, folded_player_ids=set()) == []


def test_zero_amount_contributions_are_ignored():
    contributions = {"a": 0, "b": 100, "c": 100}
    pots = compute_side_pots(contributions, folded_player_ids=set())
    assert len(pots) == 1
    assert "a" not in pots[0].eligible_player_ids


# ---------------------------------------------------------------------------
# award_pots -- integration with real hand rankings
# ---------------------------------------------------------------------------

def _rank(cards_str: str) -> HandRank:
    return evaluate_5(parse_cards(cards_str))


def test_single_pot_single_winner():
    pots = [Pot(300, ["a", "b", "c"])]
    hand_ranks = {
        "a": _rank("Ah Ad Ac Kh Kd"),   # full house, aces full
        "b": _rank("Qh Qd 9c 4s 2h"),   # pair of queens
        "c": _rank("Jh Ts 8c 4d 2c"),   # high card
    }
    payouts = award_pots(pots, hand_ranks, seat_order=["a", "b", "c"])
    assert payouts == {"a": 300}


def test_side_pot_awarded_separately_from_main_pot():
    """
    a is all-in for 100 with the best hand overall. b and c both put in
    300; b has the better hand of the two of them. a should win the main
    pot only; b should win the side pot even though a's hand is stronger
    overall, since a isn't eligible for chips they never had a chance to
    win from b and c's extra bet.
    """
    pots = [
        Pot(300, ["a", "b", "c"]),   # main pot
        Pot(400, ["b", "c"]),        # side pot, a not eligible
    ]
    hand_ranks = {
        "a": _rank("Ah Ad Ac Kh Kd"),   # full house -- best hand at the table
        "b": _rank("Qh Qd 9c 4s 2h"),   # pair of queens -- best among b/c
        "c": _rank("Jh Ts 8c 4d 2c"),   # high card
    }
    payouts = award_pots(pots, hand_ranks, seat_order=["a", "b", "c"])
    assert payouts == {"a": 300, "b": 400}


def test_split_pot_even_division():
    pots = [Pot(400, ["a", "b"])]
    tied_rank = _rank("Ah Kd Qc Js Th")
    hand_ranks = {"a": tied_rank, "b": tied_rank}
    payouts = award_pots(pots, hand_ranks, seat_order=["a", "b"])
    assert payouts == {"a": 200, "b": 200}


def test_split_pot_odd_chip_goes_to_first_winner_in_seat_order():
    pots = [Pot(301, ["a", "b", "c"])]
    tied_rank = _rank("Ah Kd Qc Js Th")
    losing_rank = _rank("2c 3d 5h 7s 9c")
    hand_ranks = {"a": tied_rank, "b": tied_rank, "c": losing_rank}
    # seat order starts at b, so b should get the extra odd chip
    payouts = award_pots(pots, hand_ranks, seat_order=["b", "c", "a"])
    assert payouts["a"] + payouts["b"] == 301
    assert payouts["b"] == 151
    assert payouts["a"] == 150
    assert "c" not in payouts


def test_pot_with_no_eligible_players_raises():
    with pytest.raises(SidePotError):
        award_pots([Pot(100, [])], hand_ranks={}, seat_order=[])


# ---------------------------------------------------------------------------
# End-to-end: uncalled bet -> side pots -> award, in one pass
# ---------------------------------------------------------------------------

def test_full_pipeline_heads_up_uncalled_raise():
    """
    a shoves 500, b can only call 200 (short stack, all-in), so 300 of
    a's bet was never at risk and must be refunded before pot math, and
    a should win only the 400 that was actually contested (200 * 2).
    """
    contributions = {"a": 500, "b": 200}
    adjusted, refund = return_uncalled_bet(contributions)
    assert refund == ("a", 300)

    pots = compute_side_pots(adjusted, folded_player_ids=set())
    assert len(pots) == 1
    assert pots[0].amount == 400

    hand_ranks = {
        "a": _rank("Ah Ad Ac Kh Kd"),
        "b": _rank("2c 3d 5h 7s 9c"),
    }
    payouts = award_pots(pots, hand_ranks, seat_order=["a", "b"])
    # a's total take = pot winnings + the direct refund of the uncalled excess
    total_a = payouts["a"] + refund[1]
    assert total_a == 700  # everything both players put in
    assert payouts.get("b", 0) == 0


def test_full_pipeline_three_way_all_in_with_a_fold():
    """
    a all-in 100, b all-in 250, c folds after putting in 250, d covers
    everyone with 400 (not all-in). Verifies total chip conservation
    across refund + all pot layers + a fold in the mix.
    """
    contributions = {"a": 100, "b": 250, "c": 250, "d": 400}
    adjusted, refund = return_uncalled_bet(contributions)
    assert refund == ("d", 150)  # d's excess above the next-highest (250) refunded
    assert adjusted["d"] == 250

    pots = compute_side_pots(adjusted, folded_player_ids={"c"})
    total_pot_chips = sum(p.amount for p in pots)
    assert total_pot_chips + refund[1] == sum(contributions.values())

    hand_ranks = {
        "a": _rank("2c 3d 5h 7s 9c"),     # worst hand
        "b": _rank("Qh Qd 9c 4s 2h"),     # pair of queens
        "d": _rank("Ah Ad Ac Kh Kd"),     # full house -- best hand, wins every pot eligible for
    }
    payouts = award_pots(pots, hand_ranks, seat_order=["a", "b", "d"])
    total_awarded = sum(payouts.values()) + refund[1]
    assert total_awarded == sum(contributions.values())
    assert payouts["d"] > 0
    assert "c" not in payouts  # folded, never eligible despite contributing chips
