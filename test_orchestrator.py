"""
Tests for orchestrator.py (Hand + Tournament).

Run with: pytest -v test_orchestrator.py
"""

import random

import pytest

from betting_state_machine import ActionType, IllegalActionError, Street
from orchestrator import (
    Hand,
    OrchestratorError,
    Tournament,
    default_bot_action,
    play_out_with_bots,
)
from poker_types import Card, full_deck, parse_cards
from tournament_structure import BlindLevel, generate_default_schedule


# ---------------------------------------------------------------------------
# Hand: basic wiring
# ---------------------------------------------------------------------------

def test_hand_deals_two_hole_cards_and_posts_blinds():
    hand = Hand(
        seat_order=[("p0", 1000), ("p1", 1000), ("p2", 1000)],
        button_index=0,
        small_blind=1,
        big_blind=2,
        rng=random.Random(1),
    )
    for p in hand.player_states:
        assert len(p.hole_cards) == 2

    # 3-handed: sb=index1, bb=index2 (button posts nothing pre-blind)
    assert hand.player_states[1].committed_this_street == 1
    assert hand.player_states[2].committed_this_street == 2
    assert hand.player_states[1].stack == 999
    assert hand.player_states[2].stack == 998


def test_three_handed_button_acts_first_preflop():
    """With exactly 3 seats, the button is the only non-blind seat, so it
    acts first preflop (left of the big blind wraps to the button)."""
    hand = Hand(
        seat_order=[("p0", 1000), ("p1", 1000), ("p2", 1000)],
        button_index=0,
        small_blind=1,
        big_blind=2,
        rng=random.Random(1),
    )
    assert hand.current_actor_id == "p0"


def test_heads_up_button_posts_small_blind_and_acts_first():
    hand = Hand(
        seat_order=[("p0", 1000), ("p1", 1000)],
        button_index=0,
        small_blind=1,
        big_blind=2,
        rng=random.Random(1),
    )
    assert hand.player_states[0].committed_this_street == 1  # button = SB
    assert hand.player_states[1].committed_this_street == 2  # BB
    assert hand.current_actor_id == "p0"  # heads-up: button acts first preflop


def test_legal_actions_empty_when_no_betting_decision_open():
    hand = Hand(
        seat_order=[("p0", 1000), ("p1", 1000)],
        button_index=0,
        small_blind=1,
        big_blind=2,
        rng=random.Random(1),
    )
    assert hand.legal_actions("nonexistent_player") == []


def test_apply_action_after_hand_complete_raises():
    hand = Hand(
        seat_order=[("p0", 1000), ("p1", 1000)],
        button_index=0,
        small_blind=1,
        big_blind=2,
        rng=random.Random(1),
    )
    play_out_with_bots(hand)
    assert hand.is_complete
    with pytest.raises(OrchestratorError):
        hand.apply_action("p0", ActionType.CHECK)


def test_third_hole_card_dealt_after_preflop_betting():
    hand = Hand(
        seat_order=[("p0", 1000), ("p1", 1000)],
        button_index=0,
        small_blind=1,
        big_blind=2,
        rng=random.Random(1),
    )
    hand.apply_action("p0", ActionType.CALL)
    hand.apply_action("p1", ActionType.CHECK)  # closes preflop
    # now mid flop-betting street, 3rd hole cards should already be dealt
    for p in hand.player_states:
        assert len(p.hole_cards) == 3
    assert len(hand.community_cards) == 3


# ---------------------------------------------------------------------------
# Hand: full play-through, chip conservation, deck integrity
# ---------------------------------------------------------------------------

def test_checked_down_hand_conserves_total_chips():
    starting = {"p0": 1000, "p1": 1000, "p2": 1000}
    hand = Hand(
        seat_order=list(starting.items()),
        button_index=0,
        small_blind=1,
        big_blind=2,
        rng=random.Random(7),
    )
    play_out_with_bots(hand)
    assert hand.is_complete
    assert sum(hand.final_stacks().values()) == sum(starting.values())
    assert len(hand.community_cards) == 5


def test_fold_out_ends_hand_immediately_and_awards_full_pot():
    hand = Hand(
        seat_order=[("p0", 1000), ("p1", 1000), ("p2", 1000)],
        button_index=0,
        small_blind=1,
        big_blind=2,
        rng=random.Random(3),
    )
    # p0 acts first (3-handed). Everyone folds to the big blind.
    hand.apply_action("p0", ActionType.FOLD)
    hand.apply_action("p1", ActionType.FOLD)
    assert hand.is_complete
    assert sum(hand.result.payouts.values()) == 3  # sb(1) + bb(2), nothing else wagered
    assert hand.result.payouts.get("p2") == 3
    assert hand.community_cards == []  # never got past preflop


