"""
Analytics / instrumentation layer for Hold'em Plus.

This is what actually tests the hypothesis from the tech plan (Section
3.3, instrumentation bullet): is Hold'em Plus faster and more
action-packed than standard Hold'em? That question can only be
answered from real usage data, and this module is where that data gets
captured and summarized. Before this module, the project could prove
the game *runs*, but had nothing that could show it's *better* --
see HANDOFF.md.

Deliberately built as a pure, dependency-free read layer on top of
`HandResult` (from orchestrator.py) rather than something threaded
through the engine itself: every hand the engine plays already produces
a `HandResult`. This module's only job is turning a stream of those
into the specific numbers the tech plan calls out:

  - hands per hour
  - average pot size relative to the blinds
  - showdown frequency (showdown vs. won-by-fold)
  - hand-strength distribution at showdown (pairs/two-pair/.../straight
    flush rate), compared against a standard-Hold'em baseline
  - a lightweight player-reported excitement signal (thumbs up/down)

Nothing here mutates game state or `HandResult` itself -- api.py (or
any other caller) builds a `HandRecord` right after a hand completes,
while it still has the blind level / clock / seat-count context that
only lives on the `Hand`/`Tournament` objects, and hands it to an
`AnalyticsLog`.
"""

from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from hand_evaluator import evaluate_best_of
from orchestrator import HandResult
from poker_types import HandCategory, full_deck


@dataclass
class HandRecord:
    """
    One completed hand's worth of analytics-relevant facts.

    Deliberately a smaller, different shape than `HandResult`:
    `HandResult` is the engine's authoritative settlement record
    (payouts, refund, pots, revealed hole cards); `HandRecord` is just
    the handful of derived numbers the tech plan's hypothesis-testing
    actually needs, plus the bits of context (blinds, clock position,
    seats dealt in) that live on `Hand`/`Tournament`, not on
    `HandResult` itself.
    """
    small_blind: int
    big_blind: int
    elapsed_seconds: int          # Tournament.elapsed_seconds at completion
    num_dealt_in: int             # players seated for this hand
    num_folded: int
    pot_total: int
    went_to_showdown: bool
    showdown_categories: Tuple[HandCategory, ...]  # one entry per revealed hand


def build_hand_record(
    result: HandResult,
    *,
    small_blind: int,
    big_blind: int,
    elapsed_seconds: int,
    num_dealt_in: int,
) -> HandRecord:
    """
    Derives a HandRecord from a completed hand's HandResult plus the
    context (blinds/clock/seat count) that only the caller -- whoever
    just called `Tournament.complete_hand()` -- still has to hand, since
    HandResult itself doesn't carry it.

    Recomputing each revealed hand's HandCategory here (rather than
    threading it through from `orchestrator.Hand._finalize()`) keeps
    `HandResult` itself unchanged and keeps this module strictly a
    read-only consumer of it -- evaluate_best_of() is cheap (a handful
    of best-5-of-8 comparisons) and this only runs once per completed
    hand, not in any hot path.
    """
    showdown_categories = tuple(
        evaluate_best_of(list(hole_cards) + list(result.community_cards)).category
        for hole_cards in result.revealed_hands.values()
    )
    return HandRecord(
        small_blind=small_blind,
        big_blind=big_blind,
        elapsed_seconds=elapsed_seconds,
        num_dealt_in=num_dealt_in,
        num_folded=len(result.folded_players),
        pot_total=sum(result.payouts.values()),
        went_to_showdown=bool(result.revealed_hands),
        showdown_categories=showdown_categories,
    )


def _category_fractions(categories: List[HandCategory]) -> Dict[str, float]:
    if not categories:
        return {}
    counts = Counter(categories)
    total = len(categories)
    return {cat.name: count / total for cat, count in counts.items()}


