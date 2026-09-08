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

import time

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
# Rabbit hunt over REST (see also HANDOFF.md Bug 3 and Bug 4)
# ---------------------------------------------------------------------------

def _play_heads_up_to_turn_fold(table_id: str) -> str:
    """
    Drives a fresh heads-up hand from deal through checks/calls to the
    turn betting street, then folds whoever is left to act -- ending the
    hand immediately and making that player rabbit-hunt eligible.
    Returns the folding player's id. Always reads current_actor from
    state rather than assuming a fixed seat order, since Tournament.create
    shuffles seating.
    """
    def act_current(preferred: str = None) -> str:
        state = client.get(f"/tables/{table_id}/state").json()
        actor = state["hand"]["current_actor"]
        actor_view = client.get(f"/tables/{table_id}/state", params={"player_id": actor}).json()
        legal = actor_view["hand"]["legal_actions"]
        action_type = preferred if preferred and preferred in legal else (
            "CHECK" if "CHECK" in legal else "CALL"
        )
        resp = client.post(f"/tables/{table_id}/actions", json={"player_id": actor, "action_type": action_type})
        assert resp.status_code == 200
        return actor

    act_current()  # preflop: first actor calls (can't check, owes the blind)
    act_current()  # preflop: closes
    act_current()  # flop betting: check
    act_current()  # flop betting: closes -> turn

    state = client.get(f"/tables/{table_id}/state").json()
    folder = state["hand"]["current_actor"]
    resp = client.post(f"/tables/{table_id}/actions", json={"player_id": folder, "action_type": "FOLD"})
    assert resp.status_code == 200
    return folder


def test_rabbit_hunt_succeeds_via_api_immediately_after_eligible_fold():
    """
    Regression test for HANDOFF.md Bug 3: the very first rabbit-hunt
    attempt right after a legitimately-eligible turn fold must succeed,
    not 400 -- even though the API has already auto-dealt a brand new
    hand by the time this request arrives, same as every other response.
    Before the fix, the endpoint looked up _current_hand(session) (the
    NEW hand, always incomplete) instead of the hand that actually just
    finished, so this failed unconditionally, on every single hand,
    regardless of timing.
    """
    table_id = make_table(max_seats=2, starting_stack=1000)
    p0, p1 = make_guest(), make_guest()
    join(table_id, p0)
    join(table_id, p1)
    client.post(f"/tables/{table_id}/start")

    folder = _play_heads_up_to_turn_fold(table_id)

    resp = client.post(f"/tables/{table_id}/rabbit-hunt", json={"player_id": folder})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["river"]) == 1
    assert body["cost"] > 0


def test_rabbit_hunt_fee_is_reflected_in_ongoing_tournament_stack():
    """
    Regression test for HANDOFF.md Bug 4: paying for a rabbit hunt must
    actually leave the player's real, ongoing tournament stack (the one
    future hands are dealt from), not just an orphaned HandResult that
    nothing reads again. Before the fix this fee was silently free.
    """
    table_id = make_table(max_seats=2, starting_stack=1000)
    p0, p1 = make_guest(), make_guest()
    join(table_id, p0)
    join(table_id, p1)
    client.post(f"/tables/{table_id}/start")

    folder = _play_heads_up_to_turn_fold(table_id)
    stack_before = client.get(f"/tables/{table_id}/state").json()["stacks"][folder]

    resp = client.post(f"/tables/{table_id}/rabbit-hunt", json={"player_id": folder})
    cost = resp.json()["cost"]
    assert cost > 0

    stack_after = client.get(f"/tables/{table_id}/state").json()["stacks"][folder]
    assert stack_before - stack_after == cost


