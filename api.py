"""
Thin REST + WebSocket API layer over the Hold'em Plus orchestrator
(Hand + Tournament) -- this is the "next seam" from the tech plan: it
puts the game engine on the network so a browser client (e.g. a forked
PokerTH web client) or a bot can play without importing any Python.

Scope, deliberately, for a fake-money v1 demo:

  - Single-table games only. A "table" here maps 1:1 onto a Tournament
    created with max_table_size == the table's seat count, which always
    produces exactly one internal table ("T1"). Tournament already
    supports multi-table balancing for later; this API just doesn't
    route across tables yet -- see the handoff doc for that seam.
  - Fully in-memory. No database, no persistence across restarts, no
    auth beyond an opaque guest player_id the client holds onto. Fine
    for a public demo; NOT fine for anything with real stakes.
  - Must run as a single process / single worker: state lives in
    module-level dicts, not a shared store. A real deployment needs
    something like Redis or a DB behind TableSession before running more
    than one worker or more than one machine.
  - No reconnect/session-resume story beyond REST polling: a dropped
    WebSocket loses the live push channel, but GET /tables/{id}/state
    still works, and the player's seat/stack/hand aren't affected by a
    lost socket -- their next action (via REST or a fresh WS connection)
    picks up wherever the hand actually is.
  - Guest play only, matching the "no login to try it" requirement --
    POST /guest just mints an id, no password/verification of any kind.

Run locally with:  uvicorn api:app --reload
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from betting_state_machine import ActionType, IllegalActionError
from orchestrator import Hand, HandResult, OrchestratorError, Tournament
from tournament_structure import generate_default_schedule

INTERNAL_TABLE_ID = "T1"  # Tournament's internal table id when max_table_size == seat count

app = FastAPI(title="Hold'em Plus Demo API", version="0.1.0")

# Permissive for demo purposes only -- lock this down to the actual
# frontend origin(s) before this touches anything but a local/dev demo.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# In-memory state
# ---------------------------------------------------------------------------

@dataclass
class TableSession:
    table_id: str
    max_seats: int
    starting_stack: int
    player_ids: List[str] = field(default_factory=list)
    status: str = "waiting"  # waiting | in_progress | complete
    tournament: Optional[Tournament] = None
    connections: Dict[WebSocket, Optional[str]] = field(default_factory=dict)
    # The most recently finished hand at this table, kept around so a
    # client can see what happened even after the next hand has already
    # been dealt (see HANDOFF.md Bug 2 -- complete_hand() used to run,
    # then _start_next_hand_if_needed() would immediately overwrite
    # hands_by_table["T1"] with a new Hand before anything was ever sent
    # to a client, so the finished hand's payouts/showdown were computed
    # correctly but never actually reached anyone). Persisted here
    # (rather than sent as a one-off message only) so it survives a
    # missed broadcast, a fresh GET /state, or a WS reconnect a moment
    # later, not just the exact instant the hand completed.
    last_hand_result: Optional[HandResult] = None
    # The actual just-finished Hand object (not just its HandResult),
    # kept alive for exactly as long as last_hand_result above so
    # /rabbit-hunt has something to call .rabbit_hunt() on (see
    # HANDOFF.md Bug 3 -- Tournament.complete_hand() deletes the Hand
    # from hands_by_table and only ever returns/keeps its HandResult, so
    # rabbit_hunt() -- a method on the live Hand, needing its mutable
    # PlayerState/rabbit_hunts bookkeeping -- had no object left to run
    # against by the time any client could ever call the endpoint; a
    # replacement hand is dealt synchronously in the same request that
    # completed the old one, so there is no timing window in which
    # _current_hand() could still return it). Same "most recent only"
    # lifetime/limitation as last_hand_result: once a further hand
    # completes, this reference moves on and the previous rabbit-hunt
    # window is gone, matching how last_hand_result already behaves.
    last_completed_hand: Optional[Hand] = None


GUESTS: Dict[str, str] = {}          # player_id -> display_name
TABLES: Dict[str, TableSession] = {}  # table_id -> TableSession


def _get_table(table_id: str) -> TableSession:
    session = TABLES.get(table_id)
    if session is None:
        raise HTTPException(404, f"No such table: {table_id}")
    return session


def _current_hand(session: TableSession) -> Optional[Hand]:
    if session.tournament is None:
        return None
    return session.tournament.hands_by_table.get(INTERNAL_TABLE_ID)


def _start_next_hand_if_needed(session: TableSession) -> None:
    t = session.tournament
    assert t is not None
    if t.is_complete():
        session.status = "complete"
        return
    if INTERNAL_TABLE_ID in t.hands_by_table:
        return  # a hand is already in progress
    t.start_hand(INTERNAL_TABLE_ID)


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------

class GuestCreateRequest(BaseModel):
    display_name: Optional[str] = None


class CreateTableRequest(BaseModel):
    max_seats: int = 10
    starting_stack: int = 40  # matches the source spec's Simple Format Option


class JoinTableRequest(BaseModel):
    player_id: str


class ActionRequest(BaseModel):
    player_id: str
    action_type: str  # matches betting_state_machine.ActionType member names
    amount: int = 0


class RabbitHuntRequest(BaseModel):
    player_id: str


# ---------------------------------------------------------------------------
# State serialization -- redacts hole cards the viewer isn't allowed to see
# ---------------------------------------------------------------------------

def _serialize_hand_result(
    result: HandResult,
    hand: Optional[Hand],
    viewer_player_id: Optional[str],
) -> dict:
    """Serializes a *finished* hand's outcome for the 'last_hand' field --
    same card-stringification convention as the live 'hand' payload
    below, but there's no viewer-based redaction to do here: every card
    in revealed_hands already went to showdown and is public, and a
    folded player's hole cards were never added to revealed_hands in the
    first place (see orchestrator.Hand._finalize).

    `hand`, if given, is the actual Hand object this result came from
    (see TableSession.last_completed_hand) -- used only to compute
    rabbit_hunt_eligible for the requesting viewer. This is the correct
    home for that flag: it was previously computed against whatever hand
    happened to be *currently* in progress, which (per HANDOFF.md Bug 3)
    is never the hand this eligibility question is actually about.
    """
    rabbit_hunt_eligible = (
        hand is not None
        and viewer_player_id is not None
        and hand.is_eligible_for_rabbit_hunt(viewer_player_id)
        and viewer_player_id not in hand.rabbit_hunts
    )
    return {
        "is_complete": True,
        "payouts": dict(result.payouts),
        "community_cards": [str(c) for c in result.community_cards],
        "revealed_hands": {
            pid: [str(c) for c in cards] for pid, cards in result.revealed_hands.items()
        },
        "folded_players": list(result.folded_players),
        "rabbit_hunt_eligible": rabbit_hunt_eligible,
    }


def _serialize_state(session: TableSession, viewer_player_id: Optional[str]) -> dict:
    payload: dict = {
        "table_id": session.table_id,
        "status": session.status,
        "max_seats": session.max_seats,
        "seated_players": list(session.player_ids),
        "last_hand": (
            _serialize_hand_result(
                session.last_hand_result, session.last_completed_hand, viewer_player_id
            )
            if session.last_hand_result is not None
            else None
        ),
    }

    t = session.tournament
    if t is None:
        return payload

    payload["stacks"] = dict(t.stacks)
    hand = _current_hand(session)
    if hand is None:
        payload["hand"] = None
        return payload

    players_view = []
    for p in hand.player_states:
        is_viewer = viewer_player_id is not None and p.player_id == viewer_player_id
        revealed_at_showdown = hand.is_complete and p.player_id in hand.result.revealed_hands
        show_cards = is_viewer or revealed_at_showdown
        players_view.append({
            "player_id": p.player_id,
            "stack": p.stack,
            "folded": p.folded,
            "all_in": p.all_in,
            "hole_card_count": len(p.hole_cards),
            "hole_cards": [str(c) for c in p.hole_cards] if show_cards else None,
        })

    legal_actions: List[str] = []
    if viewer_player_id and not hand.is_complete and viewer_player_id == hand.current_actor_id:
        legal_actions = [a.name for a in hand.legal_actions(viewer_player_id)]

    payload["hand"] = {
        "small_blind": hand.small_blind,
        "big_blind": hand.big_blind,
        "community_cards": [str(c) for c in hand.community_cards],
        "players": players_view,
        "current_actor": hand.current_actor_id,
        "legal_actions": legal_actions,
        "is_complete": hand.is_complete,
        "payouts": hand.result.payouts if hand.is_complete else None,
    }
    return payload


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/guest")
def create_guest(payload: GuestCreateRequest) -> dict:
    player_id = uuid.uuid4().hex[:12]
    display_name = payload.display_name or f"Guest-{player_id[:4]}"
    GUESTS[player_id] = display_name
    return {"player_id": player_id, "display_name": display_name}


@app.post("/tables")
def create_table(payload: CreateTableRequest) -> dict:
    if payload.max_seats < 2:
        raise HTTPException(400, "max_seats must be at least 2")
    table_id = uuid.uuid4().hex[:8]
    TABLES[table_id] = TableSession(
        table_id=table_id,
        max_seats=payload.max_seats,
        starting_stack=payload.starting_stack,
    )
    return {"table_id": table_id, "max_seats": payload.max_seats, "starting_stack": payload.starting_stack}


@app.post("/tables/{table_id}/join")
def join_table(table_id: str, payload: JoinTableRequest) -> dict:
    session = _get_table(table_id)
    if payload.player_id not in GUESTS:
        raise HTTPException(404, "Unknown player_id -- create a guest session first via POST /guest")
    if session.status != "waiting":
        raise HTTPException(400, "Table is no longer accepting new players")
    if payload.player_id in session.player_ids:
        raise HTTPException(400, "Already joined this table")
    if len(session.player_ids) >= session.max_seats:
        raise HTTPException(400, "Table is full")

    session.player_ids.append(payload.player_id)
    return {"table_id": table_id, "seated_players": len(session.player_ids), "max_seats": session.max_seats}


@app.post("/tables/{table_id}/start")
def start_table(table_id: str) -> dict:
    session = _get_table(table_id)
    if session.status != "waiting":
        raise HTTPException(400, f"Table is already {session.status}")
    if len(session.player_ids) < 2:
        raise HTTPException(400, "Need at least 2 seated players to start")

    session.tournament = Tournament.create(
        player_ids=list(session.player_ids),
        starting_stack=session.starting_stack,
        max_table_size=session.max_seats,
        blind_schedule=generate_default_schedule(),
    )
    session.status = "in_progress"
    _start_next_hand_if_needed(session)
    return {"table_id": table_id, "status": session.status}


@app.get("/tables/{table_id}/state")
def get_state(table_id: str, player_id: Optional[str] = None) -> dict:
    session = _get_table(table_id)
    return _serialize_state(session, player_id)


@app.post("/tables/{table_id}/actions")
async def apply_action(table_id: str, payload: ActionRequest) -> dict:
    session = _get_table(table_id)
    hand = _current_hand(session)
    if hand is None or hand.is_complete:
        raise HTTPException(400, "No betting decision is currently open at this table")

    try:
        action_type = ActionType[payload.action_type]
    except KeyError:
        raise HTTPException(400, f"Unknown action_type: {payload.action_type!r}")

    try:
        hand.apply_action(payload.player_id, action_type, payload.amount)
    except (OrchestratorError, IllegalActionError, KeyError) as exc:
        raise HTTPException(400, str(exc))

    if hand.is_complete:
        assert session.tournament is not None
        # Capture both the finished hand's result AND the live Hand
        # object itself BEFORE starting the next hand, which immediately
        # overwrites hands_by_table["T1"] -- see the last_hand_result /
        # last_completed_hand field comments on TableSession. Losing the
        # live object (not just its result) is exactly what made
        # /rabbit-hunt unreachable before (HANDOFF.md Bug 3).
        session.last_hand_result = session.tournament.complete_hand(INTERNAL_TABLE_ID)
        session.last_completed_hand = hand
        _start_next_hand_if_needed(session)

    await _broadcast_state(session)
    return _serialize_state(session, payload.player_id)


@app.post("/tables/{table_id}/rabbit-hunt")
async def rabbit_hunt(table_id: str, payload: RabbitHuntRequest) -> dict:
    session = _get_table(table_id)
    # Deliberately NOT _current_hand(session): a rabbit hunt is always
    # about the hand that just finished, never whatever's currently in
    # progress (a new hand is dealt synchronously the moment the old one
    # completes, so _current_hand() would never be the right hand to ask
    # -- see HANDOFF.md Bug 3).
    hand = session.last_completed_hand
    if hand is None:
        raise HTTPException(400, "No hand to rabbit hunt on")

    try:
        river = hand.rabbit_hunt(payload.player_id)
    except OrchestratorError as exc:
        raise HTTPException(400, str(exc))

    # hand.rabbit_hunt() only updates its own (orphaned) HandResult --
    # Tournament.stacks was already snapshotted by complete_hand() before
    # this fee was paid, so without this line the fee would never
    # actually leave the player's real, ongoing tournament bankroll (see
    # HANDOFF.md Bug 4). Note this can only affect hands that haven't
    # been dealt yet: the *next* hand may already be in progress (dealt
    # the instant the rabbit-hunt-eligible hand completed) using the
    # pre-fee stack, same as how a blind post can't retroactively change
    # chips already committed to a hand already under way.
    if session.tournament is not None:
        session.tournament.stacks[payload.player_id] = hand.final_stacks()[payload.player_id]

    await _broadcast_state(session)
    return {"river": [str(c) for c in river], "cost": hand.rabbit_hunts[payload.player_id]}


# ---------------------------------------------------------------------------
# WebSocket: live push channel, same state shape as GET /state
# ---------------------------------------------------------------------------

@app.websocket("/ws/tables/{table_id}")
async def table_websocket(websocket: WebSocket, table_id: str, player_id: Optional[str] = None) -> None:
    await websocket.accept()
    session = TABLES.get(table_id)
    if session is None:
        await websocket.send_json({"type": "error", "message": f"No such table: {table_id}"})
        await websocket.close()
        return

    session.connections[websocket] = player_id
    await websocket.send_json({"type": "state", **_serialize_state(session, player_id)})

    try:
        while True:
            msg = await websocket.receive_json()
            await _handle_ws_message(session, player_id, msg)
    except WebSocketDisconnect:
        pass
    finally:
        session.connections.pop(websocket, None)


async def _handle_ws_message(session: TableSession, player_id: Optional[str], msg: dict) -> None:
    msg_type = msg.get("type")
    hand = _current_hand(session)

    try:
        if msg_type == "action":
            if player_id is None:
                raise OrchestratorError("Connect with ?player_id=... to take actions")
            if hand is None or hand.is_complete:
                raise OrchestratorError("No betting decision is currently open")
            action_type = ActionType[msg["action_type"]]
            amount = int(msg.get("amount", 0))
            hand.apply_action(player_id, action_type, amount)
            if hand.is_complete:
                assert session.tournament is not None
                session.last_hand_result = session.tournament.complete_hand(INTERNAL_TABLE_ID)
                session.last_completed_hand = hand
                _start_next_hand_if_needed(session)
        elif msg_type == "rabbit_hunt":
            if player_id is None:
                raise OrchestratorError("Connect with ?player_id=... to rabbit hunt")
            completed_hand = session.last_completed_hand
            if completed_hand is None:
                raise OrchestratorError("No hand to rabbit hunt on")
            completed_hand.rabbit_hunt(player_id)
            if session.tournament is not None:
                session.tournament.stacks[player_id] = completed_hand.final_stacks()[player_id]
        else:
            raise OrchestratorError(f"Unknown message type: {msg_type!r}")
    except (OrchestratorError, IllegalActionError, KeyError) as exc:
        await _send_to_player(session, player_id, {"type": "error", "message": str(exc)})
        return

    await _broadcast_state(session)


async def _broadcast_state(session: TableSession) -> None:
    dead: List[WebSocket] = []
    for ws, viewer in list(session.connections.items()):
        try:
            await ws.send_json({"type": "state", **_serialize_state(session, viewer)})
        except Exception:
            dead.append(ws)
    for ws in dead:
        session.connections.pop(ws, None)


async def _send_to_player(session: TableSession, player_id: Optional[str], message: dict) -> None:
    for ws, viewer in list(session.connections.items()):
        if viewer == player_id:
            try:
                await ws.send_json(message)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Static demo client -- served at /app so it doesn't collide with the API
# routes above. This is a minimal placeholder client to prove the API and
# get *something* clickable live; forking a real poker client (e.g. the
# PokerTH web client per the tech plan) remains the recommended path for a
# polished v1 -- see HANDOFF.md.
# ---------------------------------------------------------------------------

from pathlib import Path

from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles


@app.get("/app", include_in_schema=False)
async def _redirect_app_to_index() -> RedirectResponse:
    """
    Explicit, relative redirect for the no-trailing-slash form of the
    demo client's URL (see HANDOFF.md Bug 1).

    Without this route, Starlette's StaticFiles mount handles the
    trailing-slash redirect itself, and builds that redirect from the
    server's own view of its scheme/host. Behind a reverse proxy that
    doesn't forward the original Host (e.g. Codespaces' port-forwarding
    proxy), that resolves to `localhost`, and the browser -- correctly,
    since it isn't inside the container -- refuses to follow it.

    Registering this route ahead of the mount below makes it take
    priority for the exact "/app" path. Returning a path-only Location
    header ("/app/", no scheme or host) sidesteps the host-detection
    problem entirely: the browser resolves a relative redirect against
    whatever origin it's actually talking to, regardless of what the
    server behind the proxy thinks its own address is.
    """
    return RedirectResponse(url="/app/")


_static_dir = Path(__file__).parent / "static"
if _static_dir.is_dir():
    app.mount("/app", StaticFiles(directory=str(_static_dir), html=True), name="static")
