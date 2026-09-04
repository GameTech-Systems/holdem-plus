"""
Elimination / table-balancing logic for Hold'em Plus tournaments.

The source concept's "Billion Dollar Challenge" format is described as
single-table (10-player max) sit-and-goes chained together, but the same
tournament shell also needs to support a straightforward multi-table
event (an online room or a card-room floor running one bigger field
instead of many small ones), which is what this module is for: given a
pool of tables and players, keep tables balanced as players bust out,
and consolidate ("break") tables as the field shrinks -- exactly what
every real MTT does between hands.

Scope, deliberately:
  - Seating/eliminating/balancing/breaking tables. That's it.
  - Does NOT touch chip stacks, betting, or hand play -- those live in
    betting_state_machine.py / side_pots.py. This module only answers
    "who is sitting where, and does the seating need to change."
  - Player moves happen immediately on elimination, as a discrete event
    between hands. Real rooms sometimes delay a move until the moved
    player's next big blind to avoid mid-orbit disruption -- that's a
    presentation-layer/scheduling nuance to layer on top of this later,
    not a change to the underlying balancing logic.
  - No "don't reseat two players who were just at the same table
    together" softening rule. Real MTT software does this; it's a
    reasonable v2 refinement flagged here rather than built now.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional


# A table is considered unbalanced once the gap between its player count
# and another active table's player count reaches this many players.
BALANCE_THRESHOLD = 2


@dataclass
class Table:
    table_id: str
    max_seats: int
    seats: Dict[int, Optional[str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.seats:
            self.seats = {i: None for i in range(1, self.max_seats + 1)}

    def occupied_seats(self) -> Dict[int, str]:
        return {seat: pid for seat, pid in self.seats.items() if pid is not None}

    def open_seat_numbers(self) -> List[int]:
        return [seat for seat, pid in self.seats.items() if pid is None]

    def player_count(self) -> int:
        return len(self.occupied_seats())

    def is_empty(self) -> bool:
        return self.player_count() == 0

    def seat_player(self, player_id: str, seat_number: Optional[int] = None,
                     rng: Optional[random.Random] = None) -> int:
        open_seats = self.open_seat_numbers()
        if not open_seats:
            raise TableFullError(f"Table {self.table_id} has no open seats")
        if seat_number is None:
            rng = rng or random.Random()
            seat_number = rng.choice(open_seats)
        elif self.seats.get(seat_number) is not None:
            raise TableFullError(f"Seat {seat_number} at table {self.table_id} is occupied")
        self.seats[seat_number] = player_id
        return seat_number

    def remove_player(self, player_id: str) -> None:
        for seat, pid in self.seats.items():
            if pid == player_id:
                self.seats[seat] = None
                return
        raise KeyError(f"{player_id} is not seated at table {self.table_id}")


@dataclass
class PlayerInfo:
    player_id: str
    table_id: Optional[str] = None
    seat_number: Optional[int] = None
    eliminated: bool = False
    finish_position: Optional[int] = None


class TableFullError(Exception):
    pass


class TournamentError(Exception):
    pass


@dataclass
class TournamentState:
    tables: Dict[str, Table]
    players: Dict[str, PlayerInfo]
    target_table_size: int

    def active_tables(self) -> List[Table]:
        return [t for t in self.tables.values() if t.player_count() > 0]

    def active_player_ids(self) -> List[str]:
        return [pid for pid, p in self.players.items() if not p.eliminated]

    def active_player_count(self) -> int:
        return len(self.active_player_ids())

    def is_complete(self) -> bool:
        return self.active_player_count() <= 1


# ---------------------------------------------------------------------------
# Tournament creation
# ---------------------------------------------------------------------------

def create_tournament(
    player_ids: List[str],
    max_table_size: int,
    rng: Optional[random.Random] = None,
) -> TournamentState:
    """
    Randomly draws players into as few tables as possible while keeping
    initial table sizes within 1 player of each other (the standard way
    a field is drawn into starting tables), each table capped at
    max_table_size seats.
    """
    if not player_ids:
        raise TournamentError("Cannot start a tournament with zero players")
    if max_table_size < 2:
        raise TournamentError("max_table_size must be at least 2")

    rng = rng or random.Random()
    shuffled = list(player_ids)
    rng.shuffle(shuffled)

    total = len(shuffled)
    num_tables = -(-total // max_table_size)  # ceil division
    base_size, remainder = divmod(total, num_tables)

    tables: Dict[str, Table] = {}
    players: Dict[str, PlayerInfo] = {}
    cursor = 0
    for i in range(1, num_tables + 1):
        table_id = f"T{i}"
        size_this_table = base_size + (1 if i <= remainder else 0)
        table = Table(table_id=table_id, max_seats=max_table_size)
        for player_id in shuffled[cursor:cursor + size_this_table]:
            seat = table.seat_player(player_id, rng=rng)
            players[player_id] = PlayerInfo(
                player_id=player_id, table_id=table_id, seat_number=seat
            )
        tables[table_id] = table
        cursor += size_this_table

    return TournamentState(tables=tables, players=players, target_table_size=max_table_size)


# ---------------------------------------------------------------------------
# Elimination
# ---------------------------------------------------------------------------

def eliminate_player(
    state: TournamentState,
    player_id: str,
    rng: Optional[random.Random] = None,
) -> int:
    """
    Marks a player eliminated, vacates their seat, assigns their finishing
    position, and triggers rebalancing. Returns the finish position
    assigned (1 = tournament winner, higher numbers = earlier bust-outs).

    Does not itself decide when a player should be eliminated (that's a
    stack == 0 decision made by whatever's driving the actual hand play);
    this just records the event and updates the seating.
    """
    player = state.players.get(player_id)
    if player is None:
        raise KeyError(f"Unknown player_id: {player_id}")
    if player.eliminated:
        raise TournamentError(f"{player_id} is already eliminated")

    finish_position = state.active_player_count()  # they were one of this many just before busting
    player.eliminated = True
    player.finish_position = finish_position

    if player.table_id is not None:
        state.tables[player.table_id].remove_player(player_id)
    player.table_id = None
    player.seat_number = None

    rebalance(state, rng=rng)
    return finish_position


def finalize_tournament(state: TournamentState) -> str:
    """
    Call once state.is_complete() is True to assign the winner's finish
    position (1st place) and clear their seat. Returns the winner's
    player_id.
    """
    remaining = state.active_player_ids()
    if len(remaining) != 1:
        raise TournamentError(
            f"Tournament is not down to a single winner yet ({len(remaining)} players remain)"
        )
    winner_id = remaining[0]
    winner = state.players[winner_id]
    winner.finish_position = 1
    if winner.table_id is not None:
        state.tables[winner.table_id].remove_player(winner_id)
    winner.table_id = None
    winner.seat_number = None
    return winner_id


# ---------------------------------------------------------------------------
# Rebalancing
# ---------------------------------------------------------------------------

def rebalance(state: TournamentState, rng: Optional[random.Random] = None) -> None:
    """
    Repeatedly breaks tables that are no longer needed and moves players
    to even out table sizes, until the seating is stable:
      - no table can be broken (i.e. the field no longer fits in one
        fewer table at target_table_size), and
      - no two active tables differ in player count by more than 1.
    """
    rng = rng or random.Random()
    max_iterations = 10 * (len(state.players) + 1)

    for _ in range(max_iterations):
        table_to_break = _table_that_should_break(state)
        if table_to_break is not None:
            _break_table(state, table_to_break, rng)
            continue

        if _balance_step(state, rng):
            continue

        return  # stable: nothing left to break or balance

    raise TournamentError(
        "rebalance() did not converge within the iteration budget -- "
        "this indicates a bug in the balancing logic, not a valid tournament state."
    )


def _table_that_should_break(state: TournamentState) -> Optional[str]:
    active = state.active_tables()
    if len(active) <= 1:
        return None

    total_active_players = sum(t.player_count() for t in active)
    remaining_table_capacity = (len(active) - 1) * state.target_table_size
    if total_active_players > remaining_table_capacity:
        return None  # field doesn't fit in one fewer table yet

    smallest = min(active, key=lambda t: (t.player_count(), t.table_id))
    return smallest.table_id


def _break_table(state: TournamentState, table_id: str, rng: random.Random) -> None:
    table = state.tables[table_id]
    displaced_players = list(table.occupied_seats().values())
    rng.shuffle(displaced_players)

    for player_id in displaced_players:
        destination = _table_with_fewest_players(state, exclude=table_id)
        if destination is None:
            raise TournamentError(
                f"No open seats available to absorb players from broken table {table_id}"
            )
        seat = destination.seat_player(player_id, rng=rng)
        player = state.players[player_id]
        player.table_id = destination.table_id
        player.seat_number = seat
        table.remove_player(player_id)

    del state.tables[table_id]


def _table_with_fewest_players(
    state: TournamentState, exclude: str
) -> Optional[Table]:
    candidates = [
        t for tid, t in state.tables.items()
        if tid != exclude and len(t.open_seat_numbers()) > 0
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda t: (t.player_count(), t.table_id))


def _balance_step(state: TournamentState, rng: random.Random) -> bool:
    """Moves a single player from the fullest to the emptiest active table
    if they differ by BALANCE_THRESHOLD or more. Returns True if a move
    was made (caller should re-check for further imbalance/breaks)."""
    active = state.active_tables()
    if len(active) < 2:
        return False

    fullest = max(active, key=lambda t: (t.player_count(), t.table_id))
    emptiest = min(active, key=lambda t: (t.player_count(), t.table_id))

    if fullest.table_id == emptiest.table_id:
        return False
    if fullest.player_count() - emptiest.player_count() < BALANCE_THRESHOLD:
        return False
    if not emptiest.open_seat_numbers():
        return False

    movable = list(fullest.occupied_seats().values())
    player_id = rng.choice(movable)

    fullest.remove_player(player_id)
    seat = emptiest.seat_player(player_id, rng=rng)
    player = state.players[player_id]
    player.table_id = emptiest.table_id
    player.seat_number = seat
    return True