def test_last_hand_rabbit_hunt_eligible_is_scoped_to_the_right_player():
    """
    rabbit_hunt_eligible must be computed per-viewer against the hand
    that actually just finished -- the folder sees True, the winner
    (who has nothing to rabbit hunt) sees False. This flag previously
    lived on the *live* hand payload and was checked against whatever
    hand was currently in progress, which -- per Bug 3 -- is never the
    hand this question is actually about, so it was always False for
    everyone regardless of who was asking.
    """
    table_id = make_table(max_seats=2, starting_stack=1000)
    p0, p1 = make_guest(), make_guest()
    join(table_id, p0)
    join(table_id, p1)
    client.post(f"/tables/{table_id}/start")

    folder = _play_heads_up_to_turn_fold(table_id)
    winner = p1 if folder == p0 else p0

    folder_view = client.get(f"/tables/{table_id}/state", params={"player_id": folder}).json()
    winner_view = client.get(f"/tables/{table_id}/state", params={"player_id": winner}).json()

    assert folder_view["last_hand"]["rabbit_hunt_eligible"] is True
    assert winner_view["last_hand"]["rabbit_hunt_eligible"] is False


def test_rabbit_hunt_via_api_still_rejects_second_attempt():
    table_id = make_table(max_seats=2, starting_stack=1000)
    p0, p1 = make_guest(), make_guest()
    join(table_id, p0)
    join(table_id, p1)
    client.post(f"/tables/{table_id}/start")

    folder = _play_heads_up_to_turn_fold(table_id)
    first = client.post(f"/tables/{table_id}/rabbit-hunt", json={"player_id": folder})
    assert first.status_code == 200
    second = client.post(f"/tables/{table_id}/rabbit-hunt", json={"player_id": folder})
    assert second.status_code == 400


def test_rabbit_hunt_over_websocket_also_works_and_updates_stacks():
    table_id = make_table(max_seats=2, starting_stack=1000)
    p0, p1 = make_guest(), make_guest()
    join(table_id, p0)
    join(table_id, p1)
    client.post(f"/tables/{table_id}/start")

    folder = _play_heads_up_to_turn_fold(table_id)
    stack_before = client.get(f"/tables/{table_id}/state").json()["stacks"][folder]

    with client.websocket_connect(f"/ws/tables/{table_id}?player_id={folder}") as ws:
        ws.receive_json()  # initial state on connect
        ws.send_json({"type": "rabbit_hunt"})
        update = ws.receive_json()
        assert update["type"] == "state"

    stack_after = client.get(f"/tables/{table_id}/state").json()["stacks"][folder]
    assert stack_after < stack_before


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


# ---------------------------------------------------------------------------
# Blind-clock real-time sync (see HANDOFF.md's "blind clock never
# advances" finding from this session's audit pass)
#
# Every module involved here (BlindClock, Tournament.advance_clock) was
# already fully unit-tested and correct in isolation. The bug was that
# nothing in api.py ever called advance_clock() at all, so a table run
# through the live API sat at blind level 1 forever regardless of real
# elapsed time or hands played. These tests exercise the fix
# (_sync_tournament_clock in api.py) without needing to actually sleep,
# by backdating TableSession.started_at -- the same in-memory-dict
# access pattern test_app_redirect_is_relative_not_host_aware already
# uses to reach api.py's internals directly.
# ---------------------------------------------------------------------------

from api import TABLES  # noqa: E402  (see comment above -- deliberate direct access)


def _check_or_call_current_actor(table_id: str) -> dict:
    state = client.get(f"/tables/{table_id}/state").json()
    actor = state["hand"]["current_actor"]
    actor_state = client.get(f"/tables/{table_id}/state", params={"player_id": actor}).json()
    legal = actor_state["hand"]["legal_actions"]
    action_type = "CHECK" if "CHECK" in legal else "CALL"
    resp = client.post(f"/tables/{table_id}/actions", json={"player_id": actor, "action_type": action_type})
    assert resp.status_code == 200
    return resp.json()