# ---------------------------------------------------------------------------
# Hand: Rabbit Runner
# ---------------------------------------------------------------------------

def test_rabbit_hunt_not_eligible_after_preflop_fold():
    hand = Hand(
        seat_order=[("p0", 1000), ("p1", 1000), ("p2", 1000)],
        button_index=0,
        small_blind=1,
        big_blind=2,
        rng=random.Random(3),
    )
    hand.apply_action("p0", ActionType.FOLD)
    hand.apply_action("p1", ActionType.FOLD)
    assert hand.is_complete
    assert not hand.is_eligible_for_rabbit_hunt("p0")
    with pytest.raises(OrchestratorError):
        hand.rabbit_hunt("p0")


def test_rabbit_hunt_eligible_after_turn_fold_and_reveals_river():
    hand = Hand(
        seat_order=[("p0", 1000), ("p1", 1000)],
        button_index=0,
        small_blind=1,
        big_blind=2,
        rng=random.Random(5),
    )
    # get to the turn betting street
    hand.apply_action("p0", ActionType.CALL)
    hand.apply_action("p1", ActionType.CHECK)  # closes preflop
    hand.apply_action("p1", ActionType.CHECK)  # flop betting, p1 acts first heads-up postflop
    hand.apply_action("p0", ActionType.CHECK)  # closes flop betting
    assert not hand.is_complete

    # now on the turn -- p1 folds here, which should be rabbit-hunt eligible
    folder = hand.current_actor_id
    hand.apply_action(folder, ActionType.FOLD)
    assert hand.is_complete
    assert hand.is_eligible_for_rabbit_hunt(folder)

    stack_before = hand.final_stacks()[folder]
    revealed = hand.rabbit_hunt(folder)
    assert len(revealed) == 1
    stack_after = hand.final_stacks()[folder]
    assert stack_before - stack_after == hand.small_blind
    assert hand.rabbit_hunts[folder] == hand.small_blind


def test_rabbit_hunt_cannot_be_used_twice():
    hand = Hand(
        seat_order=[("p0", 1000), ("p1", 1000)],
        button_index=0,
        small_blind=1,
        big_blind=2,
        rng=random.Random(5),
    )
    hand.apply_action("p0", ActionType.CALL)
    hand.apply_action("p1", ActionType.CHECK)
    hand.apply_action("p1", ActionType.CHECK)
    hand.apply_action("p0", ActionType.CHECK)
    folder = hand.current_actor_id
    hand.apply_action(folder, ActionType.FOLD)

    hand.rabbit_hunt(folder)
    with pytest.raises(OrchestratorError):
        hand.rabbit_hunt(folder)


def test_rabbit_hunt_before_hand_complete_raises():
    hand = Hand(
        seat_order=[("p0", 1000), ("p1", 1000)],
        button_index=0,
        small_blind=1,
        big_blind=2,
        rng=random.Random(5),
    )
    with pytest.raises(OrchestratorError):
        hand.rabbit_hunt("p0")


def test_rabbit_hunt_cost_capped_at_remaining_stack():
    hand = Hand(
        seat_order=[("p0", 1000), ("p1", 1000)],
        button_index=0,
        small_blind=1,
        big_blind=2,
        rng=random.Random(5),
    )
    hand.apply_action("p0", ActionType.CALL)
    hand.apply_action("p1", ActionType.CHECK)
    hand.apply_action("p1", ActionType.CHECK)
    hand.apply_action("p0", ActionType.CHECK)
    folder = hand.current_actor_id
    hand.apply_action(folder, ActionType.FOLD)
    assert hand.is_complete

    # Directly drive the edge case: whatever the realistic post-fold
    # stack happened to be, force it below the small blind to prove the
    # charge is capped rather than driving the stack negative.
    hand._player(folder).stack = 0
    hand.rabbit_hunt(folder)
    assert hand.final_stacks()[folder] == 0
    assert hand.rabbit_hunts[folder] == 0


def test_no_duplicate_cards_dealt_across_a_full_hand():
    hand = Hand(
        seat_order=[("p0", 1000), ("p1", 1000), ("p2", 1000)],
        button_index=0,
        small_blind=1,
        big_blind=2,
        rng=random.Random(9),
    )
    play_out_with_bots(hand)

    dealt = list(hand.community_cards) + list(hand.burned_cards)
    for p in hand.player_states:
        dealt.extend(p.hole_cards)
    dealt.extend(hand.deck)  # whatever's left undealt

    assert len(dealt) == 52
    assert len(set(dealt)) == 52


