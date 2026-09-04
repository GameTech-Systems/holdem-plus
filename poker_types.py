"""
Core card / hand primitives for Hold'em Plus.

Kept deliberately small and dependency-free so both the hand evaluator
and the betting-round state machine can share a single definition of
"what a card is" and "what a hand category is."
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Tuple

RANKS = "23456789TJQKA"
SUITS = "cdhs"  # clubs, diamonds, hearts, spades

RANK_VALUES = {r: i + 2 for i, r in enumerate(RANKS)}  # '2' -> 2 ... 'A' -> 14


@dataclass(frozen=True, order=True)
class Card:
    rank: int  # 2..14
    suit: str  # one of SUITS

    def __repr__(self) -> str:
        rank_char = RANKS[self.rank - 2]
        return f"{rank_char}{self.suit}"

    @staticmethod
    def parse(text: str) -> "Card":
        """Parse a 2-char shorthand like 'Ah', 'Td', '9c' into a Card."""
        if len(text) != 2:
            raise ValueError(f"Invalid card string: {text!r}")
        rank_char, suit_char = text[0].upper(), text[1].lower()
        if rank_char not in RANKS or suit_char not in SUITS:
            raise ValueError(f"Invalid card string: {text!r}")
        return Card(RANK_VALUES[rank_char], suit_char)


def parse_cards(text: str) -> Tuple[Card, ...]:
    """Parse a space-separated shorthand string, e.g. 'Ah Kd 9c 9d 2s'."""
    return tuple(Card.parse(tok) for tok in text.split())


def full_deck() -> Tuple[Card, ...]:
    return tuple(Card(RANK_VALUES[r], s) for r in RANKS for s in SUITS)


class HandCategory(IntEnum):
    HIGH_CARD = 0
    PAIR = 1
    TWO_PAIR = 2
    TRIPS = 3
    STRAIGHT = 4
    FLUSH = 5
    FULL_HOUSE = 6
    QUADS = 7
    STRAIGHT_FLUSH = 8


@dataclass(frozen=True, order=True)
class HandRank:
    """
    Fully ordered representation of a made 5-card hand's strength.

    `category` dominates comparisons; `tiebreak` is a descending tuple of
    rank values used to break ties within the same category (e.g. for two
    pair: (high_pair, low_pair, kicker)). Because it's a plain tuple of
    ints wrapped in a frozen dataclass with order=True, HandRank instances
    compare correctly with standard Python operators (<, >, ==), and equal
    HandRanks represent a tied/split-pot hand.
    """

    category: HandCategory
    tiebreak: Tuple[int, ...]

    def __repr__(self) -> str:
        return f"{self.category.name}{self.tiebreak}"