def test_blinds_never_escalate_without_the_clock_sync_bug_reproduced():
    """
    Documents the bug this session found and fixed: with no time
    manipulation at all, playing hands back to back keeps blinds pinned
    at level 1 for as long as this test cares to check, confirming the
    fix below is actually necessary and not testing a no-op.
    """
    table_id = make_table(max_seats=2, starting_stack=1000)
    p0, p1 = make_guest(), make_guest()
    join(table_id, p0)
    join(table_id, p1)
    client.post(f"/tables/{table_id}/start")

    for _ in range(10):
        state = client.get(f"/tables/{table_id}/state").json()
        if state["hand"] is None:
            break
        assert (state["hand"]["small_blind"], state["hand"]["big_blind"]) == (1, 2)
        _check_or_call_current_actor(table_id)


def test_backdating_table_start_advances_blinds_on_the_next_hand():
    """
    Regression test for the fix: simulating 20 minutes of real elapsed
    time (by backdating started_at, no actual sleeping) must be reflected
    in the blind level of the next hand dealt -- the default schedule's
    level 1 runs 0-900s and level 2 runs 900-1800s, so 1200s elapsed
    should land on level 2 (2/4).
    """
    table_id = make_table(max_seats=2, starting_stack=1000)
    p0, p1 = make_guest(), make_guest()
    join(table_id, p0)
    join(table_id, p1)
    client.post(f"/tables/{table_id}/start")

    session = TABLES[table_id]
    session.started_at = time.time() - 1200

    # Finish the in-progress hand (dealt before the backdate) so the
    # *next* hand -- the one that actually reads the now-caught-up
    # clock -- gets dealt.
    for _ in range(20):
        resp_body = _check_or_call_current_actor(table_id)
        if resp_body.get("last_hand") is not None:
            break

    final_state = client.get(f"/tables/{table_id}/state").json()
    if final_state["hand"] is not None:  # tournament may have ended heads-up
        assert (final_state["hand"]["small_blind"], final_state["hand"]["big_blind"]) == (2, 4)


# ---------------------------------------------------------------------------
# Analytics endpoint (see analytics.py)
# ---------------------------------------------------------------------------

def test_analytics_endpoint_before_any_hand_completes():
    table_id = make_table(max_seats=2, starting_stack=1000)
    p0, p1 = make_guest(), make_guest()
    join(table_id, p0)
    join(table_id, p1)
    client.post(f"/tables/{table_id}/start")

    summary = client.get(f"/tables/{table_id}/analytics").json()
    assert summary["hands_recorded"] == 0
    assert summary["showdown_frequency"] is None
    assert summary["category_distribution"] == {}
    # the standard-Hold'em baseline is process-wide, not table-specific,
    # so it's populated even before this table has played a single hand
    assert sum(summary["standard_holdem_baseline"].values()) == pytest.approx(1.0, abs=1e-6)


def test_analytics_endpoint_reflects_completed_hands():
    table_id = make_table(max_seats=2, starting_stack=1000)
    p0, p1 = make_guest(), make_guest()
    join(table_id, p0)
    join(table_id, p1)
    client.post(f"/tables/{table_id}/start")

    _play_to_first_hand_completion(table_id)

    summary = client.get(f"/tables/{table_id}/analytics").json()
    assert summary["hands_recorded"] == 1
    assert summary["average_pot_in_big_blinds"] > 0
    assert summary["showdown_frequency"] in (0.0, 1.0)  # exactly one hand recorded so far


def test_analytics_endpoint_unknown_table_returns_404():
    resp = client.get("/tables/does-not-exist/analytics")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Feedback endpoint (player-reported excitement)
# ---------------------------------------------------------------------------

def test_feedback_requires_a_real_guest_id():
    table_id = make_table()
    resp = client.post(f"/tables/{table_id}/feedback", json={"player_id": "not-a-guest", "thumbs_up": True})
    assert resp.status_code == 404


def test_feedback_is_reflected_in_analytics_summary():
    table_id = make_table(max_seats=2, starting_stack=1000)
    p0, p1 = make_guest(), make_guest()
    join(table_id, p0)
    join(table_id, p1)
    client.post(f"/tables/{table_id}/start")

    resp = client.post(f"/tables/{table_id}/feedback", json={"player_id": p0, "thumbs_up": True})
    assert resp.status_code == 200
    client.post(f"/tables/{table_id}/feedback", json={"player_id": p1, "thumbs_up": False})

    summary = client.get(f"/tables/{table_id}/analytics").json()
    assert summary["player_feedback"] == {"thumbs_up": 1, "thumbs_down": 1}


