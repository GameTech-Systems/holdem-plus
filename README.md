# Hold'em Plus — Demo Backend

A fake-money Hold'em Plus engine and API, built to be forked into a GitHub
demo that online poker rooms and casinos can try and evaluate. See
`Hold_em_Plus___Technology_Development_Plan.md` for the full product plan
and `HANDOFF.md` for exactly where this stands and what's next.

## What's here

```
poker_types.py              Card/HandCategory/HandRank primitives
hand_evaluator.py           best-5-of-8 hand evaluator
betting_state_machine.py    per-street betting rounds + the full Hold'em
                             Plus dealing sequence (HandFlow)
side_pots.py                uncalled-bet refund + multi-way side pots
tournament_structure.py     blind schedule/clock + payout structures
tournament_balancing.py     multi-table seating, elimination, breaking
orchestrator.py             Hand + Tournament -- wires all of the above
                             behind two classes, plus Rabbit Runner
api.py                      REST + WebSocket layer over the orchestrator
example_usage.py            runnable script showing the orchestrator API
test_*.py                   163 tests, pytest
requirements.txt            fastapi / uvicorn / pydantic / pytest / httpx
Dockerfile, .dockerignore   container image (Fly.io / Railway / Render-Docker)
render.yaml                 Render Blueprint (native Python runtime)
fly.toml                    Fly.io app config
Procfile                    Railway start command
DEPLOYMENT.md                step-by-step deploy instructions for all three
```

Every module above the API layer is dependency-free standard-library
Python. All 163 tests pass as of this handoff (154 original + 9 added
while fixing the four bugs described in `HANDOFF.md`).

## Running it

```bash
pip install -r requirements.txt
pytest -q                        # 163 passed
python3 example_usage.py         # orchestrator demo, no network
uvicorn api:app --reload         # real server on http://127.0.0.1:8000
```

With the server running, interactive API docs are at
`http://127.0.0.1:8000/docs` (FastAPI's built-in Swagger UI) --
useful for poking at endpoints by hand before wiring up a frontend.

To put this on a real, shareable URL instead of just running it locally,
see `DEPLOYMENT.md`.

## Quick manual walkthrough

```bash
# two guests
curl -s -X POST localhost:8000/guest -d '{"display_name":"Alice"}' -H 'Content-Type: application/json'
curl -s -X POST localhost:8000/guest -d '{"display_name":"Bob"}'   -H 'Content-Type: application/json'

# a table, both join, start it
curl -s -X POST localhost:8000/tables -d '{"max_seats":6,"starting_stack":40}' -H 'Content-Type: application/json'
curl -s -X POST localhost:8000/tables/<table_id>/join -d '{"player_id":"<alice_id>"}' -H 'Content-Type: application/json'
curl -s -X POST localhost:8000/tables/<table_id>/join -d '{"player_id":"<bob_id>"}'   -H 'Content-Type: application/json'
curl -s -X POST localhost:8000/tables/<table_id>/start

# poll state (as Alice, so her own hole cards are visible to her)
curl -s "localhost:8000/tables/<table_id>/state?player_id=<alice_id>"

# take an action
curl -s -X POST localhost:8000/tables/<table_id>/actions \
  -d '{"player_id":"<alice_id>","action_type":"CALL"}' -H 'Content-Type: application/json'
```

Or connect a WebSocket to `ws://localhost:8000/ws/tables/<table_id>?player_id=<id>`
for live push updates instead of polling `/state`.

## Known scope limits (see HANDOFF.md for the full list)

This is a single-process, in-memory, single-table-per-game demo backend.
No database, no auth beyond an opaque guest id, no frontend. It's built
to be the backend a forked PokerTH web client (or any other client) talks
to next.
