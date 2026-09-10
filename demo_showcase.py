"""
Scripted, deterministic "showcase" hands for the public demo landing page.

Why this exists (see HANDOFF.md for the session that traced this down):
the two features that actually make Hold'em Plus different from standard
Hold'em -- the 3rd hole card, and the Rabbit Runner option -- are both
easy for a first-time visitor to miss completely if they just click
around:

  - The 3rd hole card only visibly *matters* when it changes a hand's
    category at showdown, which isn't guaranteed to happen in any given
    hand -- most of the time it's a blank.
  - Rabbit Runner only ever appears after a player folds on the turn or
    river (see orchestrator.Hand.is_eligible_for_rabbit_hunt). The
    reference bot policy this project ships
    (orchestrator.default_bot_action) checks or calls whenever it can
    and only ever folds as an absolute last resort -- and since ALL_IN
    is a legal action any time a player still has chips, that last
    resort is essentially never reached while a bot has a stack. A demo
    table filled with those bots, or a human just clicking check/call,
    can run for a long time without a single turn/river fold, so this
    feature can look "not there" simply by never coming up. (It isn't a
    deploy problem -- the UI code for it has been live in
    static/index.html for a while; see HANDOFF.md.)

This module sidesteps both problems by scripting a couple of hands end
to end: a fixed deck (built the same way test_orchestrator.py's
_build_rigged_heads_up_deck() rigs one) plus a fixed sequence of
actions, so both features are guaranteed to show up, in a form worth
watching, every single time the demo runs. It plays the scripted hands
through the *real* Hand / HandFlow / BettingRound / side_pots /
hand_evaluator stack -- nothing here reimplements game logic -- so what
the demo shows is provably the same engine real tables run on, not a
mocked-up animation.

Every event below deliberately reveals every seat's hole cards, even
ones a real (non-demo) viewer would never see. That's a spectator/
teaching choice specific to this module, not a change to the real
game's hidden-information rules, which are untouched -- api.py's
_serialize_state still redacts normally for actual tables. Nothing in
here creates a Tournament, a TableSession, a guest, or touches
TABLES/GUESTS at all; it only ever builds throwaway orchestrator.Hand
objects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from betting_state_machine import ActionType
from orchestrator import Hand
from poker_types import Card, full_deck, parse_cards


@dataclass
class DemoEvent:
    """
    One step of a scripted hand. Deliberately self-contained: a frontend
    can render any single event on its own without remembering state
    from earlier ones, since every event carries the full current board
    and every seat's current public info (community_cards/players are
    always populated, even if unchanged from the previous event).
    """

    kind: str  # "deal" | "action" | "reveal" | "hand_result" | "rabbit_hunt"
    narration: str
    community_cards: List[str] = field(default_factory=list)
    players: List[dict] = field(default_factory=list)
    actor: Optional[str] = None
    action: Optional[str] = None
    amount: Optional[int] = None
    payouts: Optional[Dict[str, int]] = None
    revealed_card: Optional[str] = None  # rabbit-hunt reveals only
    highlight: bool = False  # True for "this is the Hold'em Plus part" beats


@dataclass
class DemoHand:
    title: str
    summary: str
    events: List[DemoEvent]


def _seat_order_ids(num_players: int, button_index: int) -> List[int]:
    """
    Matches orchestrator.Hand._seat_order_from(button_index + 1): hole
    cards (all three rounds of them) are always dealt starting left of
    the button, regardless of which seat acts first in the betting on
    any given street.
    """
    return [(button_index + 1 + i) % num_players for i in range(num_players)]


def _build_scripted_deck(
    num_players: int,
    button_index: int,
    hole_cards_by_seat: List[Tuple[Card, Card]],
    third_hole_card_by_seat: List[Card],
    community_cards: Tuple[Card, Card, Card, Card, Card],
) -> List[Card]:
    """
    Builds a full 52-card deck, as the stack-of-cards list Hand expects
    (drawn via .pop(), so the first card needed must be last in the
    list), that deals exactly the specified hole/community cards in
    exactly the order orchestrator.Hand actually draws them in. Mirrors
    test_orchestrator.py's _build_rigged_heads_up_deck(), generalized to
    any seat count.

    `hole_cards_by_seat` / `third_hole_card_by_seat` are indexed by
    absolute seat position (0..num_players-1), matching the seat_order
    list passed to Hand(). `community_cards` is
    (flop1, flop2, flop3, turn, river).
    """
    order = _seat_order_ids(num_players, button_index)

    scripted_cards = (
        [hole_cards_by_seat[s][0] for s in order]
        + [hole_cards_by_seat[s][1] for s in order]
        + list(community_cards)
        + [third_hole_card_by_seat[s] for s in order]
    )
    used = set(scripted_cards)
    pool = [c for c in full_deck() if c not in used]
    if len(pool) < 4:
        raise ValueError("Not enough unused cards left over to burn")
    burns, filler = pool[:4], pool[4:]

    draw_sequence = (
        [hole_cards_by_seat[s][0] for s in order]  # hole card round 1
        + [hole_cards_by_seat[s][1] for s in order]  # hole card round 2
        + [burns[0]] + list(community_cards[0:3])  # burn + flop
        + [burns[1]] + [third_hole_card_by_seat[s] for s in order]  # burn + 3rd hole cards
        + [burns[2]] + [community_cards[3]]  # burn + 4th street facedown
        + [burns[3]] + [community_cards[4]]  # burn + 5th street facedown
    )
    deck = filler + list(reversed(draw_sequence))
    assert len(deck) == 52, f"expected 52 cards, built {len(deck)}"
    assert len(set(deck)) == 52, "scripted deck has a duplicate card"
    return deck


def _snapshot(hand: Hand) -> List[dict]:
    """
    Public state for every seat -- INCLUDING hole cards, for every
    player, regardless of fold/all-in status. See module docstring: this
    is a demo-only, full-reveal snapshot, not how real tables serialize
    state (compare api.py's _serialize_state, which redacts normally).
    """
    return [
        {
            "player_id": p.player_id,
            "stack": p.stack,
            "folded": p.folded,
            "all_in": p.all_in,
            "hole_cards": [str(c) for c in p.hole_cards],
        }
        for p in hand.player_states
    ]


def _apply(
    hand: Hand,
    events: List[DemoEvent],
    player_id: str,
    action_type: ActionType,
    narration: str,
    amount: int = 0,
) -> None:
    hand.apply_action(player_id, action_type, amount)
    events.append(
        DemoEvent(
            kind="action",
            narration=narration,
            actor=player_id,
            action=action_type.name,
            amount=amount or None,
            community_cards=[str(c) for c in hand.community_cards],
            players=_snapshot(hand),
        )
    )


# ---------------------------------------------------------------------------
# Showcase hand 1: the 3rd hole card actually matters
# ---------------------------------------------------------------------------

def _build_extra_card_showcase() -> DemoHand:
    seat_order = [("Kai", 200), ("Ada", 200), ("Milo", 200)]  # seat 0 = button

    hole = {
        0: parse_cards("6h 6d"),  # Kai, button
        1: parse_cards("Ah Kd"),  # Ada, small blind
        2: parse_cards("3d 4d"),  # Milo, big blind
    }
    third = {
        0: parse_cards("Th")[0],
        1: parse_cards("2s")[0],
        2: parse_cards("Jc")[0],
    }
    community = parse_cards("9c 8d 7s 2h 2c")  # flop, flop, flop, turn, river

    deck = _build_scripted_deck(
        num_players=3,
        button_index=0,
        hole_cards_by_seat=[tuple(hole[i]) for i in range(3)],
        third_hole_card_by_seat=[third[i] for i in range(3)],
        community_cards=tuple(community),
    )

    hand = Hand(seat_order=seat_order, button_index=0, small_blind=1, big_blind=2, deck=deck)
    events: List[DemoEvent] = [
        DemoEvent(
            kind="deal",
            narration="Kai, Ada, and Milo each get 2 hole cards -- same as standard Hold'em so far.",
            community_cards=[],
            players=_snapshot(hand),
        )
    ]

    _apply(hand, events, "Kai", ActionType.CALL, "Kai (button) calls.")
    _apply(hand, events, "Ada", ActionType.CALL, "Ada (small blind) calls.")
    _apply(hand, events, "Milo", ActionType.CHECK, "Milo (big blind) checks -- on to the flop.")

    events.append(
        DemoEvent(
            kind="reveal",
            narration=(
                "Flop: 9\u2663 8\u2666 7\u2660 -- and here's the Hold'em Plus part: everyone "
                "still in gets a 3rd hole card, face down, before betting continues."
            ),
            community_cards=[str(c) for c in hand.community_cards],
            players=_snapshot(hand),
            highlight=True,
        )
    )
    _apply(hand, events, "Ada", ActionType.CHECK, "Ada checks.")
    _apply(hand, events, "Milo", ActionType.CHECK, "Milo checks.")
    _apply(hand, events, "Kai", ActionType.CHECK, "Kai checks.")

    events.append(
        DemoEvent(
            kind="reveal",
            narration="Turn: 2\u2665 (dealt face down back at the flop, only now turned up).",
            community_cards=[str(c) for c in hand.community_cards],
            players=_snapshot(hand),
        )
    )
    _apply(hand, events, "Ada", ActionType.CHECK, "Ada checks.")
    _apply(hand, events, "Milo", ActionType.CHECK, "Milo checks.")
    _apply(hand, events, "Kai", ActionType.CHECK, "Kai checks.")

    events.append(
        DemoEvent(
            kind="reveal",
            narration="River: 2\u2663.",
            community_cards=[str(c) for c in hand.community_cards],
            players=_snapshot(hand),
        )
    )
    _apply(hand, events, "Ada", ActionType.CHECK, "Ada checks.")
    _apply(hand, events, "Milo", ActionType.CHECK, "Milo checks.")
    _apply(hand, events, "Kai", ActionType.CHECK, "Kai checks -- showdown.")

    assert hand.is_complete
    events.append(
        DemoEvent(
            kind="hand_result",
            narration=(
                "Showdown! Kai's 3rd hole card (T\u2665) completes a T-9-8-7-6 straight -- a "
                "hand that isn't reachable from this deal with only 2 hole cards. Ada's 3rd "
                "card (2\u2660) gave her trip deuces off the board pair, still not enough to catch it."
            ),
            community_cards=[str(c) for c in hand.community_cards],
            players=_snapshot(hand),
            payouts=dict(hand.result.payouts),
            highlight=True,
        )
    )

    return DemoHand(
        title="The Extra Card",
        summary="Watch a 3rd hole card make a hand that plain Hold'em couldn't.",
        events=events,
    )


# ---------------------------------------------------------------------------
# Showcase hand 2: Rabbit Runner
# ---------------------------------------------------------------------------

def _build_rabbit_hunt_showcase() -> DemoHand:
    seat_order = [("Rio", 200), ("Sam", 200)]  # seat 0 = button/small blind (heads-up)

    hole = {0: parse_cards("8d 7s"), 1: parse_cards("Kh Jd")}
    third = {0: parse_cards("6c")[0], 1: parse_cards("4d")[0]}
    community = parse_cards("9s 3c 2c Td Qh")  # flop, flop, flop, turn, river

    deck = _build_scripted_deck(
        num_players=2,
        button_index=0,
        hole_cards_by_seat=[tuple(hole[i]) for i in range(2)],
        third_hole_card_by_seat=[third[i] for i in range(2)],
        community_cards=tuple(community),
    )

    hand = Hand(seat_order=seat_order, button_index=0, small_blind=1, big_blind=2, deck=deck)
    events: List[DemoEvent] = [
        DemoEvent(
            kind="deal",
            narration="Heads-up this time: Rio (button/small blind) and Sam (big blind).",
            community_cards=[],
            players=_snapshot(hand),
        )
    ]

    _apply(hand, events, "Rio", ActionType.CALL, "Rio calls.")
    _apply(hand, events, "Sam", ActionType.CHECK, "Sam checks -- on to the flop.")

    events.append(
        DemoEvent(
            kind="reveal",
            narration="Flop: 9\u2660 3\u2663 2\u2663 -- 3rd hole cards go out.",
            community_cards=[str(c) for c in hand.community_cards],
            players=_snapshot(hand),
            highlight=True,
        )
    )
    _apply(hand, events, "Sam", ActionType.CHECK, "Sam checks.")
    _apply(hand, events, "Rio", ActionType.CHECK, "Rio checks.")

    events.append(
        DemoEvent(
            kind="reveal",
            narration="Turn: T\u2666.",
            community_cards=[str(c) for c in hand.community_cards],
            players=_snapshot(hand),
        )
    )
    _apply(hand, events, "Sam", ActionType.CHECK, "Sam checks.")
    _apply(
        hand, events, "Rio", ActionType.BET,
        "Rio bets 6 -- that ten on the turn just gave him a straight.", amount=6,
    )
    _apply(hand, events, "Sam", ActionType.FOLD, "Sam's only got a gutshot draw and folds to the bet.")

    assert hand.is_complete
    assert hand.is_eligible_for_rabbit_hunt("Sam")
    events.append(
        DemoEvent(
            kind="hand_result",
            narration="Rio takes the pot uncontested.",
            community_cards=[str(c) for c in hand.community_cards],
            players=_snapshot(hand),
            payouts=dict(hand.result.payouts),
        )
    )

    river = hand.rabbit_hunt("Sam")
    events.append(
        DemoEvent(
            kind="rabbit_hunt",
            narration=(
                f"Rabbit Runner: for the cost of a small blind, Sam pays to see the river "
                f"that would have come: {river[0]} -- exactly the queen his gutshot needed. "
                f"His king-jack would have turned into a king-high straight, good enough to "
                f"beat Rio's ten-high one."
            ),
            community_cards=[str(c) for c in hand.community_cards],
            players=_snapshot(hand),
            revealed_card=str(river[0]),
            highlight=True,
        )
    )

    return DemoHand(
        title="Rabbit Runner",
        summary=(
            "If folding ends the hand before the river's revealed, you can still pay "
            "to see what it would have been."
        ),
        events=events,
    )


def build_demo_script() -> List[DemoHand]:
    return [_build_extra_card_showcase(), _build_rabbit_hunt_showcase()]


def serialize_demo_script(hands: List[DemoHand]) -> List[dict]:
    return [
        {
            "title": h.title,
            "summary": h.summary,
            "events": [
                {
                    "kind": e.kind,
                    "narration": e.narration,
                    "community_cards": e.community_cards,
                    "players": e.players,
                    "actor": e.actor,
                    "action": e.action,
                    "amount": e.amount,
                    "payouts": e.payouts,
                    "revealed_card": e.revealed_card,
                    "highlight": e.highlight,
                }
                for e in h.events
            ],
        }
        for h in hands
    ]
