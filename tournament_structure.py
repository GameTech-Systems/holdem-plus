"""
Tournament / blind-escalation layer for Hold'em Plus, implementing the
"Simple Format Option" from the source concept:

  Each player begins with 40 chips each worth 1. 1,2 blinds to begin,
  then 2,4 - 3,6 - 4,8 - 5,10 then doubling every 15 min.

This module is deliberately built around a configurable BlindSchedule
rather than hard-coding just those numbers, since the source material
explicitly calls out variable criteria per game level ("antes/blinds
straight doubling sequence, speed-rounds, fewer than 10 players if the
$ difference is made up, payout splits allowed/not allowed, etc.") --
the Base/Low/Mid/... Level structure implies the same engine needs to
run many different stake levels, not just one fixed schedule.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Blind schedule
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BlindLevel:
    level_number: int          # 1-indexed
    small_blind: int
    big_blind: int
    ante: int = 0
    duration_seconds: int = 900  # 15 minutes, matching the source spec

    def __repr__(self) -> str:
        ante_part = f"/{self.ante} ante" if self.ante else ""
        return f"L{self.level_number}({self.small_blind}/{self.big_blind}{ante_part})"


def generate_default_schedule(num_levels: int = 12) -> List[BlindLevel]:
    """
    Recreates the exact sequence from the source spec:
        1,2 -> 2,4 -> 3,6 -> 4,8 -> 5,10 -> then doubling every level.
    i.e. levels 1-5 are fixed steps, and from level 6 onward each level's
    blinds are double the previous level's (10,20 -> 20,40 -> 40,80 ...).
    """
    if num_levels < 1:
        raise ValueError("num_levels must be at least 1")

    fixed_steps = [(1, 2), (2, 4), (3, 6), (4, 8), (5, 10)]
    levels: List[BlindLevel] = []

    for i, (sb, bb) in enumerate(fixed_steps[:num_levels], start=1):
        levels.append(BlindLevel(level_number=i, small_blind=sb, big_blind=bb))

    while len(levels) < num_levels:
        prev = levels[-1]
        levels.append(
            BlindLevel(
                level_number=prev.level_number + 1,
                small_blind=prev.small_blind * 2,
                big_blind=prev.big_blind * 2,
            )
        )

    return levels


def generate_custom_schedule(
    starting_small_blind: int,
    starting_big_blind: int,
    num_levels: int,
    level_duration_seconds: int = 900,
    growth: str = "double",  # "double" or a fixed increment via `increment`
    increment: Optional[int] = None,
    ante_schedule: Optional[Dict[int, int]] = None,
) -> List[BlindLevel]:
    """
    General-purpose schedule builder for the other stake levels described
    in the source (Base/Low/Mid/Big/High/Pro/Grand/Great), speed rounds
    (shorter level_duration_seconds), or straight-increment structures
    instead of doubling.
    """
    if num_levels < 1:
        raise ValueError("num_levels must be at least 1")
    if growth not in ("double", "increment"):
        raise ValueError("growth must be 'double' or 'increment'")
    if growth == "increment" and increment is None:
        raise ValueError("increment must be provided when growth='increment'")

    ante_schedule = ante_schedule or {}
    levels: List[BlindLevel] = []
    sb, bb = starting_small_blind, starting_big_blind

    for i in range(1, num_levels + 1):
        levels.append(
            BlindLevel(
                level_number=i,
                small_blind=sb,
                big_blind=bb,
                ante=ante_schedule.get(i, 0),
                duration_seconds=level_duration_seconds,
            )
        )
        if growth == "double":
            sb, bb = sb * 2, bb * 2
        else:
            sb, bb = sb + increment, bb + increment  # type: ignore[operator]

    return levels


@dataclass
class BlindClock:
    """
    Tracks tournament time and reports the current blind level, given a
    schedule and elapsed seconds. Kept as a pure function of elapsed time
    (no wall-clock/threading concerns) so it's trivial to unit test and
    trivial to drive from either a live wall clock or a fast-forwarded
    simulation.
    """

    schedule: List[BlindLevel]

    def level_at(self, elapsed_seconds: int) -> BlindLevel:
        if elapsed_seconds < 0:
            raise ValueError("elapsed_seconds must be non-negative")

        cursor = 0
        for level in self.schedule:
            cursor += level.duration_seconds
            if elapsed_seconds < cursor:
                return level
        return self.schedule[-1]  # tournament has run past the defined schedule

    def seconds_remaining_in_level(self, elapsed_seconds: int) -> int:
        cursor = 0
        for level in self.schedule:
            cursor += level.duration_seconds
            if elapsed_seconds < cursor:
                return cursor - elapsed_seconds
        return 0  # past the end of the defined schedule

    def next_level(self, elapsed_seconds: int) -> Optional[BlindLevel]:
        current = self.level_at(elapsed_seconds)
        idx = current.level_number - 1
        if idx + 1 < len(self.schedule):
            return self.schedule[idx + 1]
        return None


def chips_in_big_blinds(stack: int, level: BlindLevel) -> float:
    """Stack depth expressed in big blinds -- the standard way tournament
    players and commentary describe how deep/short a stack is."""
    if level.big_blind == 0:
        raise ValueError("Big blind cannot be zero")
    return stack / level.big_blind


# ---------------------------------------------------------------------------
# Payout structures
# ---------------------------------------------------------------------------
# The source material explicitly calls out both a "winner-take-all fashion"
# default and "payout splits allowed/not allowed" as a configurable variant
# (e.g. players chopping equally, or a Level 8 "chopped pot at player's
# preference"). These three functions cover the shapes described.

def winner_take_all(prize_pool: int, ordered_finishers: List[str]) -> Dict[str, int]:
    """Standard sit-and-go default per the source spec."""
    if not ordered_finishers:
        raise ValueError("ordered_finishers must not be empty")
    return {ordered_finishers[0]: prize_pool}


def chop_evenly(prize_pool: int, players: List[str]) -> Dict[str, int]:
    """
    Even split among the given players (e.g. a player's-preference chop
    at the final table, or the "chopped pot" option called out for the
    Great Level 8 games). Any remainder chip(s) that don't divide evenly
    are handed out one at a time in the given player order, matching the
    same odd-chip convention used in side_pots.award_pots.
    """
    if not players:
        raise ValueError("players must not be empty")
    share, remainder = divmod(prize_pool, len(players))
    payouts = {p: share for p in players}
    for i in range(remainder):
        payouts[players[i % len(players)]] += 1
    return payouts


def payout_curve(
    prize_pool: int,
    ordered_finishers: List[str],
    percentages: List[float],
) -> Dict[str, int]:
    """
    Top-heavy payout curve for larger fields, e.g. 1st=50%, 2nd=30%,
    3rd=20%. `percentages` must be listed in finishing-position order
    (1st place first) and sum to 1.0 (within floating-point tolerance).
    Rounds down to whole chips per position, then distributes any
    leftover chips (from rounding) to the top finishers first, so the
    payouts always sum to exactly prize_pool with no chips lost.
    """
    if not ordered_finishers:
        raise ValueError("ordered_finishers must not be empty")
    if len(percentages) > len(ordered_finishers):
        raise ValueError("more percentages than finishers to pay")
    if abs(sum(percentages) - 1.0) > 1e-6:
        raise ValueError(f"percentages must sum to 1.0, got {sum(percentages)}")

    raw_shares = [prize_pool * pct for pct in percentages]
    payouts = {
        finisher: int(share)
        for finisher, share in zip(ordered_finishers, raw_shares)
    }
    distributed = sum(payouts.values())
    leftover = prize_pool - distributed

    i = 0
    while leftover > 0:
        finisher = ordered_finishers[i % len(percentages)]
        payouts[finisher] += 1
        leftover -= 1
        i += 1

    return payouts
