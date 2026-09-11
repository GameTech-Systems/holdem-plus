"""
Hand-evaluator test cases for Hold'em Plus.

Organized in three tiers:
  1. evaluate_5 correctness for each of the 9 standard hand categories
     (including the wheel-straight edge case).
  2. Category-ordering and tiebreak/kicker comparisons.
  3. evaluate_best_of() over 8 cards -- the Hold'em Plus-specific case
     (3 hole + 5 community), including scenarios that only exist because
     of the extra hole card and wouldn't arise in standard 7-card Hold'em.

Run with: pytest -v test_hand_evaluator.py
"""

import pytest

from itertools import combinations

from hand_evaluator import describe_hand_rank, evaluate_5, evaluate_best_of
from poker_types import HandCategory, parse_cards


# ---------------------------------------------------------------------------
# Tier 1: evaluate_5 -- one representative case per category
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "cards, expected_category",
    [
        ("Ah Kh Qh Jh Th", HandCategory.STRAIGHT_FLUSH),
        ("5h 4h 3h 2h Ah", HandCategory.STRAIGHT_FLUSH),  # wheel straight flush
        ("9c 9d 9h 9s 2c", HandCategory.QUADS),
        ("Kc Kd Kh 4s 4c", HandCategory.FULL_HOUSE),
        ("2h 5h 9h Jh Kh", HandCategory.FLUSH),
        ("Ah Kd Qc Js Th", HandCategory.STRAIGHT),
        ("5c 4d 3h 2s Ah", HandCategory.STRAIGHT),        # wheel, not flush
        ("7c 7d 7h Ks 2c", HandCategory.TRIPS),
        ("Jc Jd 4h 4s 9c", HandCategory.TWO_PAIR),
        ("Qc Qd 9h 4s 2c", HandCategory.PAIR),
        ("Ac Kd 9h 4s 2c", HandCategory.HIGH_CARD),
    ],
)
def test_category_identification(cards, expected_category):
    hand = evaluate_5(parse_cards(cards))
    assert hand.category == expected_category


def test_wheel_straight_high_card_is_five_not_ace():
    """A-2-3-4-5 is the lowest straight; its 'high card' for comparison is 5."""
    wheel = evaluate_5(parse_cards("5c 4d 3h 2s Ah"))
    assert wheel.category == HandCategory.STRAIGHT
    assert wheel.tiebreak == (5,)


def test_six_high_straight_beats_wheel():
    wheel = evaluate_5(parse_cards("5c 4d 3h 2s Ah"))
    six_high = evaluate_5(parse_cards("6c 5d 4h 3s 2c"))
    assert six_high > wheel


def test_broadway_is_ace_high_not_wheel():
    broadway = evaluate_5(parse_cards("Ah Kd Qc Js Th"))
    assert broadway.category == HandCategory.STRAIGHT
    assert broadway.tiebreak == (14,)


def test_four_flush_five_different_ranks_is_not_a_straight_or_flush():
    """Guards against a false-positive straight/flush on near-miss hands."""
    hand = evaluate_5(parse_cards("2h 5h 9h Jh Kc"))  # 4 hearts + 1 off-suit
    assert hand.category == HandCategory.HIGH_CARD


# ---------------------------------------------------------------------------
# Tier 2: ordering and tiebreak / kicker correctness
# ---------------------------------------------------------------------------

def test_category_ordering_top_to_bottom():
    straight_flush = evaluate_5(parse_cards("9h 8h 7h 6h 5h"))
    quads = evaluate_5(parse_cards("Ac Ad Ah As Kc"))
    full_house = evaluate_5(parse_cards("Ac Ad Ah Ks Kc"))
    flush = evaluate_5(parse_cards("2h 5h 9h Jh Kh"))
    straight = evaluate_5(parse_cards("9c 8d 7h 6s 5c"))
    trips = evaluate_5(parse_cards("7c 7d 7h Ks 2c"))
    two_pair = evaluate_5(parse_cards("Jc Jd 4h 4s 9c"))
    pair = evaluate_5(parse_cards("Qc Qd 9h 4s 2c"))
    high_card = evaluate_5(parse_cards("Ac Kd 9h 4s 2c"))

    ordered = [
        high_card, pair, two_pair, trips, straight,
        flush, full_house, quads, straight_flush,
    ]
    for weaker, stronger in zip(ordered, ordered[1:]):
        assert stronger > weaker


def test_full_house_ranked_by_trips_not_pair():
    """A-A-A-K-K must beat K-K-K-A-A -- the trips rank decides, not the pair."""
    aces_full = evaluate_5(parse_cards("Ac Ad Ah Ks Kc"))
    kings_full = evaluate_5(parse_cards("Kc Kd Kh As Ac".replace("Ac", "Ah")))  # avoid dup card below
    kings_full = evaluate_5(parse_cards("Kc Kd Kh 2s 2c"))
    aces_full_2 = evaluate_5(parse_cards("Ac Ad Ah 3s 3c"))
    assert aces_full > kings_full
    assert aces_full_2 > kings_full


def test_two_pair_kicker_breaks_tie():
    jacks_fours_king_kicker = evaluate_5(parse_cards("Jc Jd 4h 4s Kc"))
    jacks_fours_nine_kicker = evaluate_5(parse_cards("Jh Js 4c 4d 9c"))
    assert jacks_fours_king_kicker > jacks_fours_nine_kicker


def test_pair_kickers_compared_in_order():
    pair_aces_king_kicker = evaluate_5(parse_cards("2c 2d Ah Kd 9c"))
    pair_aces_queen_kicker = evaluate_5(parse_cards("2h 2s Ac Qd 9h"))
    assert pair_aces_king_kicker > pair_aces_queen_kicker