@dataclass
class AnalyticsLog:
    """
    Accumulates HandRecords for one table/session and answers the
    specific questions the tech plan's instrumentation bullet calls
    out: hands/hour, pot size relative to blinds, showdown frequency,
    and hand-strength distribution at showdown. Player-reported
    excitement (thumbs up/down) is tracked alongside it since it's the
    same "one lightweight log per table" concept, even though it
    doesn't derive from HandResult at all.

    Deliberately dependency-free and storage-agnostic: it's a plain
    in-memory list here (matching the rest of the demo API's storage
    model -- see api.py's own module docstring), but nothing about the
    shape assumes that; swapping in a database-backed version later
    only needs to preserve record_hand()/record_feedback()/summary().
    """
    records: List[HandRecord] = field(default_factory=list)
    thumbs_up: int = 0
    thumbs_down: int = 0

    def record_hand(self, record: HandRecord) -> None:
        self.records.append(record)

    def record_feedback(self, thumbs_up: bool) -> None:
        if thumbs_up:
            self.thumbs_up += 1
        else:
            self.thumbs_down += 1

    def hands_per_hour(self) -> Optional[float]:
        """
        None until there are at least two recorded hands to measure a
        rate between (a single hand has no elapsed interval to divide
        by). Uses len(records) - 1 intervals spanning the recorded
        elapsed-time range, scaled to a per-hour rate -- the standard
        way poker software reports table speed.
        """
        if len(self.records) < 2:
            return None
        elapsed = self.records[-1].elapsed_seconds - self.records[0].elapsed_seconds
        if elapsed <= 0:
            return None
        return (len(self.records) - 1) / elapsed * 3600

    def average_pot_in_big_blinds(self) -> Optional[float]:
        ratios = [r.pot_total / r.big_blind for r in self.records if r.big_blind > 0]
        if not ratios:
            return None
        return sum(ratios) / len(ratios)

    def showdown_frequency(self) -> Optional[float]:
        if not self.records:
            return None
        showdowns = sum(1 for r in self.records if r.went_to_showdown)
        return showdowns / len(self.records)

    def category_distribution(self) -> Dict[str, float]:
        """
        Fraction of all *revealed showdown hands* (not hands played --
        a 3-way showdown contributes 3 data points) falling into each
        HandCategory. Empty dict if nothing's reached showdown yet.
        """
        all_categories = [c for r in self.records for c in r.showdown_categories]
        return _category_fractions(all_categories)

    def summary(self) -> Dict[str, object]:
        return {
            "hands_recorded": len(self.records),
            "hands_per_hour": self.hands_per_hour(),
            "average_pot_in_big_blinds": self.average_pot_in_big_blinds(),
            "showdown_frequency": self.showdown_frequency(),
            "category_distribution": self.category_distribution(),
            "player_feedback": {"thumbs_up": self.thumbs_up, "thumbs_down": self.thumbs_down},
        }


def simulate_standard_holdem_baseline(
    num_hands: int = 5000,
    rng: Optional[random.Random] = None,
) -> Dict[str, float]:
    """
    Empirical hand-category baseline for *standard* Hold'em (2 hole
    cards + 5 community, best-5-of-7), computed by dealing random hands
    through this same codebase's evaluator -- not a table of published
    constants. That keeps the comparison self-consistent (same
    evaluator, same category boundaries, same tie-handling as the
    Hold'em Plus numbers it's being compared against) and auditable
    (anyone can bump num_hands and re-run it rather than needing to
    trust an external citation) -- in keeping with this codebase's own
    stated preference for auditability over cleverness (see side_pots.py
    and hand_evaluator.py's module docstrings).

    Not wired into any hot path -- this is deliberately a slower,
    one-shot reference calculation, meant to be computed once (e.g.
    lazily on first request to a comparison endpoint, then cached) and
    not per-hand. 5,000 iterations is enough for the common categories
    (pair, two pair, high card) to settle to within a percentage point
    or two; bump it for a tighter estimate on the rare categories
    (quads, straight flush).
    """
    if num_hands < 1:
        raise ValueError("num_hands must be at least 1")
    rng = rng or random.Random()
    categories: List[HandCategory] = []
    deck_template = list(full_deck())
    for _ in range(num_hands):
        deck = list(deck_template)
        rng.shuffle(deck)
        seven = deck[:7]  # 2 "hole" + 5 "community", order doesn't matter to the evaluator
        categories.append(evaluate_best_of(seven).category)
    return _category_fractions(categories)
