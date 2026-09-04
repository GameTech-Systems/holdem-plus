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


# NOTE on performance:
# This implementation re-evaluates from scratch every call, and for 8 cards
# checks all C(8,5) = 56 combinations. That's more than fast enough for
# server-side showdown evaluation (showdowns are rare relative to actions
# per hand) and for unit testing. If profiling later shows the evaluator as
# a hotspot -- e.g. if it gets reused for Monte Carlo equity calculations in
# a "trainer mode" -- swap in a lookup-table-based evaluator (e.g. a
# Cactus-Kev/2+2-style perfect-hash evaluator) behind this same
# evaluate_best_of() signature so nothing else in the codebase has to change.
