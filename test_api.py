"""
Tests for api.py.

Uses FastAPI's TestClient (in-process ASGI, no real sockets/ports) for
both REST calls and the WebSocket endpoint.

Run with: pytest -v test_api.py

Note: TABLES/GUESTS are module-level dicts in api.py, so each test
creates its own fresh table/guests via the API itself rather than
relying on isolation between tests -- this mirrors how the real service
behaves (state persists for the life of the process) and avoids needing
a fixture that reaches into api.py's internals to reset it.
"""

import pytest
from fastapi.testclient import TestClient

from api import app

client = TestClient(app)


def make_guest(name: str = "") -> str:
    resp = client.post("/guest", json={"display_name": name} if name else {})
    assert resp.status_code == 200
    return resp.json()["player_id"]


def make_table(max_seats: int = 10, starting_stack: int = 40) -> str:
    resp = client.post("/tables", json={"max_seats": max_seats, "starting_stack": starting_stack})
    assert resp.status_code == 200
    return resp.json()["table_id"]


def join(table_id: str, player_id: str) -> None:
    resp = client.post(f"/tables/{table_id}/join", json={"player_id": player_id})
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Basic REST flow
# ---------------------------------------------------------------------------

def test_health_check():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_create_guest_returns_player_id_and_display_name():
    resp = client.post("/guest", json={"display_name": "Alice"})
    assert resp.status_code == 200
    body = resp.json()
    assert "player_id" in body
    assert body["display_name"] == "Alice"


def test_create_guest_without_display_name_gets_a_default():
    resp = client.post("/guest", json={})
    assert resp.status_code == 200
    assert resp.json()["display_name"].startswith("Guest-")


def test_create_table_returns_table_id():
    resp = client.post("/tables", json={"max_seats": 6, "starting_stack": 100})
    assert resp.status_code == 200
    body = resp.json()
    assert "table_id" in body
    assert body["max_seats"] == 6


def test_create_table_rejects_too_few_seats():
    resp = client.post("/tables", json={"max_seats": 1})
    assert resp.status_code == 400


def test_join_requires_a_real_guest_id():
    table_id = make_table()
    resp = client.post(f"/tables/{table_id}/join", json={"player_id": "not-a-real-guest"})
    assert resp.status_code == 404


def test_join_unknown_table_returns_404():
    guest = make_guest()
    resp = client.post("/tables/does-not-exist/join", json={"player_id": guest})
    assert resp.status_code == 404


def test_join_full_table_rejected():
    table_id = make_table(max_seats=2)
    join(table_id, make_guest())
    join(table_id, make_guest())
    resp = client.post(f"/tables/{table_id}/join", json={"player_id": make_guest()})
    assert resp.status_code == 400


def test_start_requires_at_least_two_players():
    table_id = make_table()
    join(table_id, make_guest())
    resp = client.post(f"/tables/{table_id}/start")
    assert resp.status_code == 400


def test_start_deals_a_hand_and_state_reflects_blinds():
    table_id = make_table(max_seats=4, starting_stack=40)
    p0, p1 = make_guest(), make_guest()
    join(table_id, p0)
    join(table_id, p1)

    resp = client.post(f"/tables/{table_id}/start")
    assert resp.status_code == 200
    assert resp.json()["status"] == "in_progress"

    state = client.get(f"/tables/{table_id}/state").json()
    assert state["hand"] is not None
    assert state["hand"]["small_blind"] == 1  # default schedule level 1
    assert state["hand"]["big_blind"] == 2


def test_join_after_start_is_rejected():
    table_id = make_table()
    p0, p1 = make_guest(), make_guest()
    join(table_id, p0)
    join(table_id, p1)
    client.post(f"/tables/{table_id}/start")

    resp = client.post(f"/tables/{table_id}/join", json={"player_id": make_guest()})
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# State redaction: hole cards must not leak to other viewers
# ---------------------------------------------------------------------------

