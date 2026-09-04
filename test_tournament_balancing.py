"""
Tests for tournament_balancing.py.

Run with: pytest -v test_tournament_balancing.py
"""

import random

import pytest

from tournament_balancing import (
    TableFullError,
    TournamentError,
    create_tournament,
    eliminate_player,
    finalize_tournament,
    rebalance,
)


def player_ids(n: int) -> list:
    return [f"p{i}" for i in range(n)]


# ---------------------------------------------------------------------------
# create_tournament
# ---------------------------------------------------------------------------

def test_create_tournament_rejects_empty_field():
    with pytest.raises(TournamentError):
        create_tournament([], max_table_size=10)


def test_create_tournament_rejects_too_small_table_size():
    with pytest.raises(TournamentError):
        create_tournament(player_ids(5), max_table_size=1)


def test_every_player_seated_exactly_once():
    state = create_tournament(player_ids(23), max_table_size=10, rng=random.Random(1))
    seated_ids = set()
    for table in state.tables.values():
        for pid in table.occupied_seats().values():
            assert pid not in seated_ids  # no duplicates
            seated_ids.add(pid)
    assert seated_ids == set(player_ids(23))


def test_initial_tables_within_one_player_of_each_other():
    state = create_tournament(player_ids(23), max_table_size=10, rng=random.Random(1))
    counts = [t.player_count() for t in state.tables.values()]
    assert max(counts) - min(counts) <= 1
    assert all(c <= 10 for c in counts)


def test_uses_minimum_number_of_tables():
    # 23 players at 10-max should need exactly 3 tables (ceil(23/10))
    state = create_tournament(player_ids(23), max_table_size=10, rng=random.Random(1))
    assert len(state.tables) == 3


def test_exact_multiple_of_table_size_fills_tables_evenly():
    state = create_tournament(player_ids(20), max_table_size=10, rng=random.Random(1))
    counts = [t.player_count() for t in state.tables.values()]
    assert counts == [10, 10]


def test_single_table_when_field_fits():
    state = create_tournament(player_ids(9), max_table_size=10, rng=random.Random(1))
    assert len(state.tables) == 1
    assert state.tables["T1"].player_count() == 9


# ---------------------------------------------------------------------------
# eliminate_player
# ---------------------------------------------------------------------------

def test_eliminate_player_marks_eliminated_and_vacates_seat():
    state = create_tournament(player_ids(9), max_table_size=10, rng=random.Random(1))
    eliminate_player(state, "p0")
    assert state.players["p0"].eliminated
    assert state.players["p0"].table_id is None
    assert "p0" not in state.tables["T1"].occupied_seats().values()


def test_eliminate_player_assigns_descending_finish_positions():
    state = create_tournament(player_ids(5), max_table_size=10, rng=random.Random(1))
    positions = []
    order = ["p0", "p1", "p2", "p3"]
    for pid in order:
        positions.append(eliminate_player(state, pid))
    # 5 players active -> first elimination finishes 5th, ... down to 2nd
    assert positions == [5, 4, 3, 2]
    finalize_tournament(state)  # last remaining player, p4, finishes 1st
    assert state.players["p4"].finish_position == 1


def test_eliminate_unknown_player_raises():
    state = create_tournament(player_ids(5), max_table_size=10, rng=random.Random(1))
    with pytest.raises(KeyError):
        eliminate_player(state, "ghost")


def test_eliminate_already_eliminated_player_raises():
    state = create_tournament(player_ids(5), max_table_size=10, rng=random.Random(1))
    eliminate_player(state, "p0")
    with pytest.raises(TournamentError):
        eliminate_player(state, "p0")


def test_finalize_before_tournament_is_actually_down_to_one_raises():
    state = create_tournament(player_ids(5), max_table_size=10, rng=random.Random(1))
    with pytest.raises(TournamentError):
        finalize_tournament(state)


def test_finalize_seats_winner_out_and_returns_winner_id():
    state = create_tournament(player_ids(2), max_table_size=10, rng=random.Random(1))
    eliminate_player(state, "p0")
    winner = finalize_tournament(state)
    assert winner == "p1"
    assert state.players["p1"].table_id is None


# ---------------------------------------------------------------------------
# Table breaking / consolidation
# ---------------------------------------------------------------------------