def test_all_in_preflop_heads_up_runs_board_out_automatically():
    hand = Hand(
        seat_order=[("p0", 10), ("p1", 10)],
        button_index=0,
        small_blind=1,
        big_blind=2,
        rng=random.Random(11),
    )
    assert hand.current_actor_id == "p0"
    hand.apply_action("p0", ActionType.ALL_IN)
    hand.apply_action("p1", ActionType.ALL_IN)
    # both players are now all-in with no further decisions possible --
    # the hand should auto-run the rest of the board straight to showdown
    assert hand.is_complete
    assert len(hand.community_cards) == 5
    assert sum(hand.result.payouts.values()) == 20


# ---------------------------------------------------------------------------
# Hand: runout (POLISH_PLAN.md Phase 0.5a)
# ---------------------------------------------------------------------------

_RUNOUT_STREET_SEQUENCE = [
    Street.DEAL_FLOP,
    Street.DEAL_THIRD_HOLE_CARD,
    Street.REVEAL_FOURTH_STREET,
    Street.REVEAL_FIFTH_STREET,
]


def test_all_in_preflop_runout_has_one_step_per_street_with_hole_cards_from_the_start():
    hand = Hand(
        seat_order=[("p0", 10), ("p1", 10)],
        button_index=0,
        small_blind=1,
        big_blind=2,
        rng=random.Random(11),
    )
    hand.apply_action("p0", ActionType.ALL_IN)
    hand.apply_action("p1", ActionType.ALL_IN)
    assert hand.is_complete

    assert [step.street for step in hand.runout] == _RUNOUT_STREET_SEQUENCE
    assert [len(step.community_cards) for step in hand.runout] == [3, 3, 4, 5]
    # both players were already locked in (all-in, nothing left to
    # decide) before the very first step even ran, so every step --
    # starting with the flop -- has both hole-card sets exposed, not
    # just the last one before showdown.
    for step in hand.runout:
        assert set(step.revealed_hole_cards.keys()) == {"p0", "p1"}

    # HandResult.runout is a snapshot taken the moment _finalize() ran,
    # not a live reference -- confirm it actually got threaded through
    # rather than silently staying the HandResult default ([]).
    assert hand.result.runout == hand.runout
    assert hand.result.runout is not hand.runout


def test_checked_down_hand_runout_has_one_step_per_street_with_no_early_reveal():
    hand = Hand(
        seat_order=[("p0", 1000), ("p1", 1000), ("p2", 1000)],
        button_index=0,
        small_blind=1,
        big_blind=2,
        rng=random.Random(7),
    )
    play_out_with_bots(hand)
    assert hand.is_complete
    # confirms this scenario actually exercises "nobody went all-in" --
    # the reference bot policy always checks/calls small amounts here,
    # never shoving a 1000-chip stack, so the runout's early-reveal
    # condition should never trigger below.
    assert all(not p.all_in for p in hand.player_states)

    assert [step.street for step in hand.runout] == _RUNOUT_STREET_SEQUENCE
    assert [len(step.community_cards) for step in hand.runout] == [3, 3, 4, 5]
    # hole cards only ever become public at the real showdown (via
    # hand.result.revealed_hands) for a hand like this one -- no step
    # should reveal anything early.
    assert all(step.revealed_hole_cards == {} for step in hand.runout)


def test_fold_after_flop_stops_the_runout_at_the_point_of_the_fold():
    hand = Hand(
        seat_order=[("p0", 1000), ("p1", 1000), ("p2", 1000)],
        button_index=0,
        small_blind=1,
        big_blind=2,
        rng=random.Random(7),
    )
    hand.apply_action("p0", ActionType.CALL)
    hand.apply_action("p1", ActionType.CALL)
    hand.apply_action("p2", ActionType.CHECK)  # closes preflop
    assert not hand.is_complete
    # the flop and 3rd hole cards are both dealt automatically before
    # flop betting opens -- the runout should already reflect exactly
    # those two steps.
    assert [step.street for step in hand.runout] == [
        Street.DEAL_FLOP,
        Street.DEAL_THIRD_HOLE_CARD,
    ]

    actor = hand.current_actor_id
    hand.apply_action(actor, ActionType.BET, amount=20)
    for _ in range(2):
        actor = hand.current_actor_id
        hand.apply_action(actor, ActionType.FOLD)

    assert hand.is_complete
    assert len(hand.result.folded_players) == 2
    # folding down to one player ends the hand immediately, via
    # HandFlow's own "everyone else folded" logic, without ever
    # reaching REVEAL_FOURTH_STREET / REVEAL_FIFTH_STREET -- nothing
    # here should fabricate steps for streets the hand never visited.
    assert [step.street for step in hand.runout] == [
        Street.DEAL_FLOP,
        Street.DEAL_THIRD_HOLE_CARD,
    ]


