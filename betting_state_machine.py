"""
Hold'em Plus hand-flow state machine.

Encodes the exact dealing/betting sequence from the game spec:

  1. Deal 2 hole cards to each player.
  2. Pre-flop betting round.
  3. Burn, deal flop (3 community cards).
  4. Burn, deal 3rd hole card to each active player.
  5. Burn, deal 4th street face DOWN (not yet revealed).
  6. Burn, deal 5th street face DOWN (not yet revealed).
     -> deck is now fully set; dealer's remaining job is running betting
        and turning already-dealt cards face up at the right moments.
  7. Betting round (flop + 3rd hole card known).
  8. Reveal 4th street (turn it face up -- no new card dealt here).
  9. Betting round (turn).
 10. Reveal 5th street (turn it face up -- no new card dealt here).
 11. Betting round (river).
 12. Showdown.

This module models the *flow* and *betting legality* -- whose turn it is,
what actions are legal, when a betting round is complete, when a hand ends
early because everyone but one player folded. It intentionally does NOT
implement side-pot math for multi-way all-ins; that's flagged as a TODO
since it's an orthogonal, separately-testable piece of pot logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional

from poker_types import Card


class Street(Enum):
    DEAL_HOLE_CARDS = auto()
    PREFLOP_BETTING = auto()
    DEAL_FLOP = auto()
    DEAL_THIRD_HOLE_CARD = auto()
    DEAL_FOURTH_STREET_FACEDOWN = auto()
    DEAL_FIFTH_STREET_FACEDOWN = auto()
    FLOP_BETTING = auto()          # betting with 3 hole + 3 community known
    REVEAL_FOURTH_STREET = auto()
    TURN_BETTING = auto()
    REVEAL_FIFTH_STREET = auto()
    RIVER_BETTING = auto()
    SHOWDOWN = auto()
    HAND_COMPLETE = auto()         # terminal: showdown finished, or won by folds


# The fixed order the hand progresses through. Betting-round completion
# (see BettingRound.is_complete) is what triggers each advance; dealing
# steps advance automatically since they have no player decision in them.
STREET_ORDER: List[Street] = [
    Street.DEAL_HOLE_CARDS,
    Street.PREFLOP_BETTING,
    Street.DEAL_FLOP,
    Street.DEAL_THIRD_HOLE_CARD,
    Street.DEAL_FOURTH_STREET_FACEDOWN,
    Street.DEAL_FIFTH_STREET_FACEDOWN,
    Street.FLOP_BETTING,
    Street.REVEAL_FOURTH_STREET,
    Street.TURN_BETTING,
    Street.REVEAL_FIFTH_STREET,
    Street.RIVER_BETTING,
    Street.SHOWDOWN,
    Street.HAND_COMPLETE,
]

BETTING_STREETS = {
    Street.PREFLOP_BETTING,
    Street.FLOP_BETTING,
    Street.TURN_BETTING,
    Street.RIVER_BETTING,
}


class ActionType(Enum):
    FOLD = auto()
    CHECK = auto()
    CALL = auto()
    BET = auto()
    RAISE = auto()
    ALL_IN = auto()


@dataclass
class Action:
    player_id: str
    action_type: ActionType
    amount: int = 0  # total chips put in with this action, 0 for fold/check


@dataclass
class PlayerState:
    player_id: str
    stack: int
    hole_cards: List[Card] = field(default_factory=list)
    folded: bool = False
    all_in: bool = False
    committed_this_street: int = 0   # chips put in during the CURRENT betting street
    committed_total: int = 0         # chips put in during the whole hand
    has_acted_this_street: bool = False


class IllegalActionError(Exception):
    pass


@dataclass
class BettingRound:
    """
    Manages a single betting street: whose turn it is, what's legal,
    and whether the street is complete.

    A street is complete when every player who is still in the hand and
    not all-in has acted at least once AND has either matched the current
    bet or folded. (Standard "action closes when it gets back around with
    no outstanding raise" rule.)
    """

    street: Street
    players: List[PlayerState]
    action_order: List[str]          # player_ids in the order they act this street
    current_bet: int = 0
    min_raise: int = 0
    actor_index: int = 0
    big_blind: int = 0

    def __post_init__(self) -> None:
        if self.min_raise == 0:
            self.min_raise = self.big_blind

    def _player(self, player_id: str) -> PlayerState:
        for p in self.players:
            if p.player_id == player_id:
                return p
        raise KeyError(f"Unknown player_id: {player_id}")

    def active_players(self) -> List[PlayerState]:
        return [p for p in self.players if not p.folded]

    def players_who_can_still_act(self) -> List[PlayerState]:
        return [p for p in self.active_players() if not p.all_in]

    @property
    def current_actor_id(self) -> Optional[str]:
        eligible = [pid for pid in self.action_order
                    if not self._player(pid).folded and not self._player(pid).all_in]
        if not eligible:
            return None
        # find next eligible actor starting at actor_index
        n = len(self.action_order)
        for offset in range(n):
            idx = (self.actor_index + offset) % n
            pid = self.action_order[idx]
            if pid in eligible:
                return pid
        return None

    def legal_actions(self, player_id: str) -> List[ActionType]:
        player = self._player(player_id)
        if player.folded or player.all_in:
            return []

        to_call = self.current_bet - player.committed_this_street
        actions = [ActionType.FOLD]
        if to_call == 0:
            actions.append(ActionType.CHECK)
            actions.append(ActionType.BET)
        else:
            actions.append(ActionType.CALL)
            if player.stack > to_call:
                actions.append(ActionType.RAISE)
        if player.stack > 0:
            actions.append(ActionType.ALL_IN)
        return actions

    def apply_action(self, action: Action) -> None:
        player = self._player(action.player_id)
        legal = self.legal_actions(action.player_id)
        if action.action_type not in legal:
            raise IllegalActionError(
                f"{action.action_type} is not legal for {action.player_id} "
                f"(legal: {legal})"
            )

        if action.player_id != self.current_actor_id:
            raise IllegalActionError(
                f"It is not {action.player_id}'s turn "
                f"(current actor: {self.current_actor_id})"
            )

        to_call = self.current_bet - player.committed_this_street

        if action.action_type == ActionType.FOLD:
            player.folded = True

        elif action.action_type == ActionType.CHECK:
            pass  # no chips move

        elif action.action_type == ActionType.CALL:
            amount = min(to_call, player.stack)
            self._commit(player, amount)

        elif action.action_type == ActionType.BET:
            if action.amount <= 0:
                raise IllegalActionError("Bet amount must be positive")
            self._commit(player, action.amount)
            self.current_bet = player.committed_this_street
            self.min_raise = max(self.min_raise, action.amount)
            self._reset_others_acted_flag(except_player=player.player_id)

        elif action.action_type == ActionType.RAISE:
            raise_to = action.amount
            increment = raise_to - self.current_bet
            if increment < self.min_raise:
                raise IllegalActionError(
                    f"Raise increment {increment} is below minimum raise {self.min_raise}"
                )
            self._commit(player, raise_to - player.committed_this_street)
            self.min_raise = increment
            self.current_bet = player.committed_this_street
            self._reset_others_acted_flag(except_player=player.player_id)

        elif action.action_type == ActionType.ALL_IN:
            all_in_amount = player.stack
            self._commit(player, all_in_amount)
            player.all_in = True
            if player.committed_this_street > self.current_bet:
                increment = player.committed_this_street - self.current_bet
                if increment >= self.min_raise:
                    self.min_raise = increment
                self.current_bet = player.committed_this_street
                self._reset_others_acted_flag(except_player=player.player_id)
            # Note: an all-in for less than a full call/raise creates a
            # side-pot situation. Side-pot chip accounting is intentionally
            # out of scope here (see module docstring TODO) but the
            # committed_this_street bookkeeping below is what a side-pot
            # calculator would consume as input.

        player.has_acted_this_street = True
        self._advance_actor()

    def _commit(self, player: PlayerState, amount: int) -> None:
        amount = min(amount, player.stack)
        player.stack -= amount
        player.committed_this_street += amount
        player.committed_total += amount
        if player.stack == 0:
            player.all_in = True

    def _reset_others_acted_flag(self, except_player: str) -> None:
        for p in self.active_players():
            if p.player_id != except_player and not p.all_in:
                p.has_acted_this_street = False

    def _advance_actor(self) -> None:
        n = len(self.action_order)
        self.actor_index = (self.actor_index + 1) % n

    def is_complete(self) -> bool:
        contenders = self.players_who_can_still_act()
        if len(self.active_players()) <= 1:
            return True  # everyone else folded -- hand is over, not just the street
        if not contenders:
            return True  # everyone left is all-in -- no more betting possible
        for p in contenders:
            if not p.has_acted_this_street:
                return False
            if p.committed_this_street != self.current_bet:
                return False
        return True


@dataclass
class HandFlow:
    """
    Orchestrates a full hand through STREET_ORDER, delegating in-round
    betting logic to BettingRound and exposing dealing "hooks" the caller
    (the actual dealing/UI layer) fills in at each dealing step.
    """

    players: List[PlayerState]
    button_index: int
    big_blind: int
    street: Street = Street.DEAL_HOLE_CARDS
    current_round: Optional[BettingRound] = None

    def active_ids_in_seat_order(self, start_after: int) -> List[str]:
        n = len(self.players)
        order = []
        for offset in range(1, n + 1):
            idx = (start_after + offset) % n
            p = self.players[idx]
            if not p.folded:
                order.append(p.player_id)
        return order

    def start_betting_round(self, street: Street) -> BettingRound:
        assert street in BETTING_STREETS
        # Pre-flop action starts left of the big blind; post-flop starts
        # left of the button. This simplified helper always starts left
        # of the button for post-deal-hole-cards streets and assumes the
        # caller has already posted blinds for PREFLOP_BETTING and set
        # committed_this_street accordingly before calling this.
        order = self.active_ids_in_seat_order(self.button_index)
        current_bet = max((p.committed_this_street for p in self.players), default=0) \
            if street == Street.PREFLOP_BETTING else 0
        self.current_round = BettingRound(
            street=street,
            players=self.players,
            action_order=order,
            current_bet=current_bet,
            big_blind=self.big_blind,
        )
        self.street = street
        return self.current_round

    def advance(self) -> Street:
        """
        Move to the next Street in STREET_ORDER. Callers should invoke this
        after (a) a dealing step's dealing logic has run, or (b) the current
        BettingRound reports is_complete(). Returns the new Street.
        """
        if self.street in BETTING_STREETS:
            if self.current_round is None or not self.current_round.is_complete():
                raise IllegalActionError(
                    f"Cannot advance out of {self.street}: betting round not complete"
                )
            if len(self.current_round.active_players()) <= 1:
                self.street = Street.HAND_COMPLETE
                return self.street
            # reset per-street commitments for the next betting round
            for p in self.players:
                p.committed_this_street = 0
                p.has_acted_this_street = False

        idx = STREET_ORDER.index(self.street)
        self.street = STREET_ORDER[idx + 1]

        if self.street in BETTING_STREETS:
            self.start_betting_round(self.street)

        return self.street

    def is_hand_over(self) -> bool:
        return self.street == Street.HAND_COMPLETE