def test_identical_hands_are_a_tie():
    """Two hands with the same category and tiebreak tuple must be equal
    (i.e. this evaluator correctly signals a split pot)."""
    hand_a = evaluate_5(parse_cards("Ah Kd Qc Js Th"))
    hand_b = evaluate_5(parse_cards("As Kc Qh Jd Tc"))
    assert hand_a == hand_b


def test_flush_ties_broken_by_highest_non_matching_card():
    higher_flush = evaluate_5(parse_cards("Ah Jh 9h 5h 3h"))
    lower_flush = evaluate_5(parse_cards("Ad Jd 9d 5d 2d"))
    assert higher_flush > lower_flush


# ---------------------------------------------------------------------------
# Tier 3: evaluate_best_of() over 8 cards -- Hold'em Plus specific
# ---------------------------------------------------------------------------

def test_eight_card_combination_count_is_fifty_six():
    """Sanity check on the search space: C(8,5) = 56 candidate hands."""
    cards = parse_cards("Ah Kd Qc Js Th 9c 2d 2h")
    assert len(list(combinations(cards, 5))) == 56


def test_best_of_eight_picks_flush_over_worse_options():
    # 3 hole cards + 5 community; a heart flush is available among the 8.
    cards = parse_cards("Ah Jh 3h Kd Qc 9h 4h 2s")
    hand = evaluate_best_of(cards)
    assert hand.category == HandCategory.FLUSH
    assert hand.tiebreak == (14, 11, 9, 4, 3)  # A J 9 4 3 of hearts, best 5


def test_third_hole_card_enables_a_hand_unreachable_with_two_hole_cards():
    """
    Cleaner version of the "extra card matters" scenario: with only the
    2 standard hole cards, the best available hand is two pair. The 3rd
    hole card completes a straight that is impossible using any 5 of the
    other 7 cards.
    """
    two_hole_cards = parse_cards("6h 6d")
    third_hole_card = parse_cards("Th")
    community = parse_cards("9c 8d 7s 2h 2c")

    seven_card_best = evaluate_best_of(two_hole_cards + community)
    assert seven_card_best.category == HandCategory.TWO_PAIR

    eight_card_best = evaluate_best_of(two_hole_cards + third_hole_card + community)
    assert eight_card_best.category == HandCategory.STRAIGHT
    assert eight_card_best.tiebreak == (10,)  # T-9-8-7-6, ten-high straight
    assert eight_card_best > seven_card_best


def test_best_of_eight_never_worse_than_best_of_seven_subset():
    """
    Structural invariant: adding a card to the pool can never make the best
    achievable 5-card hand worse. This should hold for every Hold'em Plus
    hand, since evaluate_best_of() searches strictly more combinations.
    """
    seven_cards = parse_cards("Ah Kd Qc Js 9h 4d 2s")
    extra_card = parse_cards("Th")[0]

    best_of_7 = evaluate_best_of(seven_cards)
    best_of_8 = evaluate_best_of(seven_cards + (extra_card,))

    assert best_of_8 >= best_of_7


def test_no_duplicate_cards_across_hole_and_community_is_caller_responsibility():
    """
    Documents an assumption rather than testing evaluator behavior: the
    evaluator trusts its input and does not itself detect an impossible
    duplicate card (e.g. the same card dealt to two players). Duplicate
    detection belongs in the dealing/shuffle layer (single-deck draw
    without replacement), not the evaluator. This test just pins down
    that evaluate_best_of() does not raise on a technically-invalid input,
    so nobody "fixes" that away and hides a real dealing bug behind a
    silent evaluator-level exception instead of surfacing it at the deal.
    """
    cards_with_duplicate = parse_cards("Ah Ah Kd Qc Js 9h 4d 2s")
    # Should not raise -- it just evaluates the 8 cards it was given.
    evaluate_best_of(cards_with_duplicate)


# ---------------------------------------------------------------------------
# describe_hand_rank -- player-facing hand descriptions (POLISH_PLAN.md
# Phase 0.5b)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "cards, expected_description",
    [
        ("9h 8h 7h 6h 5h", "Straight Flush, Nine-high"),
        ("9c 9d 9h 9s 2c", "Four of a Kind, Nines"),
        ("Kc Kd Kh 4s 4c", "Full House, Kings full of Fours"),
        ("2h 5h 9h Jh Kh", "Flush, King-high"),
        ("Ah Kd Qc Js Th", "Straight, Ace-high"),
        ("5c 4d 3h 2s Ah", "Straight, Five-high"),  # the wheel plays 5-high
        ("7c 7d 7h Ks 2c", "Three of a Kind, Sevens"),
        ("Jc Jd 4h 4s 9c", "Two Pair, Jacks and Fours"),
        ("Qc Qd 9h 4s 2c", "Pair of Queens"),
        ("Ac Kd 9h 4s 2c", "High Card, Ace"),
    ],
)
def test_describe_hand_rank_covers_every_category_with_the_right_wording(cards, expected_description):
    """One example per HandCategory (plus the wheel-straight edge case),
    matching test_category_identification's own per-category coverage
    above -- every category must produce a real, specific string."""
    rank = evaluate_5(parse_cards(cards))
    assert describe_hand_rank(rank) == expected_description


def test_describe_hand_rank_full_house_names_trips_before_pair():
    """A-A-A-K-K must read 'Aces full of Kings', not the reverse --
    the same point test_full_house_ranked_by_trips_not_pair makes about
    comparison, here applied to the description's wording instead."""
    aces_full = evaluate_5(parse_cards("Ac Ad Ah Ks Kc"))
    kings_full = evaluate_5(parse_cards("Kc Kd Kh 2s 2c"))
    assert describe_hand_rank(aces_full) == "Full House, Aces full of Kings"
    assert describe_hand_rank(kings_full) == "Full House, Kings full of Twos"
