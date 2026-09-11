"""
Hand evaluator for Hold'em Plus.

Standard Texas Hold'em needs "best 5 of 7" (2 hole + 5 community).
Hold'em Plus needs "best 5 of 8" (3 hole + 5 community) at showdown,
since each active player gets a 3rd hole card after the flop.

This module implements a straightforward, easy-to-audit evaluator
(not the fastest possible one -- see NOTE at bottom for a performance
path) so the logic is easy to verify against the test suite before
any performance optimization work happens.
"""

from __future__ import annotations

from collections import Counter
from itertools import combinations
from typing import Sequence, Tuple

from poker_types import Card, HandCategory, HandRank

# Ace-low ("wheel") straight: A-2-3-4-5, where the Ace plays as rank 1.
WHEEL_RANKS = frozenset({14, 2, 3, 4, 5})


def evaluate_5(cards: Sequence[Card]) -> HandRank:
    """Evaluate exactly 5 cards and return their HandRank."""
    if len(cards) != 5:
        raise ValueError(f"evaluate_5 requires exactly 5 cards, got {len(cards)}")

    ranks = sorted((c.rank for c in cards), reverse=True)
    suits = [c.suit for c in cards]

    is_flush = len(set(suits)) == 1
    is_straight, straight_high = _check_straight(ranks)

    rank_counts = Counter(ranks)
    # Sort by (count desc, rank desc) so e.g. trips outrank a higher-rank pair.
    by_count = sorted(rank_counts.items(), key=lambda item: (-item[1], -item[0]))
    counts_shape = sorted(rank_counts.values(), reverse=True)

    if is_straight and is_flush:
        return HandRank(HandCategory.STRAIGHT_FLUSH, (straight_high,))

    if counts_shape == [4, 1]:
        quad_rank = by_count[0][0]
        kicker = by_count[1][0]
        return HandRank(HandCategory.QUADS, (quad_rank, kicker))

    if counts_shape == [3, 2]:
        trips_rank = by_count[0][0]
        pair_rank = by_count[1][0]
        return HandRank(HandCategory.FULL_HOUSE, (trips_rank, pair_rank))

    if is_flush:
        return HandRank(HandCategory.FLUSH, tuple(ranks))

    if is_straight:
        return HandRank(HandCategory.STRAIGHT, (straight_high,))

    if counts_shape == [3, 1, 1]:
        trips_rank = by_count[0][0]
        kickers = tuple(sorted((r for r, c in by_count[1:]), reverse=True))
        return HandRank(HandCategory.TRIPS, (trips_rank,) + kickers)

    if counts_shape == [2, 2, 1]:
        high_pair, low_pair = by_count[0][0], by_count[1][0]
        kicker = by_count[2][0]
        return HandRank(HandCategory.TWO_PAIR, (high_pair, low_pair, kicker))

    if counts_shape == [2, 1, 1, 1]:
        pair_rank = by_count[0][0]
        kickers = tuple(sorted((r for r, c in by_count[1:]), reverse=True))
        return HandRank(HandCategory.PAIR, (pair_rank,) + kickers)

    return HandRank(HandCategory.HIGH_CARD, tuple(ranks))


def _check_straight(ranks_desc: Sequence[int]) -> Tuple[bool, int]:
    """
    ranks_desc: 5 rank values, sorted descending, may include duplicates
    (duplicates mean it can't be a straight). Returns (is_straight, high_card).
    """
    unique = set(ranks_desc)
    if len(unique) != 5:
        return False, 0

    if unique == WHEEL_RANKS:
        return True, 5  # wheel plays as 5-high, not ace-high

    hi, lo = max(unique), min(unique)
    if hi - lo == 4:
        return True, hi

    return False, 0


def evaluate_best_of(cards: Sequence[Card]) -> HandRank:
    """
    Evaluate the best possible 5-card HandRank from any number of cards
    >= 5 (7 for standard Hold'em showdown, 8 for Hold'em Plus showdown).
    """
    if len(cards) < 5:
        raise ValueError(f"Need at least 5 cards to make a hand, got {len(cards)}")
    if len(cards) == 5:
        return evaluate_5(cards)
    return max(evaluate_5(combo) for combo in combinations(cards, 5))


