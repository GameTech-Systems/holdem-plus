"""
Orchestration layer: wires poker_types, hand_evaluator, betting_state_machine,
side_pots, tournament_structure, and tournament_balancing behind two classes
so a UI or bot only has to talk to `Hand` and `Tournament`.

    Hand         -- runs ONE hand of Hold'em Plus end to end: posts blinds,
                    deals hole cards, walks every street via HandFlow,
                    performs the actual card dealing at each dealing step,
                    and resolves showdown (uncalled-bet refund -> side pots
                    -> award) into final stacks. The only thing a caller
                    does is construct it and call apply_action() for each
                    betting decision; everything else -- street sequencing,
                    burns, the front-loaded 3rd/4th/5th-street dealing,
                    auto-running the board when everyone's all-in -- happens
                    internally.

    Tournament   -- runs a whole event across however many tables: tracks
                    chip stacks across hands, looks up the current blind
                    level from the tournament clock, starts a Hand at a
                    given table using its current seating, and on
                    completion writes stacks back, eliminates anyone at 0,
                    and lets tournament_balancing handle re-seating/table
                    breaks -- all through eliminate_player(), which already
                    triggers rebalance() internally.

default_bot_action() is included as a minimal reference policy (check if
possible, else call, else all-in, else fold) -- useful for filling seats
with practice bots in the demo, and for driving multi-hand simulations/tests
without needing a real player at every seat.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import tournament_balancing as tb
import tournament_structure as ts
from betting_state_machine import (
    Action,
    ActionType,
    BETTING_STREETS,
    BettingRound,
    HandFlow,
    IllegalActionError,
    PlayerState,
    Street,
)
from hand_evaluator import evaluate_best_of
from poker_types import Card, HandRank, full_deck
from side_pots import Pot, SidePotError, award_pots, compute_side_pots, return_uncalled_bet


class OrchestratorError(Exception):
    pass


# ---------------------------------------------------------------------------
# Hand
# ---------------------------------------------------------------------------

@dataclass
class HandResult:
    payouts: Dict[str, int]
    refund: Optional[Tuple[str, int]]
    revealed_hands: Dict[str, List[Card]]
    community_cards: List[Card]
    pots: List[Pot]
    folded_players: List[str]
    final_stacks: Dict[str, int]


class Hand:
    """
    One full hand of Hold'em Plus. `seat_order` is the list of
    (player_id, starting_stack) in table-seating order, with the button
    seat at index `button_index`.

    `deck`, if given, is treated as a stack (deal draws from the end via
    .pop()) and used verbatim instead of a fresh shuffle -- primarily for
    deterministic testing/replay, but also a reasonable hook for a future
    "rigged practice deck" tutorial mode.
    """

    def __init__(
        self,
        seat_order: List[Tuple[str, int]],
        button_index: int,
        small_blind: int,
        big_blind: int,
        rng: Optional[random.Random] = None,
        deck: Optional[List[Card]] = None,
    ) -> None:
        if len(seat_order) < 2:
            raise OrchestratorError("A hand needs at least 2 players")
        if not (0 <= button_index < len(seat_order)):
            raise OrchestratorError("button_index out of range")

        self.rng = rng or random.Random()
        self.player_states: List[PlayerState] = [
            PlayerState(player_id=pid, stack=stack) for pid, stack in seat_order
        ]
        self.button_index = button_index
        self.small_blind = small_blind
        self.big_blind = big_blind

        if deck is not None:
            self.deck: List[Card] = list(deck)
        else:
            self.deck = list(full_deck())
            self.rng.shuffle(self.deck)

        self.burned_cards: List[Card] = []
        self.community_cards: List[Card] = []
        self._fourth_street_card: Optional[Card] = None
        self._fifth_street_card: Optional[Card] = None
        self._fold_street: Dict[str, Street] = {}
        self.rabbit_hunts: Dict[str, int] = {}
        self.result: Optional[HandResult] = None

        self.flow = HandFlow(
            players=self.player_states, button_index=button_index, big_blind=big_blind
        )

        self._deal_hole_cards(count=2)
        self._sb_idx, self._bb_idx = self._post_blinds()
        self._start_preflop_betting()
        self._progress()

    # -- public API ---------------------------------------------------

    @property
    def is_complete(self) -> bool:
        return self.result is not None

    @property
    def current_actor_id(self) -> Optional[str]:
        round_ = self.flow.current_round
        if round_ is None or self.flow.street not in BETTING_STREETS:
            return None
        return round_.current_actor_id

    def legal_actions(self, player_id: str) -> List[ActionType]:
        round_ = self.flow.current_round
        if round_ is None or self.flow.street not in BETTING_STREETS:
            return []
        try:
            return round_.legal_actions(player_id)
        except KeyError:
            return []

    def apply_action(self, player_id: str, action_type: ActionType, amount: int = 0) -> None:
        if self.is_complete:
            raise OrchestratorError("This hand is already complete")
        round_ = self.flow.current_round
        if round_ is None or self.flow.street not in BETTING_STREETS:
            raise OrchestratorError("No betting decision is currently open")
        street_at_action = self.flow.street
        round_.apply_action(Action(player_id, action_type, amount))
        if action_type == ActionType.FOLD:
            self._fold_street[player_id] = street_at_action
        self._progress()

    def final_stacks(self) -> Dict[str, int]:
        return {p.player_id: p.stack for p in self.player_states}

    def is_eligible_for_rabbit_hunt(self, player_id: str) -> bool:
        """
        Per the spec: a player who folds on the turn or river (i.e. after
        the 4th street card has already been revealed) may pay one small
        blind to see the river they'd have faced. Folding earlier
        (preflop or on the flop street) is not eligible -- there's more
        of the hand left undealt-in-spirit at that point, and the source
        spec ties this specifically to "folding after 4th street."
        """
        return self._fold_street.get(player_id) in (
            Street.TURN_BETTING,
            Street.RIVER_BETTING,
        )

    def rabbit_hunt(self, player_id: str) -> List[Card]:
        """
        Charges the small blind (capped at whatever's left in their
        stack) and reveals the river card that was already dealt
        face-down as part of the front-loaded dealing procedure -- it
        exists whether or not the hand ever reached a real river reveal.
        Demo-mode note: the charge is simply deducted here; the "goes to
        a dealer-tip pool" economics described in the spec are a
        live-casino-only concept (see Section 2a of the plan) and aren't
        modeled as real money anywhere in this fake-money demo.
        """
        if not self.is_complete:
            raise OrchestratorError("Rabbit hunt is only available after the hand is complete")
        if player_id in self.rabbit_hunts:
            raise OrchestratorError(f"{player_id} already used rabbit hunt on this hand")
        if not self.is_eligible_for_rabbit_hunt(player_id):
            raise OrchestratorError(
                f"{player_id} is not eligible for rabbit hunt "
                f"(must have folded on the turn or river)"
            )

        player = self._player(player_id)
        cost = min(self.small_blind, player.stack)
        player.stack -= cost
        self.rabbit_hunts[player_id] = cost

        assert self.result is not None
        self.result.final_stacks[player_id] = player.stack
        assert self._fifth_street_card is not None
        return [self._fifth_street_card]

    # -- internal: dealing ---------------------------------------------

    def _draw(self) -> Card:
        return self.deck.pop()

    def _burn(self) -> None:
        self.burned_cards.append(self.deck.pop())

    def _seat_order_from(self, start_idx: int) -> List[PlayerState]:
        n = len(self.player_states)
        return [self.player_states[(start_idx + i) % n] for i in range(n)]

    def _deal_hole_cards(self, count: int) -> None:
        order = self._seat_order_from(self.button_index + 1)
        for _ in range(count):
            for p in order:
                p.hole_cards.append(self._draw())

    def _post_blinds(self) -> Tuple[int, int]:
        n = len(self.player_states)
        if n == 2:
            # Heads-up convention: the button posts the small blind.
            sb_idx = self.button_index
            bb_idx = (self.button_index + 1) % n
        else:
            sb_idx = (self.button_index + 1) % n
            bb_idx = (self.button_index + 2) % n

        self._commit_forced_bet(self.player_states[sb_idx], self.small_blind)
        self._commit_forced_bet(self.player_states[bb_idx], self.big_blind)
        return sb_idx, bb_idx

    def _commit_forced_bet(self, player: PlayerState, amount: int) -> None:
        amt = min(amount, player.stack)
        player.stack -= amt
        player.committed_this_street += amt
        player.committed_total += amt
        if player.stack == 0:
            player.all_in = True

    def _start_preflop_betting(self) -> None:
        # Action starts left of the big blind -- NOT left of the button,
        # which is what HandFlow.start_betting_round() always does (that
        # helper is correct for every street except preflop; see its
        # docstring). We build the preflop BettingRound directly instead
        # of going through it, and attach it the same way advance() would.
        order = self.flow.active_ids_in_seat_order(self._bb_idx)
        current_bet = max(p.committed_this_street for p in self.player_states)
        round_ = BettingRound(
            street=Street.PREFLOP_BETTING,
            players=self.player_states,
            action_order=order,
            current_bet=current_bet,
            big_blind=self.big_blind,
        )
        self.flow.current_round = round_
        self.flow.street = Street.PREFLOP_BETTING

    def _handle_dealing_for(self, street: Street) -> None:
        if street == Street.DEAL_FLOP:
            self._burn()
            self.community_cards.extend(self._draw() for _ in range(3))
        elif street == Street.DEAL_THIRD_HOLE_CARD:
            self._burn()
            for p in self._seat_order_from(self.button_index + 1):
                if not p.folded:
                    p.hole_cards.append(self._draw())
        elif street == Street.DEAL_FOURTH_STREET_FACEDOWN:
            self._burn()
            self._fourth_street_card = self._draw()
        elif street == Street.DEAL_FIFTH_STREET_FACEDOWN:
            self._burn()
            self._fifth_street_card = self._draw()
        elif street == Street.REVEAL_FOURTH_STREET:
            assert self._fourth_street_card is not None
            self.community_cards.append(self._fourth_street_card)
        elif street == Street.REVEAL_FIFTH_STREET:
            assert self._fifth_street_card is not None
            self.community_cards.append(self._fifth_street_card)
        # FLOP_BETTING / TURN_BETTING / RIVER_BETTING: nothing to deal --
        # flow.advance() already started the round (correctly, "left of
        # button" is right for every street except preflop).
        # SHOWDOWN / HAND_COMPLETE: handled by _finalize(), not here.

    # -- internal: flow control -----------------------------------------

    def _progress(self) -> None:
        """Advance through the hand -- dealing/reveal steps automatically,
        pausing only at a betting street with an outstanding decision, or
        finalizing once the hand reaches HAND_COMPLETE."""
        while True:
            street = self.flow.street

            if street == Street.HAND_COMPLETE:
                if self.result is None:
                    self._finalize()
                return

            if street in BETTING_STREETS:
                round_ = self.flow.current_round
                if round_ is not None and not round_.is_complete():
                    return  # waiting on a player decision

            new_street = self.flow.advance()
            self._handle_dealing_for(new_street)

    def _finalize(self) -> None:
        active = [p for p in self.player_states if not p.folded]
        folded_ids = [p.player_id for p in self.player_states if p.folded]

        if len(active) == 1:
            winner = active[0]
            pot_total = sum(p.committed_total for p in self.player_states)
            winner.stack += pot_total
            self.result = HandResult(
                payouts={winner.player_id: pot_total},
                refund=None,
                revealed_hands={},
                community_cards=list(self.community_cards),
                pots=[],
                folded_players=folded_ids,
                final_stacks=self.final_stacks(),
            )
            return

        contributions = {p.player_id: p.committed_total for p in self.player_states}
        adjusted, refund = return_uncalled_bet(contributions)
        if refund is not None:
            refund_pid, refund_amt = refund
            self._player(refund_pid).stack += refund_amt

        folded_id_set = set(folded_ids)
        pots = compute_side_pots(adjusted, folded_player_ids=folded_id_set)

        hand_ranks: Dict[str, HandRank] = {}
        revealed: Dict[str, List[Card]] = {}
        for p in active:
            full_hand = list(p.hole_cards) + list(self.community_cards)
            hand_ranks[p.player_id] = evaluate_best_of(full_hand)
            revealed[p.player_id] = list(p.hole_cards)

        seat_order_ids = [p.player_id for p in self._seat_order_from(self.button_index + 1)]
        payouts = award_pots(pots, hand_ranks, seat_order=seat_order_ids)
        for pid, amount in payouts.items():
            self._player(pid).stack += amount

        self.result = HandResult(
            payouts=payouts,
            refund=refund,
            revealed_hands=revealed,
            community_cards=list(self.community_cards),
            pots=pots,
            folded_players=folded_ids,
            final_stacks=self.final_stacks(),
        )

    def _player(self, player_id: str) -> PlayerState:
        for p in self.player_states:
            if p.player_id == player_id:
                return p
        raise KeyError(player_id)


def default_bot_action(hand: Hand, player_id: str) -> Action:
    """Minimal reference policy: check if free, otherwise call, otherwise
    shove, otherwise fold. Not meant to play well -- meant to be a
    drop-in "someone is sitting here" filler for demo tables and for
    driving hands/tournaments in tests without a real player at every
    seat."""
    legal = hand.legal_actions(player_id)
    if ActionType.CHECK in legal:
        return Action(player_id, ActionType.CHECK)
    if ActionType.CALL in legal:
        return Action(player_id, ActionType.CALL)
    if ActionType.ALL_IN in legal:
        return Action(player_id, ActionType.ALL_IN)
    return Action(player_id, ActionType.FOLD)


def play_out_with_bots(hand: Hand) -> None:
    """Drives a Hand to completion using default_bot_action() for every
    seat. Convenience for demos/tests; a real table would call
    hand.apply_action() itself from actual player/bot input instead."""
    while not hand.is_complete:
        actor = hand.current_actor_id
        if actor is None:
            break
        action = default_bot_action(hand, actor)
        hand.apply_action(actor, action.action_type, action.amount)


# ---------------------------------------------------------------------------
# Tournament
# ---------------------------------------------------------------------------

@dataclass
class Tournament:
    state: tb.TournamentState
    stacks: Dict[str, int]
    blind_clock: ts.BlindClock
    rng: random.Random = field(default_factory=random.Random)
    elapsed_seconds: int = 0
    hands_by_table: Dict[str, Hand] = field(default_factory=dict)
    hand_history: List[HandResult] = field(default_factory=list)
    _button_seat_by_table: Dict[str, int] = field(default_factory=dict)

    # -- setup -----------------------------------------------------------

    @classmethod
    def create(
        cls,
        player_ids: List[str],
        starting_stack: int,
        max_table_size: int,
        blind_schedule: Optional[List[ts.BlindLevel]] = None,
        rng: Optional[random.Random] = None,
    ) -> "Tournament":
        rng = rng or random.Random()
        state = tb.create_tournament(player_ids, max_table_size, rng=rng)
        stacks = {pid: starting_stack for pid in player_ids}
        schedule = blind_schedule or ts.generate_default_schedule()
        clock = ts.BlindClock(schedule=schedule)
        return cls(state=state, stacks=stacks, blind_clock=clock, rng=rng)

    # -- clock / blinds ---------------------------------------------------

    def current_blind_level(self) -> ts.BlindLevel:
        return self.blind_clock.level_at(self.elapsed_seconds)

    def advance_clock(self, seconds: int) -> None:
        if seconds < 0:
            raise OrchestratorError("Cannot advance the clock backwards")
        self.elapsed_seconds += seconds

    # -- hand lifecycle ----------------------------------------------------

    def active_table_ids(self) -> List[str]:
        return [
            tid for tid, table in self.state.tables.items()
            if table.player_count() >= 2
        ]

    def start_hand(self, table_id: str, deck: Optional[List[Card]] = None) -> Hand:
        if table_id in self.hands_by_table:
            raise OrchestratorError(f"A hand is already in progress at table {table_id}")
        if table_id not in self.state.tables:
            raise OrchestratorError(f"No such table: {table_id}")

        table = self.state.tables[table_id]
        occupied = table.occupied_seats()
        if len(occupied) < 2:
            raise OrchestratorError(
                f"Table {table_id} has fewer than 2 players seated ({len(occupied)})"
            )

        seat_numbers = sorted(occupied.keys())
        prev_button_seat = self._button_seat_by_table.get(table_id)
        button_seat = _next_occupied_seat(seat_numbers, prev_button_seat)
        self._button_seat_by_table[table_id] = button_seat

        rotated_seats = _rotate_to_start_at(seat_numbers, button_seat)
        seat_order = [(occupied[s], self.stacks[occupied[s]]) for s in rotated_seats]

        level = self.current_blind_level()
        hand = Hand(
            seat_order=seat_order,
            button_index=0,  # list is pre-rotated so index 0 is always the button
            small_blind=level.small_blind,
            big_blind=level.big_blind,
            rng=self.rng,
            deck=deck,
        )
        self.hands_by_table[table_id] = hand
        return hand

    def complete_hand(self, table_id: str) -> HandResult:
        hand = self.hands_by_table.get(table_id)
        if hand is None:
            raise OrchestratorError(f"No hand in progress at table {table_id}")
        if not hand.is_complete:
            raise OrchestratorError(f"Hand at table {table_id} has not finished yet")

        result = hand.result
        assert result is not None
        for pid, stack in result.final_stacks.items():
            self.stacks[pid] = stack

        self.hand_history.append(result)
        del self.hands_by_table[table_id]

        busted = [pid for pid, stack in result.final_stacks.items() if stack == 0]
        # Stable order so simultaneous bust-outs still get deterministic,
        # reproducible finishing positions from a given rng/hand outcome.
        for pid in sorted(busted):
            if not self.state.players[pid].eliminated:
                tb.eliminate_player(self.state, pid, rng=self.rng)

        return result

    def is_complete(self) -> bool:
        return self.state.is_complete()

    def finalize(self) -> str:
        return tb.finalize_tournament(self.state)


def _next_occupied_seat(sorted_seat_numbers: List[int], prev_seat: Optional[int]) -> int:
    if not sorted_seat_numbers:
        raise OrchestratorError("No occupied seats to choose a button from")
    if prev_seat is None:
        return sorted_seat_numbers[0]
    for seat in sorted_seat_numbers:
        if seat > prev_seat:
            return seat
    return sorted_seat_numbers[0]  # wrap around


def _rotate_to_start_at(sorted_seat_numbers: List[int], start_seat: int) -> List[int]:
    idx = sorted_seat_numbers.index(start_seat)
    return sorted_seat_numbers[idx:] + sorted_seat_numbers[:idx]