def test_hole_cards_hidden_from_other_players_mid_hand():
    table_id = make_table(max_seats=4, starting_stack=1000)
    p0, p1 = make_guest(), make_guest()
    join(table_id, p0)
    join(table_id, p1)
    client.post(f"/tables/{table_id}/start")

    state_for_p0 = client.get(f"/tables/{table_id}/state", params={"player_id": p0}).json()
    own_entry = next(p for p in state_for_p0["hand"]["players"] if p["player_id"] == p0)
    other_entry = next(p for p in state_for_p0["hand"]["players"] if p["player_id"] == p1)

    assert own_entry["hole_cards"] is not None
    assert len(own_entry["hole_cards"]) == 2
    assert other_entry["hole_cards"] is None
    assert other_entry["hole_card_count"] == 2  # count visible, contents aren't


def test_spectator_view_shows_no_hole_cards_at_all():
    table_id = make_table(max_seats=4, starting_stack=1000)
    p0, p1 = make_guest(), make_guest()
    join(table_id, p0)
    join(table_id, p1)
    client.post(f"/tables/{table_id}/start")

    spectator_state = client.get(f"/tables/{table_id}/state").json()  # no player_id param
    assert all(p["hole_cards"] is None for p in spectator_state["hand"]["players"])


def test_only_current_actor_gets_legal_actions_in_their_own_view():
    table_id = make_table(max_seats=4, starting_stack=1000)
    p0, p1 = make_guest(), make_guest()
    join(table_id, p0)
    join(table_id, p1)
    client.post(f"/tables/{table_id}/start")

    state = client.get(f"/tables/{table_id}/state").json()
    current_actor = state["hand"]["current_actor"]
    non_actor = p1 if current_actor == p0 else p0

    actor_state = client.get(f"/tables/{table_id}/state", params={"player_id": current_actor}).json()
    non_actor_state = client.get(f"/tables/{table_id}/state", params={"player_id": non_actor}).json()

    assert len(actor_state["hand"]["legal_actions"]) > 0
    assert non_actor_state["hand"]["legal_actions"] == []


# ---------------------------------------------------------------------------
# Applying actions over REST, all the way to a new hand starting
# ---------------------------------------------------------------------------

def test_full_hand_via_rest_actions_starts_a_new_hand_after():
    table_id = make_table(max_seats=2, starting_stack=1000)
    p0, p1 = make_guest(), make_guest()
    join(table_id, p0)
    join(table_id, p1)
    client.post(f"/tables/{table_id}/start")

    state = client.get(f"/tables/{table_id}/state").json()
    stacks_before = dict(state["stacks"])

    # heads-up: button/SB acts first preflop, then checks around to showdown
    for _ in range(20):
        state = client.get(f"/tables/{table_id}/state").json()
        if state["hand"] is None:
            break
        actor = state["hand"]["current_actor"]
        if actor is None:
            break
        legal = state["hand"]["legal_actions"] if False else None  # (actor's own view needed below)
        actor_state = client.get(f"/tables/{table_id}/state", params={"player_id": actor}).json()
        legal_actions = actor_state["hand"]["legal_actions"]
        action_type = "CHECK" if "CHECK" in legal_actions else "CALL"
        resp = client.post(f"/tables/{table_id}/actions", json={"player_id": actor, "action_type": action_type})
        assert resp.status_code == 200

    final_state = client.get(f"/tables/{table_id}/state").json()
    assert sum(final_state["stacks"].values()) == sum(stacks_before.values())
    # a brand-new hand should already be dealt (or the tournament ended, heads-up
    # elimination is possible depending on RNG -- either is a valid outcome here)
    assert final_state["status"] in ("in_progress", "complete")


def test_action_with_unknown_action_type_returns_400():
    table_id = make_table(max_seats=2, starting_stack=1000)
    p0, p1 = make_guest(), make_guest()
    join(table_id, p0)
    join(table_id, p1)
    client.post(f"/tables/{table_id}/start")

    resp = client.post(
        f"/tables/{table_id}/actions",
        json={"player_id": p0, "action_type": "NOT_A_REAL_ACTION"},
    )
    assert resp.status_code == 400