# Rank-name lookup tables for describe_hand_rank() below -- plain
# dictionaries rather than a pluralization algorithm, on purpose:
# English plurals of card ranks have no irregularities here ("Six" ->
# "Sixes" is the only mildly-irregular one), but a direct table is
# still simpler to audit at a glance than any rule would be, matching
# this module's own stated preference for straightforward over clever.
_RANK_NAMES = {
    2: "Two", 3: "Three", 4: "Four", 5: "Five", 6: "Six", 7: "Seven",
    8: "Eight", 9: "Nine", 10: "Ten", 11: "Jack", 12: "Queen", 13: "King",
    14: "Ace",
}
_RANK_PLURALS = {
    2: "Twos", 3: "Threes", 4: "Fours", 5: "Fives", 6: "Sixes", 7: "Sevens",
    8: "Eights", 9: "Nines", 10: "Tens", 11: "Jacks", 12: "Queens",
    13: "Kings", 14: "Aces",
}


def describe_hand_rank(rank: HandRank) -> str:
    """
    Human-readable description of a HandRank, e.g. "Full House, Aces
    full of Kings" or "Two Pair, Jacks and Fours" -- the specific
    player-facing strings POLISH_PLAN.md's Phase 0.5b calls for next to
    each revealed hand at showdown.

    Deliberately separate from HandRank.__repr__ (poker_types.py), which
    stays a compact, programmer-facing repr (e.g. "FULL_HOUSE(13, 12)")
    used for engine-side debugging/printing (see example_usage.py) --
    changing this function's wording should never risk changing what
    __repr__ prints for debugging, or vice versa.

    Every HandCategory has a real branch below; there's no silent
    fallback. If a future HandCategory is ever added to poker_types.py
    without a matching branch here, this raises rather than returning
    something misleading -- the same "surface a bug loudly rather than
    paper over it" preference side_pots.SidePotError already documents
    for this codebase.
    """
    tb = rank.tiebreak
    if rank.category == HandCategory.STRAIGHT_FLUSH:
        return f"Straight Flush, {_RANK_NAMES[tb[0]]}-high"
    if rank.category == HandCategory.QUADS:
        return f"Four of a Kind, {_RANK_PLURALS[tb[0]]}"
    if rank.category == HandCategory.FULL_HOUSE:
        return f"Full House, {_RANK_PLURALS[tb[0]]} full of {_RANK_PLURALS[tb[1]]}"
    if rank.category == HandCategory.FLUSH:
        return f"Flush, {_RANK_NAMES[tb[0]]}-high"
    if rank.category == HandCategory.STRAIGHT:
        return f"Straight, {_RANK_NAMES[tb[0]]}-high"
    if rank.category == HandCategory.TRIPS:
        return f"Three of a Kind, {_RANK_PLURALS[tb[0]]}"
    if rank.category == HandCategory.TWO_PAIR:
        return f"Two Pair, {_RANK_PLURALS[tb[0]]} and {_RANK_PLURALS[tb[1]]}"
    if rank.category == HandCategory.PAIR:
        return f"Pair of {_RANK_PLURALS[tb[0]]}"
    if rank.category == HandCategory.HIGH_CARD:
        return f"High Card, {_RANK_NAMES[tb[0]]}"
    raise ValueError(f"No description implemented for category {rank.category!r}")


# NOTE on performance:
# This implementation re-evaluates from scratch every call, and for 8 cards
# checks all C(8,5) = 56 combinations. That's more than fast enough for
# server-side showdown evaluation (showdowns are rare relative to actions
# per hand) and for unit testing. If profiling later shows the evaluator as
# a hotspot -- e.g. if it gets reused for Monte Carlo equity calculations in
# a "trainer mode" -- swap in a lookup-table-based evaluator (e.g. a
# Cactus-Kev/2+2-style perfect-hash evaluator) behind this same
# evaluate_best_of() signature so nothing else in the codebase has to change.