# ---------------------------------------------------------------------------
# Audit-testing pass: multi-way all-ins through to real showdown, and
# folds at every street -- the specific bug classes HANDOFF.md's
# "fastest path forward" called out for the next audit pass, exercised
# here through the actual API surface (not just Hand/Tournament objects
# directly, which test_orchestrator.py already covers) since that's
# where the clock bug above was actually hiding.
# ---------------------------------------------------------------------------

def _act_with_policy(table_id: str, actor: str) -> dict:
    """Reference policy driven entirely through the API's own legal_actions,
    mirroring orchestrator.default_bot_action but over HTTP: check if
    free, else call, else shove, else fold."""
    actor_state = client.get(f"/tables/{table_id}/state", params={"player_id": actor}).json()
    legal = actor_state["hand"]["legal_actions"]
    if "CHECK" in legal:
        action_type = "CHECK"
    elif "CALL" in legal:
        action_type = "CALL"
    elif "ALL_IN" in legal:
        action_type = "ALL_IN"
    else:
        action_type = "FOLD"
    resp = client.post(f"/tables/{table_id}/actions", json={"player_id": actor, "action_type": action_type})
    assert resp.status_code == 200
    return resp.json()


def test_three_handed_shallow_stacks_reach_multiway_all_ins_via_api_with_chips_conserved():
    """
    Shallow starting stacks (5 big blinds) with a check/call/shove/fold
    policy reliably produces multi-way all-ins and side pots within a
    handful of hands, purely through blind pressure -- no rigged deck
    needed, since this only asserts the chip-conservation invariant and
    that the tournament reaches completion without an unhandled
    exception, not any specific hand outcome. This is the API-level
    analogue of test_orchestrator.py's
    test_multi_hand_bot_simulation_keeps_chips_conserved_and_terminates,
    covering the additional surface (serialization, session bookkeeping,
    analytics recording) that only exists at the api.py layer.
    """
    table_id = make_table(max_seats=3, starting_stack=10)
    guests = [make_guest() for _ in range(3)]
    for g in guests:
        join(table_id, g)
    client.post(f"/tables/{table_id}/start")

    stacks_before = dict(client.get(f"/tables/{table_id}/state").json()["stacks"])
    total_chips = sum(stacks_before.values())

    for _ in range(5000):
        state = client.get(f"/tables/{table_id}/state").json()
        if state["status"] == "complete" or state["hand"] is None:
            break
        actor = state["hand"]["current_actor"]
        if actor is None:
            break
        _act_with_policy(table_id, actor)

    final_state = client.get(f"/tables/{table_id}/state").json()
    assert sum(final_state["stacks"].values()) == total_chips
    assert final_state["status"] == "complete"

    analytics = client.get(f"/tables/{table_id}/analytics").json()
    assert analytics["hands_recorded"] >= 1


def _play_n_clears_then_fold(table_id: str, n_clears: int) -> str:
    """Clears n_clears actions with check/call, then folds whoever acts
    next -- used to force a fold at a specific betting street (0 clears
    = fold preflop immediately, 2 = fold on the flop, 4 = fold on the
    turn, 6 = fold on the river, for a heads-up hand)."""
    for _ in range(n_clears):
        _check_or_call_current_actor(table_id)
    state = client.get(f"/tables/{table_id}/state").json()
    folder = state["hand"]["current_actor"]
    resp = client.post(f"/tables/{table_id}/actions", json={"player_id": folder, "action_type": "FOLD"})
    assert resp.status_code == 200
    return folder