def test_immediate_preflop_fold_out_hand_has_an_empty_runout():
    hand = Hand(
        seat_order=[("p0", 1000), ("p1", 1000), ("p2", 1000)],
        button_index=0,
        small_blind=1,
        big_blind=2,
        rng=random.Random(3),
    )
    hand.apply_action("p0", ActionType.FOLD)
    hand.apply_action("p1", ActionType.FOLD)
    assert hand.is_complete
    # community cards are never dealt at all when a hand ends preflop --
    # there's nothing for the runout to record.
    assert hand.runout == []
    assert hand.result.runout == []


# ---------------------------------------------------------------------------
# Hand: deterministic outcome via an injected rigged deck
# ---------------------------------------------------------------------------

def _build_rigged_heads_up_deck() -> list:
    """
    Heads-up, p0=button/SB, p1=BB. Dealing order (left of button first)
    means p1's cards are drawn before p0's at every step.

    p1 ends up with pocket rockets plus a third ace (trip aces locked
    from hole cards alone, regardless of the board).
    p0 gets three unconnected, unpaired low/mid cards, and the board is
    chosen so p0 can't pair, straight, or flush -- guaranteed to lose.
    """
    p1_hole = parse_cards("Ah Ad")       # rounds 1 & 2
    p0_hole = parse_cards("2c 7d")       # rounds 1 & 2
    p1_third = parse_cards("As")[0]
    p0_third = parse_cards("9s")[0]
    board = parse_cards("Kc Qd Jc 4h 3d")  # flop(3) + turn + river

    draw_sequence = (
        [p1_hole[0], p0_hole[0], p1_hole[1], p0_hole[1]]  # hole card rounds 1 & 2
        + ["BURN1"] + list(board[0:3])                     # burn + flop
        + ["BURN2"] + [p1_third, p0_third]                 # burn + 3rd hole cards
        + ["BURN3"] + [board[3]]                            # burn + 4th street facedown
        + ["BURN4"] + [board[4]]                            # burn + 5th street facedown
    )

    used = set(c for c in draw_sequence if isinstance(c, Card))
    pool = [c for c in full_deck() if c not in used]
    junk_burns = pool[:4]
    filler = pool[4:]

    sequence = []
    burn_iter = iter(junk_burns)
    for item in draw_sequence:
        sequence.append(next(burn_iter) if item == "BURN1" or item == "BURN2"
                         or item == "BURN3" or item == "BURN4" else item)

    deck = filler + list(reversed(sequence))
    assert len(deck) == 52
    assert len(set(deck)) == 52
    return deck


def test_rigged_deck_produces_deterministic_showdown_winner():
    deck = _build_rigged_heads_up_deck()
    hand = Hand(
        seat_order=[("p0", 1000), ("p1", 1000)],
        button_index=0,
        small_blind=1,
        big_blind=2,
        deck=deck,
    )
    # p0 (button) acts first heads-up preflop; both just check/call down
    while not hand.is_complete:
        actor = hand.current_actor_id
        legal = hand.legal_actions(actor)
        if ActionType.CHECK in legal:
            hand.apply_action(actor, ActionType.CHECK)
        else:
            hand.apply_action(actor, ActionType.CALL)

    assert hand.result.payouts.get("p1", 0) > hand.result.payouts.get("p0", 0)
    assert hand.final_stacks()["p1"] > 1000
    assert hand.final_stacks()["p0"] < 1000
    assert sum(hand.final_stacks().values()) == 2000


# ---------------------------------------------------------------------------
# Tournament: setup and single-hand wiring
# ---------------------------------------------------------------------------

def test_tournament_create_seats_everyone_with_starting_stack():
    t = Tournament.create(
        player_ids=[f"p{i}" for i in range(6)],
        starting_stack=40,
        max_table_size=10,
        rng=random.Random(1),
    )
    assert set(t.stacks.keys()) == {f"p{i}" for i in range(6)}
    assert all(stack == 40 for stack in t.stacks.values())
    assert len(t.state.tables) == 1


