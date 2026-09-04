"""
Tests for the Hold'em Plus dealing/betting-round state machine.

Run with: pytest -v test_betting_state_machine.py
"""

import pytest

from betting_state_machine import (
    Action,
    ActionType,
    BettingRound,
    HandFlow,
    IllegalActionError,
    PlayerState,
    Street,
    STREET_ORDER,
)


def make_players(n=3, stack=1000):
    return [PlayerState(player_id=f"p{i}", stack=stack) for i in range(n)]


# ---------------------------------------------------------------------------
# BettingRound: legality and turn order
# ---------------------------------------------------------------------------

def test_out_of_turn_action_is_rejected():
    players = make_players(3)
    round_ = BettingRound(
        street=Street.FLOP_BETTING,
        players=players,
        action_order=["p0", "p1", "p2"],
        big_blind=10,
    )
    with pytest.raises(IllegalActionError):
        round_.apply_action(Action("p1", ActionType.CHECK))  # p0 acts first


def test_check_then_check_then_check_closes_the_street():
    players = make_players(3)
    round_ = BettingRound(
        street=Street.FLOP_BETTING,
        players=players,
        action_order=["p0", "p1", "p2"],
        big_blind=10,
    )
    assert not round_.is_complete()
    round_.apply_action(Action("p0", ActionType.CHECK))
    round_.apply_action(Action("p1", ActionType.CHECK))
    assert not round_.is_complete()
    round_.apply_action(Action("p2", ActionType.CHECK))
    assert round_.is_complete()


def test_bet_reopens_action_for_players_who_already_acted():
    players = make_players(3)
    round_ = BettingRound(
        street=Street.FLOP_BETTING,
        players=players,
        action_order=["p0", "p1", "p2"],
        big_blind=10,
    )
    round_.apply_action(Action("p0", ActionType.CHECK))
    round_.apply_action(Action("p1", ActionType.BET, amount=20))
    # p0 already acted this street, but p1's bet must reopen action for p0
    assert not round_.is_complete()
    round_.apply_action(Action("p2", ActionType.CALL))
    assert not round_.is_complete()  # p0 still owes a call/fold/raise decision
    round_.apply_action(Action("p0", ActionType.CALL))
    assert round_.is_complete()


def test_raise_below_minimum_is_illegal():
    players = make_players(2, stack=1000)
    round_ = BettingRound(
        street=Street.FLOP_BETTING,
        players=players,
        action_order=["p0", "p1"],
        big_blind=10,
    )
    round_.apply_action(Action("p0", ActionType.BET, amount=20))
    with pytest.raises(IllegalActionError):
        # min raise increment is 20 (matches the bet); raising to 30 is only
        # a 10-chip increment, below the minimum
        round_.apply_action(Action("p1", ActionType.RAISE, amount=30))


def test_valid_raise_reopens_action():
    players = make_players(2, stack=1000)
    round_ = BettingRound(
        street=Street.FLOP_BETTING,
        players=players,
        action_order=["p0", "p1"],
        big_blind=10,
    )
    round_.apply_action(Action("p0", ActionType.BET, amount=20))
    round_.apply_action(Action("p1", ActionType.RAISE, amount=50))  # +30 raise, legal
    assert not round_.is_complete()
    round_.apply_action(Action("p0", ActionType.CALL))
    assert round_.is_complete()
    assert players[0].committed_this_street == 50
    assert players[1].committed_this_street == 50


def test_fold_down_to_one_player_completes_round_immediately():
    players = make_players(3)
    round_ = BettingRound(
        street=Street.FLOP_BETTING,
        players=players,
        action_order=["p0", "p1", "p2"],
        big_blind=10,
    )
    round_.apply_action(Action("p0", ActionType.BET, amount=20))
    round_.apply_action(Action("p1", ActionType.FOLD))
    round_.apply_action(Action("p2", ActionType.FOLD))
    assert round_.is_complete()
    assert round_.active_players() == [players[0]]


def test_all_in_for_less_still_lets_others_close_action():
    players = make_players(3, stack=1000)
    players[2].stack = 15  # short stack
    round_ = BettingRound(
        street=Street.FLOP_BETTING,
        players=players,
        action_order=["p0", "p1", "p2"],
        big_blind=10,
    )
    round_.apply_action(Action("p0", ActionType.BET, amount=50))
    round_.apply_action(Action("p1", ActionType.CALL))
    round_.apply_action(Action("p2", ActionType.ALL_IN))  # only 15, short of the 50 call
    assert players[2].all_in
    assert round_.is_complete()  # no one left who can still act owes more


def test_illegal_action_type_for_player_is_rejected():
    players = make_players(2)
    round_ = BettingRound(
        street=Street.FLOP_BETTING,
        players=players,
        action_order=["p0", "p1"],
        big_blind=10,
    )
    with pytest.raises(IllegalActionError):
        # can't call when nothing has been bet yet (current_bet == 0)
        round_.apply_action(Action("p0", ActionType.CALL))