@pytest.mark.parametrize("n_clears", [0, 2, 4, 6])
def test_fold_at_every_street_ends_hand_cleanly_and_conserves_chips(n_clears):
    """
    Folding preflop (0 clears), on the flop (2), on the turn (4), and on
    the river (6) must each end the hand immediately, award the whole
    pot to the remaining player, conserve total chips, and leave the
    table ready for (or having already dealt) a new hand -- one of the
    specific scenario classes flagged for this session's audit pass.
    """
    table_id = make_table(max_seats=2, starting_stack=1000)
    p0, p1 = make_guest(), make_guest()
    join(table_id, p0)
    join(table_id, p1)
    client.post(f"/tables/{table_id}/start")

    stacks_before = dict(client.get(f"/tables/{table_id}/state").json()["stacks"])

    folder = _play_n_clears_then_fold(table_id, n_clears)
    winner = p1 if folder == p0 else p0

    final = client.get(f"/tables/{table_id}/state").json()
    assert sum(final["stacks"].values()) == sum(stacks_before.values())
    assert final["last_hand"]["is_complete"] is True
    assert final["last_hand"]["payouts"].get(winner, 0) > 0
    assert folder not in final["last_hand"]["payouts"]
    assert folder in final["last_hand"]["folded_players"]
    # folding players are never added to revealed_hands (see orchestrator.Hand._finalize)
    assert folder not in final["last_hand"]["revealed_hands"]
    # the table must be ready for more play, not stuck
    assert final["status"] in ("in_progress", "complete")


# ---------------------------------------------------------------------------
# Demo script endpoint (see demo_showcase.py)
#
# This is the fix for the "rabbit runner doesn't seem to show up in the
# live demo" report: the feature was never actually missing from
# static/index.html, it's just gated behind a turn/river fold, which the
# reference bot policy (default_bot_action) essentially never triggers on
# its own -- so a visitor clicking through a bot-filled or organically
# played table could go a long time without ever seeing it. These tests
# cover the endpoint surface; demo_showcase.py's own test file
# (test_demo_showcase.py) covers the scripted poker logic itself.
# ---------------------------------------------------------------------------

def test_demo_script_endpoint_returns_both_showcase_hands_in_order():
    resp = client.get("/demo/script")
    assert resp.status_code == 200
    hands = resp.json()["hands"]
    assert [h["title"] for h in hands] == ["The Extra Card", "Rabbit Runner"]


def test_demo_script_endpoint_stands_entirely_on_its_own():
    """No /guest, /tables, or /join call anywhere above this test -- the
    demo script must not require any table/session state to exist."""
    resp = client.get("/demo/script")
    assert resp.status_code == 200


def test_demo_script_hands_include_a_rabbit_hunt_reveal():
    resp = client.get("/demo/script")
    hands = resp.json()["hands"]
    rabbit_hand = next(h for h in hands if h["title"] == "Rabbit Runner")
    reveal_events = [e for e in rabbit_hand["events"] if e["kind"] == "rabbit_hunt"]
    assert len(reveal_events) == 1
    assert reveal_events[0]["revealed_card"] is not None


def test_demo_script_is_stable_across_repeated_requests():
    first = client.get("/demo/script").json()
    second = client.get("/demo/script").json()
    assert first == second


# ---------------------------------------------------------------------------
# Hand history (see api.HandHistoryEntry's docstring)
#
# Regression coverage for the specific report this feature answers: a
# table's first hand plays out, then its info "goes away" the moment the
# second hand starts. That's `last_hand` behaving exactly as documented
# (it only ever describes the single most-recently-finished hand) -- the
# fix isn't a change to `last_hand`, it's this separate, persistent log.
# ---------------------------------------------------------------------------

