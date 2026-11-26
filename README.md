# Hold'em Plus: Demo Backend, Client and Strategy Guide

A play-money Hold'em Plus engine, API, demo table and equity simulation, built to be tried and evaluated by
online poker rooms and casinos. Hold'em Plus is Texas Hold'em with a third hole card dealt after the flop;
showdown is the best 5 of 8 cards.

- Live demo: https://holdem-plus-demo.onrender.com/app/
- Strategy Guide: https://holdem-plus-demo.onrender.com/app/strategy.html
- New to the repo or picking up where a session left off: read `ORIENTATION.md`, then `HANDOFF.md`
  (current state) and `POLISH_PLAN.md` (backlog). The product plan is
  `Hold_em_Plus___Technology_Development_Plan.md`.

## What's here

```
poker_types.py              Card/HandCategory/HandRank primitives
hand_evaluator.py           best-5-of-8 evaluator, plus describe_hand_rank()
betting_state_machine.py    per-street betting + the full Hold'em Plus dealing sequence
side_pots.py                uncalled-bet refund + multi-way side pots
tournament_structure.py     blind schedule/clock, payouts
tournament_balancing.py     multi-table seating, elimination, table breaks
orchestrator.py             Hand + Tournament, Rabbit Runner, per-hand runout log
analytics.py                hands/hour, pot vs blinds, showdown frequency, hand-strength distribution
demo_showcase.py            two scripted, deterministic showcase hands (GET /demo/script)
api.py                      REST + WebSocket layer
example_usage.py            runnable orchestrator example
test_*.py                   244 tests (pytest)
static/index.html           the demo table client (vanilla JS), served at /app/
static/strategy.html        the Strategy Guide, served at /app/strategy.html
sim/                        C equity simulator, evaluator validation, run_checks.sh, replication notes
.github/workflows/          equity-sim.yml, tests.yml, unpack-zip.yml
docs/                       audit records
Dockerfile, render.yaml, fly.toml, Procfile, DEPLOYMENT.md   deployment (Render auto-deploys on push to main)
```

Everything above the API layer is dependency-free standard-library Python.

## Running it

```bash
pip install -r requirements.txt
bash sim/run_checks.sh py        # pytest: 244 passed
bash sim/run_checks.sh sim       # simulator + evaluator validation + strategy-page match, about 2 minutes
python3 example_usage.py         # orchestrator demo, no network
uvicorn api:app --reload         # server on http://127.0.0.1:8000 (Swagger UI at /docs)
```

## Updating the repo with a zip

Upload one `.zip` to the repository root (GitHub: Add file, Upload files). The "Unpack uploaded zip" workflow
unpacks it into the right folders, runs the validation that fits what changed, and only then commits to `main`
and deletes the zip; on any problem nothing is committed and the zip stays. Accepted: root `*.py`,
`requirements.txt`, `.gitignore`, root `*.md`, `docs/*.md`, `sim/*`, `static/*.{html,css,js,svg}`. Legal and
deployment files are never accepted; workflow files are skipped unless a `WORKFLOW_PAT` secret exists.
Details: `ORIENTATION.md`.

## Quick manual walkthrough

```bash
curl -s -X POST localhost:8000/guest  -d '{"display_name":"Alice"}' -H 'Content-Type: application/json'
curl -s -X POST localhost:8000/guest  -d '{"display_name":"Bob"}'   -H 'Content-Type: application/json'
curl -s -X POST localhost:8000/tables -d '{"max_seats":6,"starting_stack":40}' -H 'Content-Type: application/json'
curl -s -X POST localhost:8000/tables/<table_id>/join -d '{"player_id":"<alice_id>"}' -H 'Content-Type: application/json'
curl -s -X POST localhost:8000/tables/<table_id>/join -d '{"player_id":"<bob_id>"}'   -H 'Content-Type: application/json'
curl -s -X POST localhost:8000/tables/<table_id>/start
curl -s "localhost:8000/tables/<table_id>/state?player_id=<alice_id>"
curl -s -X POST localhost:8000/tables/<table_id>/actions \
  -d '{"player_id":"<alice_id>","action_type":"CALL"}' -H 'Content-Type: application/json'
```

Or connect a WebSocket to `ws://localhost:8000/ws/tables/<table_id>?player_id=<id>` for live pushes.

## Features worth knowing about

**Watch the demo.** `GET /demo/script` returns two scripted, deterministic hands played through the real engine
with a rigged deck: "The Extra Card" (the 3rd hole card completes a straight not reachable with two) and "Rabbit
Runner" (a turn fold, then a paid peek at the river). The landing page animates them and keeps a collapsible
"Hands played so far" log. They are scripted because Rabbit Runner only appears after a turn or river fold, which
the reference bot essentially never does.

**Hand history.** `GET /tables/<id>/hands` returns every hand at a table (most recent first, up to 500 retained),
with board, payouts, revealed hands, folds, and any Rabbit Runner outcome. Unlike `last_hand` on `/state`, which
describes only the latest hand, and `/analytics`, which is aggregate only, this is the per-hand log. `last_hand`
carries a `hand_number` matching it, because its banner (and any rabbit-hunt offer) stays visible for the whole
next hand.

**Runout and showdown descriptions.** `last_hand` and each history entry carry `runout` (a step per flop, 3rd hole
card, turn and river, with the board at that point and, once no more betting is possible, every remaining
player's hole cards) and `hand_descriptions` (`"Two Pair, Jacks and Fours"`, keyed like `revealed_hands`; the
winner is read from `payouts`). Both are empty for a hand that ends by fold. `static/index.html` replays them on
the felt with a Skip button. That replay is verified structurally (jsdom) but **not yet in a real browser**.

**Live bet visibility.** The live `hand` payload carries `current_bet`, `pot_total` and each player's
`bet_this_street`, public to every viewer.

**Analytics.** `GET /tables/<id>/analytics` returns hands/hour, average pot in big blinds, showdown frequency, the
showdown category distribution and a same-evaluator standard-Hold'em baseline; `POST /tables/<id>/feedback`
records thumbs up/down. No screen displays these yet.

**Strategy Guide and equity simulation.** Every number on the guide comes from `sim/holdem_plus_equity.c`: all-in
equity for all 169 starting hands, Hold'em against Hold'em Plus on the same deals, heads-up (300,000 deals each)
and six-handed (150,000), with standard errors. This is raw strength against random hands that never fold, not
profit; the tiers and opening ranges are labelled provisional. The evaluator is validated in layers (exact 5- and
7-card counts, all 7,462 distinct five-card hands, 24 hand-derived edge cases, a 40,000-showdown cross-check
against `hand_evaluator.py`), and `sim/check_published.py` fails if the page's embedded data ever drifts from a
fresh simulation. Replication steps and limits: `sim/README.md`; audit record: `docs/AUDIT_2026-11.md`.

## Known scope limits

Single-process and in-memory: no database, no persistence across restarts, no auth beyond an opaque guest id, one
table per game in the public API (the engine supports multi-table internally), no rate limiting. The bundled
client is a vanilla-JS placeholder; forking a mature poker client is the recommended path for a polished v1
(`POLISH_PLAN.md`, Phase 4+).
