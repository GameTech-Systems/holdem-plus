"""
Minimal runnable example of the orchestrator API -- this is what a UI
or bot integration actually talks to: two classes, Hand and Tournament,
instead of the five underlying modules directly.

Run with: python3 example_usage.py
"""

import random

from betting_state_machine import ActionType
from orchestrator import Hand, Tournament, default_bot_action, play_out_with_bots
from tournament_structure import generate_default_schedule


def example_single_hand():
    print("=== Single hand, manual actions ===")
    hand = Hand(
        seat_order=[("alice", 500), ("bob", 500), ("carol", 500)],
        button_index=0,
        small_blind=1,
        big_blind=2,
        rng=random.Random(42),
    )

    while not hand.is_complete:
        actor = hand.current_actor_id
        legal = hand.legal_actions(actor)
        # A real UI/bot would show `legal` to the player and get a real
        # decision; here we just use the reference bot policy.
        action = default_bot_action(hand, actor)
        print(f"  {actor} -> {action.action_type.name}"
              + (f" {action.amount}" if action.amount else ""))
        hand.apply_action(actor, action.action_type, action.amount)

    print(f"  Community cards: {hand.community_cards}")
    print(f"  Payouts: {hand.result.payouts}")
    print(f"  Final stacks: {hand.final_stacks()}")
    print()


def example_tournament():
    print("=== Small tournament, driven to completion ===")
    players = [f"player_{i}" for i in range(9)]
    t = Tournament.create(
        player_ids=players,
        starting_stack=40,          # matches the source spec's Simple Format Option
        max_table_size=10,
        blind_schedule=generate_default_schedule(num_levels=8),
        rng=random.Random(7),
    )

    hands_played = 0
    while not t.is_complete():
        for table_id in list(t.active_table_ids()):
            if table_id in t.hands_by_table:
                continue
            hand = t.start_hand(table_id)
            play_out_with_bots(hand)
            t.complete_hand(table_id)
            hands_played += 1
        t.advance_clock(60)  # simulate a minute passing between hand batches

    winner = t.finalize()
    print(f"  Hands played: {hands_played}")
    print(f"  Winner: {winner}")
    print(f"  Final chip counts: {t.stacks}")
    print(f"  Finishing order: "
          f"{sorted(players, key=lambda p: t.state.players[p].finish_position)}")


if __name__ == "__main__":
    example_single_hand()
    example_tournament()