def _play_until_hands_completed(table_id: str, target: int, max_actions: int = 400) -> None:
    """
    Checks/calls every actor's turn until at least `target` hands have
    finished at this table (or the tournament ends first).

    Deliberately keys off state["hands_completed"] rather than watching
    for `last_hand` to change: `last_hand` stays non-None on every single
    poll after the very first hand completes (see
    test_last_hand_persists_on_subsequent_polls_until_next_hand_finishes
    above), so "it's not None" can't distinguish "a new hand just
    finished" from "the same already-finished hand is still being
    reported" -- only the count actually incrementing can.
    """
    for _ in range(max_actions):
        state = client.get(f"/tables/{table_id}/state").json()
        if state["hands_completed"] >= target or state["hand"] is None:
            return
        actor = state["hand"]["current_actor"]
        if actor is None:
            return
        actor_state = client.get(f"/tables/{table_id}/state", params={"player_id": actor}).json()
        legal_actions = actor_state["hand"]["legal_actions"]
        action_type = "CHECK" if "CHECK" in legal_actions else "CALL"
        resp = client.post(f"/tables/{table_id}/actions", json={"player_id": actor, "action_type": action_type})
        assert resp.status_code == 200
    raise AssertionError(f"did not reach {target} completed hands within {max_actions} actions")


def test_hand_history_empty_before_any_hand_completes():
    table_id = make_table(max_seats=2, starting_stack=1000)
    p0, p1 = make_guest(), make_guest()
    join(table_id, p0)
    join(table_id, p1)
    client.post(f"/tables/{table_id}/start")

    assert client.get(f"/tables/{table_id}/hands").json() == {"hands": [], "total_hands_played": 0}


def test_hand_history_available_even_before_table_is_started():
    """A table that exists but hasn't started yet has played zero hands --
    that's a valid, error-free answer, not a 400/404."""
    table_id = make_table()
    resp = client.get(f"/tables/{table_id}/hands")
    assert resp.status_code == 200
    assert resp.json() == {"hands": [], "total_hands_played": 0}


def test_hand_history_unknown_table_returns_404():
    resp = client.get("/tables/does-not-exist/hands")
    assert resp.status_code == 404


def test_state_reports_hands_completed_count():
    table_id = make_table(max_seats=2, starting_stack=1000)
    p0, p1 = make_guest(), make_guest()
    join(table_id, p0)
    join(table_id, p1)
    client.post(f"/tables/{table_id}/start")

    assert client.get(f"/tables/{table_id}/state").json()["hands_completed"] == 0
    _play_to_first_hand_completion(table_id)
    assert client.get(f"/tables/{table_id}/state").json()["hands_completed"] == 1


def test_hand_history_records_every_hand_not_just_the_last_one():
    """
    The specific gap this feature closes: after 3 hands, `last_hand` only
    ever reflects hand 3 -- but /hands must still show all of 1, 2, and 3,
    proving earlier hands' info didn't disappear once later ones finished.
    """
    table_id = make_table(max_seats=2, starting_stack=1000)
    p0, p1 = make_guest(), make_guest()
    join(table_id, p0)
    join(table_id, p1)
    client.post(f"/tables/{table_id}/start")

    _play_until_hands_completed(table_id, 3)

    history = client.get(f"/tables/{table_id}/hands").json()
    assert history["total_hands_played"] == 3
    assert [h["hand_number"] for h in history["hands"]] == [3, 2, 1]  # most recent first


def test_hand_history_entry_has_board_payouts_and_no_rabbit_hunt_by_default():
    table_id = make_table(max_seats=2, starting_stack=1000)
    p0, p1 = make_guest(), make_guest()
    join(table_id, p0)
    join(table_id, p1)
    client.post(f"/tables/{table_id}/start")

    _play_to_first_hand_completion(table_id)

    entry = client.get(f"/tables/{table_id}/hands").json()["hands"][0]
    assert entry["hand_number"] == 1
    assert entry["small_blind"] == 1 and entry["big_blind"] == 2
    assert len(entry["community_cards"]) == 5  # checked all the way down
    assert sum(entry["payouts"].values()) > 0
    assert entry["rabbit_hunt"] is None


