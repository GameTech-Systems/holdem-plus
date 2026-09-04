"""
Side-pot math for Hold'em Plus multi-way all-ins.

Deliberately kept as a standalone module (rather than folded into
BettingRound) since pot construction only needs to run once, at the end
of a hand, from each player's final `committed_total` for that hand --
it doesn't need to know about streets, action order, or betting legality
at all, and keeping it separate makes it independently testable and
independently auditable (side-pot bugs are one of the most common and
most disputed classes of bug in real poker software).

Two-step process:
  1. return_uncalled_bet() -- if the single largest contributor put in
     more than anyone else could possibly match, the excess never went
     into contest and must be returned to them before pot math even
     starts (this is the "uncalled bet" rule).
  2. compute_side_pots() -- turns a (possibly capped) set of
     per-player contributions into an ordered list of Pots, each with
     an amount and the set of players still eligible to win it (folded
     players' chips count toward pot size but they're not eligible).

award_pots() then resolves each pot independently against final hand
rankings, splitting ties and handling odd-chip remainders.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from poker_types import HandRank


@dataclass
class Pot:
    amount: int
    eligible_player_ids: List[str]

    def __repr__(self) -> str:
        return f"Pot({self.amount}, eligible={self.eligible_player_ids})"


class SidePotError(Exception):
    pass


def return_uncalled_bet(
    contributions: Dict[str, int]
) -> Tuple[Dict[str, int], Optional[Tuple[str, int]]]:
    """
    If exactly one player contributed strictly more than every other
    contributor, the amount above the next-highest contribution was never
    at risk against anyone and must be returned to them.

    Returns (adjusted_contributions, refund) where refund is either None
    or (player_id, amount_refunded).

    Note: this only resolves the single largest uncalled excess. In
    correctly-implemented betting (BettingRound rejects a raise no one
    can possibly call, and a bet against all-folded opponents ends the
    hand before any further contribution occurs), that's the only case
    that can arise in practice. Deeply nested cases -- e.g. two different
    players both left with "uncalled" amounts above a third, shorter
    stack -- shouldn't occur if uncalled-bet return is applied whenever a
    betting round closes with an unmatched raise, not just once at the
    very end of the hand; see the module-level docstring in
    betting_state_machine.py and the test suite for this module for the
    reasoning.
    """
    positive = {pid: amt for pid, amt in contributions.items() if amt > 0}
    if len(positive) < 2:
        return dict(contributions), None

    sorted_amounts = sorted(positive.values(), reverse=True)
    highest, second_highest = sorted_amounts[0], sorted_amounts[1]
    if highest <= second_highest:
        return dict(contributions), None

    top_players = [pid for pid, amt in positive.items() if amt == highest]
    if len(top_players) != 1:
        # tied for the top spot -- both were "called" by each other, nothing uncalled
        return dict(contributions), None

    pid = top_players[0]
    refund_amount = highest - second_highest
    adjusted = dict(contributions)
    adjusted[pid] -= refund_amount
    return adjusted, (pid, refund_amount)


def compute_side_pots(
    contributions: Dict[str, int],
    folded_player_ids: Set[str],
) -> List[Pot]:
    """
    Build the ordered list of pots from final per-player contributions.

    Standard peeling algorithm: repeatedly find the smallest remaining
    contribution among players who still have chips left to peel, and
    carve a pot out of that amount from every remaining contributor
    (folded players' chips count toward the pot's size; only non-folded
    players are added to that pot's eligible list). This naturally
    produces however many pot layers a given all-in structure requires.
    """
    remaining = {pid: amt for pid, amt in contributions.items() if amt > 0}
    if not remaining:
        return []

    pots: List[Pot] = []
    while remaining:
        min_amt = min(remaining.values())
        layer_amount = 0
        eligible: List[str] = []
        for pid in list(remaining.keys()):
            layer_amount += min_amt
            remaining[pid] -= min_amt
            if remaining[pid] == 0:
                del remaining[pid]
            if pid not in folded_player_ids:
                eligible.append(pid)

        if not eligible:
            # Every contributor to this layer folded. This is a known
            # simplification (see docstring): fold the dead chips forward
            # into the next lower pot layer that does have eligible
            # players, rather than losing track of them. It keeps total
            # chip accounting exact (nothing created or destroyed) even
            # though it's a simplified resolution of a rare edge case.
            if pots:
                pots[-1].amount += layer_amount
            else:
                # No prior pot to fold into and nobody eligible at all --
                # this indicates a bug further upstream (a hand can't
                # reach showdown with zero non-folded contributors).
                raise SidePotError(
                    "No eligible players for the first pot layer -- check "
                    "upstream fold/contribution bookkeeping."
                )
            continue

        pots.append(Pot(amount=layer_amount, eligible_player_ids=eligible))

    return _merge_adjacent_identical_pots(pots)


def _merge_adjacent_identical_pots(pots: List[Pot]) -> List[Pot]:
    """Cosmetic simplification: merge consecutive layers with the exact
    same eligible set into one pot, since splitting them serves no
    purpose for award_pots() and just clutters hand-history display."""
    merged: List[Pot] = []
    for pot in pots:
        if merged and merged[-1].eligible_player_ids == pot.eligible_player_ids:
            merged[-1].amount += pot.amount
        else:
            merged.append(Pot(pot.amount, list(pot.eligible_player_ids)))
    return merged


def award_pots(
    pots: List[Pot],
    hand_ranks: Dict[str, HandRank],
    seat_order: List[str],
) -> Dict[str, int]:
    """
    Resolve every pot against final showdown hand rankings.

    seat_order should be the full table's seating order starting from
    whoever acts first after the button (i.e. the same convention used
    for post-flop action order), since it's used to decide who receives
    odd chips that don't divide evenly among tied winners -- the
    standard house rule awards odd chips starting from the first tied
    winner in seat order after the button.
    """
    payouts: Dict[str, int] = {}

    for pot in pots:
        eligible = pot.eligible_player_ids
        if not eligible:
            raise SidePotError(f"Pot with no eligible players: {pot!r}")

        best_rank = max(hand_ranks[pid] for pid in eligible)
        winners = [pid for pid in eligible if hand_ranks[pid] == best_rank]

        share, remainder = divmod(pot.amount, len(winners))
        for pid in winners:
            payouts[pid] = payouts.get(pid, 0) + share

        if remainder:
            ordered_winners = [pid for pid in seat_order if pid in winners]
            # seat_order might not list every winner (e.g. caller passed a
            # partial order) -- fall back to whatever order winners came in
            if len(ordered_winners) != len(winners):
                ordered_winners = winners
            for i in range(remainder):
                recipient = ordered_winners[i % len(ordered_winners)]
                payouts[recipient] = payouts.get(recipient, 0) + 1

    return payouts