def test_action_out_of_turn_returns_400():
    table_id = make_table(max_seats=2, starting_stack=1000)
    p0, p1 = make_guest(), make_guest()
    join(table_id, p0)
    join(table_id, p1)
    client.post(f"/tables/{table_id}/start")

    state = client.get(f"/tables/{table_id}/state").json()
    actor = state["hand"]["current_actor"]
    non_actor = p1 if actor == p0 else p0

    resp = client.post(
        f"/tables/{table_id}/actions",
        json={"player_id": non_actor, "action_type": "CHECK"},
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------

def test_websocket_receives_initial_state_on_connect():
    table_id = make_table(max_seats=2, starting_stack=1000)
    p0, p1 = make_guest(), make_guest()
    join(table_id, p0)
    join(table_id, p1)
    client.post(f"/tables/{table_id}/start")

    with client.websocket_connect(f"/ws/tables/{table_id}?player_id={p0}") as ws:
        first_message = ws.receive_json()
        assert first_message["type"] == "state"
        assert first_message["table_id"] == table_id


def test_websocket_action_broadcasts_updated_state_to_both_players():
    table_id = make_table(max_seats=2, starting_stack=1000)
    p0, p1 = make_guest(), make_guest()
    join(table_id, p0)
    join(table_id, p1)
    client.post(f"/tables/{table_id}/start")

    state = client.get(f"/tables/{table_id}/state").json()
    actor = state["hand"]["current_actor"]

    with client.websocket_connect(f"/ws/tables/{table_id}?player_id={p0}") as ws0, \
         client.websocket_connect(f"/ws/tables/{table_id}?player_id={p1}") as ws1:
        ws0.receive_json()  # initial state on connect
        ws1.receive_json()

        actor_ws = ws0 if actor == p0 else ws1
        other_ws = ws1 if actor == p0 else ws0

        actor_state = client.get(f"/tables/{table_id}/state", params={"player_id": actor}).json()
        legal = actor_state["hand"]["legal_actions"]
        action_type = "CHECK" if "CHECK" in legal else "CALL"
        actor_ws.send_json({"type": "action", "action_type": action_type})

        actor_update = actor_ws.receive_json()
        other_update = other_ws.receive_json()
        assert actor_update["type"] == "state"
        assert other_update["type"] == "state"


def test_websocket_rejects_action_without_player_id():
    table_id = make_table(max_seats=2, starting_stack=1000)
    p0, p1 = make_guest(), make_guest()
    join(table_id, p0)
    join(table_id, p1)
    client.post(f"/tables/{table_id}/start")

    with client.websocket_connect(f"/ws/tables/{table_id}") as ws:  # no ?player_id=
        ws.receive_json()  # initial state
        ws.send_json({"type": "action", "action_type": "CHECK"})
        response = ws.receive_json()
        assert response["type"] == "error"


def test_websocket_unknown_table_sends_error_and_closes():
    with client.websocket_connect("/ws/tables/does-not-exist") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "error"


# ---------------------------------------------------------------------------
# Hand-completion summary (see HANDOFF.md Bug 2)
#
# Regression coverage for the sequencing bug where complete_hand() ran,
# then a brand-new hand was started and overwrote hands_by_table["T1"],
# and only *then* was the state serialized -- so the finished hand's
# payouts/is_complete never reached any client. These tests assert the
# finished hand's summary is actually delivered, both in the direct REST
# response to the action that ended the hand and in the WebSocket
# broadcast that follows it.
# ---------------------------------------------------------------------------

def _play_to_first_hand_completion(table_id: str) -> dict:
    """Checks/calls every actor's turn until a hand finishes (or the
    tournament ends), returning the JSON body of the response to the
    single REST action that completed that hand."""
    for _ in range(40):
        state = client.get(f"/tables/{table_id}/state").json()
        if state["hand"] is None:
            raise AssertionError("tournament ended before any hand completed")
        actor = state["hand"]["current_actor"]
        if actor is None:
            raise AssertionError("no current actor but hand not complete")
        actor_state = client.get(f"/tables/{table_id}/state", params={"player_id": actor}).json()
        legal_actions = actor_state["hand"]["legal_actions"]
        action_type = "CHECK" if "CHECK" in legal_actions else "CALL"
        resp = client.post(f"/tables/{table_id}/actions", json={"player_id": actor, "action_type": action_type})
        assert resp.status_code == 200
        body = resp.json()
        if body.get("last_hand") is not None:
            return body
    raise AssertionError("hand never completed within 40 actions")


def test_hand_completion_response_includes_last_hand_payout():
    """
    The response to the specific action that ends a hand must carry that
    hand's payouts and is_complete flag -- not just the state of the
    already-started next hand. This is the test HANDOFF.md's Bug 2
    write-up calls out as missing.
    """
    table_id = make_table(max_seats=2, starting_stack=1000)
    p0, p1 = make_guest(), make_guest()
    join(table_id, p0)
    join(table_id, p1)
    client.post(f"/tables/{table_id}/start")

    body = _play_to_first_hand_completion(table_id)

    last_hand = body["last_hand"]
    assert last_hand is not None
    assert last_hand["is_complete"] is True
    assert sum(last_hand["payouts"].values()) > 0


def test_last_hand_persists_on_subsequent_polls_until_next_hand_finishes():
    """
    A client that misses the exact completing response (e.g. a fresh GET
    or WS reconnect a moment later) should still be able to see what
    happened in the most recently finished hand, not just clients that
    happened to be watching at the exact instant it completed.
    """
    table_id = make_table(max_seats=2, starting_stack=1000)
    p0, p1 = make_guest(), make_guest()
    join(table_id, p0)
    join(table_id, p1)
    client.post(f"/tables/{table_id}/start")

    _play_to_first_hand_completion(table_id)

    polled = client.get(f"/tables/{table_id}/state").json()
    assert polled["last_hand"] is not None
    assert polled["last_hand"]["is_complete"] is True


def test_websocket_broadcast_after_hand_completion_includes_last_hand():
    table_id = make_table(max_seats=2, starting_stack=1000)
    p0, p1 = make_guest(), make_guest()
    join(table_id, p0)
    join(table_id, p1)
    client.post(f"/tables/{table_id}/start")

    with client.websocket_connect(f"/ws/tables/{table_id}?player_id={p0}") as ws0, \
         client.websocket_connect(f"/ws/tables/{table_id}?player_id={p1}") as ws1:
        ws0.receive_json()
        ws1.receive_json()

        seen_last_hand = None
        for _ in range(40):
            state = client.get(f"/tables/{table_id}/state").json()
            if state["hand"] is None:
                break
            actor = state["hand"]["current_actor"]
            if actor is None:
                break
            actor_ws = ws0 if actor == p0 else ws1
            other_ws = ws1 if actor == p0 else ws0
            actor_state = client.get(f"/tables/{table_id}/state", params={"player_id": actor}).json()
            legal = actor_state["hand"]["legal_actions"]
            action_type = "CHECK" if "CHECK" in legal else "CALL"
            actor_ws.send_json({"type": "action", "action_type": action_type})

            actor_update = actor_ws.receive_json()
            other_update = other_ws.receive_json()
            if actor_update.get("last_hand") is not None:
                seen_last_hand = actor_update["last_hand"]
                assert other_update.get("last_hand") is not None
                break

        assert seen_last_hand is not None
        assert seen_last_hand["is_complete"] is True
        assert sum(seen_last_hand["payouts"].values()) > 0


# ---------------------------------------------------------------------------
# /app redirect (see HANDOFF.md Bug 1)
# ---------------------------------------------------------------------------

def test_app_redirect_is_relative_not_host_aware():
    """
    Regression test for the "/app -> localhost:8000" redirect bug:
    requesting the no-trailing-slash form must redirect to a *relative*
    "/app/" (no scheme or host baked in), so it still resolves correctly
    behind a reverse proxy that doesn't forward the original Host (e.g.
    Codespaces' port-forwarding proxy). Using an obviously-non-default
    base_url here means this test would catch a regression to Starlette's
    own host-aware mount redirect, which would bake that host back in.
    """
    proxied_client = TestClient(app, base_url="http://example-public-host.test")
    resp = proxied_client.get("/app", follow_redirects=False)
    assert resp.status_code in (307, 308)
    assert resp.headers["location"] == "/app/"


# ---------------------------------------------------------------------------
# Rabbit hunt over REST
# ---------------------------------------------------------------------------

def test_rabbit_hunt_rest_endpoint_rejects_ineligible_player():
    table_id = make_table(max_seats=2, starting_stack=1000)
    p0, p1 = make_guest(), make_guest()
    join(table_id, p0)
    join(table_id, p1)
    client.post(f"/tables/{table_id}/start")

    # Hand just started -- nobody has folded on the turn/river yet, so
    # rabbit hunt must be rejected regardless of who asks.
    resp = client.post(f"/tables/{table_id}/rabbit-hunt", json={"player_id": p0})
    assert resp.status_code == 400