def test_table_breaks_when_field_fits_in_fewer_tables():
    # 20 players, 2 tables of 10. Eliminate until only 9 total remain --
    # they should now fit in a single table of 10, so one table breaks.
    state = create_tournament(player_ids(20), max_table_size=10, rng=random.Random(2))
    for i in range(11):  # 20 -> 9 players
        eliminate_player(state, f"p{i}", rng=random.Random(2))
    assert state.active_player_count() == 9
    assert len(state.tables) == 1  # consolidated down to one table


def test_broken_table_players_all_reseated_without_duplication():
    state = create_tournament(player_ids(20), max_table_size=10, rng=random.Random(3))
    for i in range(11):
        eliminate_player(state, f"p{i}", rng=random.Random(3))

    remaining_expected = set(player_ids(20)) - {f"p{i}" for i in range(11)}
    seated_ids = set()
    for table in state.tables.values():
        for pid in table.occupied_seats().values():
            assert pid not in seated_ids
            seated_ids.add(pid)
    assert seated_ids == remaining_expected


def test_no_table_ever_exceeds_max_seats_during_consolidation():
    state = create_tournament(player_ids(31), max_table_size=10, rng=random.Random(4))
    rng = random.Random(4)
    order = player_ids(31)
    rng.shuffle(order)
    for pid in order[:-1]:
        eliminate_player(state, pid, rng=rng)
        for table in state.tables.values():
            assert table.player_count() <= table.max_seats


# ---------------------------------------------------------------------------
# Balancing (no breaking involved)
# ---------------------------------------------------------------------------

def test_balance_step_moves_player_when_imbalance_reaches_threshold():
    state = create_tournament(player_ids(20), max_table_size=10, rng=random.Random(5))
    # manufacture an imbalance: bust 3 players all from table T1 specifically,
    # bypassing the normal auto-rebalance by calling eliminate then re-checking
    t1_players = list(state.tables["T1"].occupied_seats().values())
    for pid in t1_players[:3]:
        eliminate_player(state, pid, rng=random.Random(5))

    counts = [t.player_count() for t in state.active_tables()]
    assert max(counts) - min(counts) <= 1  # rebalance() already smoothed it out


def test_rebalance_is_idempotent_when_already_balanced():
    state = create_tournament(player_ids(20), max_table_size=10, rng=random.Random(6))
    before = {tid: t.player_count() for tid, t in state.tables.items()}
    rebalance(state, rng=random.Random(6))
    after = {tid: t.player_count() for tid, t in state.tables.items()}
    assert before == after


# ---------------------------------------------------------------------------
# Full simulation: invariants must hold at every step of a whole tournament
# ---------------------------------------------------------------------------

def test_full_tournament_simulation_maintains_invariants_throughout():
    rng = random.Random(42)
    all_players = player_ids(37)
    state = create_tournament(all_players, max_table_size=9, rng=rng)

    elimination_order = list(all_players)
    rng.shuffle(elimination_order)

    seen_finish_positions = set()
    for pid in elimination_order[:-1]:  # leave exactly one player standing
        position = eliminate_player(state, pid, rng=rng)

        # Invariant 1: finish positions are unique
        assert position not in seen_finish_positions
        seen_finish_positions.add(position)

        # Invariant 2: no table exceeds capacity
        for table in state.active_tables():
            assert table.player_count() <= table.max_seats

        # Invariant 3: active tables never differ in size by more than 1
        counts = [t.player_count() for t in state.active_tables()]
        if counts:
            assert max(counts) - min(counts) <= 1

        # Invariant 4: every remaining active player is seated exactly once
        seated = [
            p for t in state.active_tables() for p in t.occupied_seats().values()
        ]
        assert sorted(seated) == sorted(state.active_player_ids())

        # Invariant 5: table count never exceeds what's actually needed
        import math
        min_tables_needed = math.ceil(state.active_player_count() / 9) if state.active_player_count() else 0
        assert len(state.active_tables()) <= max(min_tables_needed, 1)

    assert state.active_player_count() == 1
    winner = finalize_tournament(state)
    assert winner == elimination_order[-1]

    # All finish positions from 2..N were assigned, plus 1 for the winner
    seen_finish_positions.add(1)
    assert seen_finish_positions == set(range(1, 38))


def test_full_tournament_all_tables_empty_at_the_end():
    rng = random.Random(7)
    all_players = player_ids(15)
    state = create_tournament(all_players, max_table_size=9, rng=rng)
    order = list(all_players)
    rng.shuffle(order)
    for pid in order[:-1]:
        eliminate_player(state, pid, rng=rng)
    finalize_tournament(state)
    assert all(t.is_empty() for t in state.tables.values())