def test_start_hand_uses_current_blind_level():
    t = Tournament.create(
        player_ids=[f"p{i}" for i in range(4)],
        starting_stack=40,
        max_table_size=10,
        rng=random.Random(1),
    )
    hand = t.start_hand("T1")
    assert hand.small_blind == 1  # level 1 of the default schedule
    assert hand.big_blind == 2
    assert {p.player_id for p in hand.player_states} == set(t.stacks.keys())


def test_start_hand_reflects_blind_escalation_after_clock_advances():
    t = Tournament.create(
        player_ids=[f"p{i}" for i in range(4)],
        starting_stack=40,
        max_table_size=10,
        rng=random.Random(1),
    )
    t.advance_clock(901)  # just past the first 15-minute level
    hand = t.start_hand("T1")
    assert (hand.small_blind, hand.big_blind) == (2, 4)


def test_cannot_start_two_hands_at_the_same_table_concurrently():
    t = Tournament.create(
        player_ids=[f"p{i}" for i in range(4)],
        starting_stack=40,
        max_table_size=10,
        rng=random.Random(1),
    )
    t.start_hand("T1")
    with pytest.raises(OrchestratorError):
        t.start_hand("T1")


def test_complete_hand_writes_stacks_back_to_tournament():
    t = Tournament.create(
        player_ids=[f"p{i}" for i in range(4)],
        starting_stack=40,
        max_table_size=10,
        rng=random.Random(2),
    )
    hand = t.start_hand("T1")
    play_out_with_bots(hand)
    result = t.complete_hand("T1")
    assert t.stacks == result.final_stacks
    assert sum(t.stacks.values()) == 160  # no chips created or destroyed


def test_button_advances_to_next_occupied_seat_across_hands():
    t = Tournament.create(
        player_ids=[f"p{i}" for i in range(4)],
        starting_stack=1000,  # deep stacks -- nobody should bust from blinds alone
        max_table_size=10,
        rng=random.Random(3),
    )
    hand1 = t.start_hand("T1")
    first_button_pid = hand1.player_states[0].player_id
    play_out_with_bots(hand1)
    t.complete_hand("T1")

    hand2 = t.start_hand("T1")
    second_button_pid = hand2.player_states[0].player_id
    assert second_button_pid != first_button_pid


# ---------------------------------------------------------------------------
# Tournament: elimination via a rigged deterministic hand
# ---------------------------------------------------------------------------

def test_complete_hand_eliminates_busted_player_and_completes_heads_up_tournament():
    t = Tournament.create(
        player_ids=["p0", "p1"],
        starting_stack=2,  # posting blinds alone puts both fully in on this deal
        max_table_size=10,
        rng=random.Random(1),
    )
    deck = _build_rigged_heads_up_deck()
    hand = t.start_hand("T1", deck=deck)
    while not hand.is_complete:
        actor = hand.current_actor_id
        legal = hand.legal_actions(actor)
        if ActionType.CHECK in legal:
            hand.apply_action(actor, ActionType.CHECK)
        else:
            hand.apply_action(actor, ActionType.CALL)

    t.complete_hand("T1")
    assert t.is_complete()
    winner = t.finalize()
    assert winner == "p1"
    assert t.state.players["p0"].eliminated
    assert t.state.players["p0"].finish_position == 2
    assert t.state.players["p1"].finish_position == 1


# ---------------------------------------------------------------------------
# Tournament: multi-hand simulation with bots (structural invariants)
# ---------------------------------------------------------------------------

def test_multi_hand_bot_simulation_keeps_chips_conserved_and_terminates():
    rng = random.Random(123)
    player_ids = [f"p{i}" for i in range(6)]
    t = Tournament.create(
        player_ids=player_ids,
        starting_stack=20,  # shallow on purpose so blind pressure eliminates people quickly
        max_table_size=10,
        blind_schedule=generate_default_schedule(num_levels=6),
        rng=rng,
    )
    total_chips = sum(t.stacks.values())

    max_hands = 500
    hands_played = 0
    while not t.is_complete() and hands_played < max_hands:
        for table_id in list(t.active_table_ids()):
            if table_id in t.hands_by_table:
                continue
            hand = t.start_hand(table_id)
            play_out_with_bots(hand)
            t.complete_hand(table_id)
            hands_played += 1
        t.advance_clock(60)  # move the clock along so blinds eventually escalate

    assert t.is_complete(), f"tournament did not finish within {max_hands} hands"
    assert sum(t.stacks.values()) == total_chips

    winner = t.finalize()
    assert t.stacks[winner] == total_chips  # winner has every chip in the tournament
    finish_positions = {pid: t.state.players[pid].finish_position for pid in player_ids}
    assert sorted(finish_positions.values()) == list(range(1, len(player_ids) + 1))