def test_hand_history_records_a_fold_without_showdown_correctly():
    table_id = make_table(max_seats=2, starting_stack=1000)
    p0, p1 = make_guest(), make_guest()
    join(table_id, p0)
    join(table_id, p1)
    client.post(f"/tables/{table_id}/start")

    state = client.get(f"/tables/{table_id}/state").json()
    folder = state["hand"]["current_actor"]
    winner = p1 if folder == p0 else p0
    client.post(f"/tables/{table_id}/actions", json={"player_id": folder, "action_type": "FOLD"})

    entry = client.get(f"/tables/{table_id}/hands").json()["hands"][0]
    assert entry["folded_players"] == [folder]
    assert entry["revealed_hands"] == {}  # nobody went to showdown
    assert entry["payouts"].get(winner, 0) > 0


def test_hand_history_limit_param_restricts_and_keeps_recency_order():
    table_id = make_table(max_seats=2, starting_stack=1000)
    p0, p1 = make_guest(), make_guest()
    join(table_id, p0)
    join(table_id, p1)
    client.post(f"/tables/{table_id}/start")

    _play_until_hands_completed(table_id, 4)

    limited = client.get(f"/tables/{table_id}/hands", params={"limit": 2}).json()
    assert [h["hand_number"] for h in limited["hands"]] == [4, 3]
    assert limited["total_hands_played"] == 4  # true count, independent of limit


def test_hand_history_rejects_non_positive_limit():
    table_id = make_table(max_seats=2, starting_stack=1000)
    p0, p1 = make_guest(), make_guest()
    join(table_id, p0)
    join(table_id, p1)
    client.post(f"/tables/{table_id}/start")

    resp = client.get(f"/tables/{table_id}/hands", params={"limit": 0})
    assert resp.status_code == 400


def test_hand_history_reflects_rabbit_hunt_once_used_via_rest():
    table_id = make_table(max_seats=2, starting_stack=1000)
    p0, p1 = make_guest(), make_guest()
    join(table_id, p0)
    join(table_id, p1)
    client.post(f"/tables/{table_id}/start")

    folder = _play_heads_up_to_turn_fold(table_id)
    rh = client.post(f"/tables/{table_id}/rabbit-hunt", json={"player_id": folder}).json()

    entry = client.get(f"/tables/{table_id}/hands").json()["hands"][0]
    assert entry["rabbit_hunt"] == {"player_id": folder, "river": rh["river"], "cost": rh["cost"]}


def test_hand_history_reflects_rabbit_hunt_used_over_websocket():
    table_id = make_table(max_seats=2, starting_stack=1000)
    p0, p1 = make_guest(), make_guest()
    join(table_id, p0)
    join(table_id, p1)
    client.post(f"/tables/{table_id}/start")

    folder = _play_heads_up_to_turn_fold(table_id)
    with client.websocket_connect(f"/ws/tables/{table_id}?player_id={folder}") as ws:
        ws.receive_json()  # initial state on connect
        ws.send_json({"type": "rabbit_hunt"})
        ws.receive_json()

    entry = client.get(f"/tables/{table_id}/hands").json()["hands"][0]
    assert entry["rabbit_hunt"] is not None
    assert entry["rabbit_hunt"]["player_id"] == folder


def test_hand_history_storage_is_capped_but_lifetime_count_is_not(monkeypatch):
    """
    MAX_HAND_HISTORY bounds how many entries are *retained*, but
    hands_completed (and therefore hand_number) is a true lifetime
    counter that keeps incrementing regardless -- hand numbering never
    resets or repeats just because earlier entries aged out of storage.
    """
    import api as api_module
    monkeypatch.setattr(api_module, "MAX_HAND_HISTORY", 2)

    table_id = make_table(max_seats=2, starting_stack=1000)
    p0, p1 = make_guest(), make_guest()
    join(table_id, p0)
    join(table_id, p1)
    client.post(f"/tables/{table_id}/start")

    _play_until_hands_completed(table_id, 5)

    history = client.get(f"/tables/{table_id}/hands").json()
    assert history["total_hands_played"] == 5
    assert len(history["hands"]) == 2
    assert [h["hand_number"] for h in history["hands"]] == [5, 4]