# ---------------------------------------------------------------------------
# HandFlow: full street sequencing, matching the Hold'em Plus spec exactly
# ---------------------------------------------------------------------------

def test_street_order_matches_spec():
    """
    Locks in the exact sequence from the rules doc: hole cards, preflop
    betting, flop, 3rd hole card, 4th street face-down, 5th street
    face-down, flop betting, reveal 4th, turn betting, reveal 5th,
    river betting, showdown.
    """
    assert STREET_ORDER == [
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


def test_deck_is_fully_set_before_any_flop_betting_occurs():
    """
    The whole point of the front-loaded dealing procedure: by the time
    FLOP_BETTING starts, both face-down streets have already been dealt
    (as far as the state machine's flow is concerned -- this test checks
    the *ordering guarantee*, not literal card dealing, since card dealing
    itself is the caller's responsibility at each dealing hook).
    """
    order = STREET_ORDER
    flop_betting_idx = order.index(Street.FLOP_BETTING)
    fourth_facedown_idx = order.index(Street.DEAL_FOURTH_STREET_FACEDOWN)
    fifth_facedown_idx = order.index(Street.DEAL_FIFTH_STREET_FACEDOWN)
    assert fourth_facedown_idx < flop_betting_idx
    assert fifth_facedown_idx < flop_betting_idx


def test_cannot_advance_out_of_betting_street_while_incomplete():
    players = make_players(2)
    flow = HandFlow(players=players, button_index=0, big_blind=10)
    flow.street = Street.PREFLOP_BETTING
    flow.start_betting_round(Street.PREFLOP_BETTING)
    with pytest.raises(IllegalActionError):
        flow.advance()


def test_full_hand_runs_to_showdown_with_only_checks():
    """
    End-to-end simulation: 3 players, no chips ever bet, every betting
    street resolved by unanimous check, hand proceeds all the way to
    SHOWDOWN without the state machine getting stuck or skipping a step.
    """
    players = make_players(3, stack=1000)
    flow = HandFlow(players=players, button_index=0, big_blind=10)

    # DEAL_HOLE_CARDS -- dealing hook, no betting decision
    assert flow.street == Street.DEAL_HOLE_CARDS
    flow.street = STREET_ORDER[STREET_ORDER.index(Street.DEAL_HOLE_CARDS) + 1]
    flow.start_betting_round(Street.PREFLOP_BETTING)

    def check_around(round_: BettingRound):
        while not round_.is_complete():
            actor = round_.current_actor_id
            round_.apply_action(Action(actor, ActionType.CHECK))

    check_around(flow.current_round)
    assert flow.street == Street.PREFLOP_BETTING
    flow.advance()
    assert flow.street == Street.DEAL_FLOP

    for expected in [
        Street.DEAL_THIRD_HOLE_CARD,
        Street.DEAL_FOURTH_STREET_FACEDOWN,
        Street.DEAL_FIFTH_STREET_FACEDOWN,
    ]:
        flow.advance()
        assert flow.street == expected

    flow.advance()
    assert flow.street == Street.FLOP_BETTING
    check_around(flow.current_round)
    flow.advance()
    assert flow.street == Street.REVEAL_FOURTH_STREET

    flow.advance()
    assert flow.street == Street.TURN_BETTING
    check_around(flow.current_round)
    flow.advance()
    assert flow.street == Street.REVEAL_FIFTH_STREET

    flow.advance()
    assert flow.street == Street.RIVER_BETTING
    check_around(flow.current_round)
    flow.advance()
    assert flow.street == Street.SHOWDOWN

    flow.advance()
    assert flow.street == Street.HAND_COMPLETE
    assert flow.is_hand_over()


def test_hand_ends_early_when_folds_leave_one_player():
    """
    If a bet folds everyone else out on, say, the flop betting street, the
    hand should jump straight to HAND_COMPLETE rather than continuing
    through reveal/turn/river/showdown.
    """
    players = make_players(3, stack=1000)
    flow = HandFlow(players=players, button_index=0, big_blind=10)
    flow.street = Street.PREFLOP_BETTING
    flow.start_betting_round(Street.PREFLOP_BETTING)

    round_ = flow.current_round
    actor = round_.current_actor_id
    round_.apply_action(Action(actor, ActionType.BET, amount=20))
    for _ in range(2):
        actor = round_.current_actor_id
        round_.apply_action(Action(actor, ActionType.FOLD))

    assert round_.is_complete()
    flow.advance()
    assert flow.street == Street.HAND_COMPLETE
    assert flow.is_hand_over()
    assert len(round_.active_players()) == 1
