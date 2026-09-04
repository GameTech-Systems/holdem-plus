# Hold'em Plus — Session Handoff

**Purpose of this document:** you're picking this up cold, either as the next
Claude session or a human developer. This tells you exactly what exists,
what's been verified, what's deliberately left undone, and the fastest path
from here to a live GitHub demo poker rooms and casinos can actually click
through.

Start with `README.md` for how to run things. This document is about
*state and decisions*, not setup commands.

---

## 1. What exists right now

A complete, tested, working backend for Hold'em Plus, plus a minimal
functional web client. Concretely:

- **154 passing tests** across 8 modules (`pytest -q`).
- **A real FastAPI server** (`api.py`) that runs with `uvicorn api:app` and
  has been smoke-tested three ways: FastAPI's in-process `TestClient`
  (the 22 tests in `test_api.py`), a real `uvicorn` process hit with `curl`,
  and a real `uvicorn` process driven through a full hand via plain HTTP
  requests (chips conserved, hand auto-advanced correctly).
- **A minimal static web client** (`static/index.html`) served at `/app` by
  the same FastAPI process — open it, create a table, open it again in a
  second tab, join, start, and play a hand with real clicks. This is
  explicitly a *placeholder*, not the recommended final client — see
  Section 4.

### Module map (see `README.md` for the same list with descriptions)

```
poker_types.py, hand_evaluator.py, betting_state_machine.py,
side_pots.py, tournament_structure.py, tournament_balancing.py
  -> orchestrator.py (Hand + Tournament)
  -> api.py (REST + WebSocket)
  -> static/index.html (vanilla JS client, served at /app)
```

Each module was built and tested independently before being wired into the
next layer up — if something breaks, the fastest diagnosis is usually
"run that module's own test file in isolation" before assuming the bug is
in the wiring.

---

## 2. What changed in this session, and why

The attached revised plan (`Hold_em_Plus___Technology_Development_Plan.md`)
answered the open rules questions from the original plan. Two of those
answers had real implementation consequences, both now done:

- **Rabbit Runner moved from v2 to v1 scope.** Implemented in
  `orchestrator.py`: `Hand.is_eligible_for_rabbit_hunt()` and
  `Hand.rabbit_hunt()`. A player who folds on the turn or river (i.e.
  after the 4th street card was already revealed) can pay one small blind
  (capped at whatever's left in their stack) to see the river card that
  was already dealt face-down as part of the front-loaded dealing
  procedure. Exposed via `POST /tables/{id}/rabbit-hunt` and a WebSocket
  `rabbit_hunt` message, and wired into the demo client's action bar.
- **Guest/anonymous play, no login required.** `POST /guest` mints an
  opaque id with no password or verification — matches the "don't make
  people log in to try it" requirement directly.

The revised dealer-procedure wording (burn-then-flop, burn-then-3rd-hole,
etc.) already matched what `betting_state_machine.py` and `orchestrator.py`
implemented from the first draft — no code change needed there, just
confirms the existing sequencing is right.

The "no equity-guidance / trainer mode for v1" answer has no code
implication (it's a product decision to build nothing there yet).

---

## 3. Architecture decisions worth knowing before you touch this

- **Preflop action order is hand-built, not from the generic helper.**
  `BettingRound`'s "start left of the button" logic (in
  `betting_state_machine.py`) is correct for every postflop street but
  wrong for preflop, which starts left of the *big blind*. `Hand`
  constructs the preflop round directly instead of routing through
  `HandFlow.start_betting_round()`. If you ever change betting order
  logic, this is the one place it's special-cased — read the comment in
  `Hand._start_preflop_betting()` first.
- **Heads-up blind posting is a special case.** Button posts the small
  blind and acts first preflop, in `Hand._post_blinds()`. This is a real
  poker rule, not a demo shortcut.
- **Chips live in `Tournament`, not `tournament_balancing`.** Seating and
  elimination (`tournament_balancing.py`) deliberately know nothing about
  chip counts — `Tournament` in `orchestrator.py` owns the `stacks` dict
  and writes it back after every hand, then hands busted player ids to
  `tournament_balancing.eliminate_player()`, which triggers its own
  rebalancing. Keep this separation if you extend either module.
- **The API is single-table-per-game.** `Tournament` already supports
  multi-table balancing and breaking (tested in `test_tournament_balancing.py`),
  but `api.py` always creates a `Tournament` with `max_table_size` equal to
  the table's seat count, so it only ever produces one internal table
  (`"T1"`). Multi-table routing through the API is real, scoped work, not
  yet started (see Section 4).
- **State is in-memory, single-process.** `TABLES` and `GUESTS` in
  `api.py` are module-level dicts. This is fine for a demo behind one
  `uvicorn` worker. It is **not** safe to run with `--workers > 1` or
  behind a load balancer without replacing that storage — each worker
  would have its own, inconsistent copy of every table.

---

## 4. What's explicitly NOT built — read this before promising anything

- **No real frontend.** `static/index.html` is a deliberately minimal,
  single-file vanilla JS/CSS client — enough to prove the API works and to
  have *something* clickable for a demo link, not a polished product. The
  original plan's recommendation to fork the PokerTH web client (or
  `bocaletto-luca/Texas-Holdem`) still stands as the right move for
  anything shown to an actual poker room or casino. Treat the current
  client as a bridge, not the destination.
- **No analytics/instrumentation layer.** Section 3.2 item 5 of the plan —
  hands-per-hour, pot-size-vs-blinds, hand-strength distribution at
  showdown, player-reported excitement — is the part that actually tests
  the core hypothesis, and none of it exists yet. This is a real gap, not
  a nice-to-have: without it, the demo can prove the game *works* but not
  that it's *better*. Natural place to start: log every `HandResult` from
  `Tournament.hand_history` (already populated) to a file or a metrics
  endpoint.
- **No persistence.** Restarting the `uvicorn` process loses every table.
  Fine for a demo; not fine for anything a casino contact might return to
  the next day. Cheapest fix for a demo (not production): a periodic
  dump of `TABLES`/`GUESTS` to disk, reloaded on startup.
- **No multi-table routing in the API**, even though `Tournament` supports
  it. If the demo needs a bigger field than one table's max seats, that's
  the next piece of `api.py` to build, not new engine work.
- **No rate limiting, no abuse protection, no real auth.** Fine behind a
  link you hand to a handful of poker-room contacts; not fine if the link
  gets shared widely.
- **Known, documented simplifications inside the engine itself** (each has
  a comment at the point in the code where it matters, and a test covering
  the specific edge case rather than leaving it silent):
  - `side_pots.py`: a pot layer where every contributor folded merges into
    the prior pot rather than being resolved via incremental uncalled-bet
    return at each street closure. Fine for a fake-money demo; worth a
    second look before anything with real stakes.
  - `betting_state_machine.py`: no side-pot math lives here by design
    (kept in `side_pots.py`); this module also doesn't handle multi-way
    all-in edge cases beyond what `is_complete()` needs.
  - `tournament_balancing.py`: player moves between tables happen
    immediately on elimination, not delayed to the moved player's next big
    blind (a real-room courtesy, not a correctness issue). No "avoid
    reseating two players who were just broken apart" softening rule.

None of these are blockers for a fake-money GitHub demo. All of them are
real conversations to have before anyone discusses real money.

---

## 5. Licensing — a decision that needs to happen before the repo goes public

Everything in this repo right now (all 8 engine/API modules, the static
client) is **original code with no forked dependencies**, so the team is
free to license this repository however it wants — MIT or Apache-2.0 are
both reasonable, permissive defaults for a repo meant to be evaluated and
possibly integrated by poker rooms and casinos.

That freedom disappears the moment anyone forks PokerTH's web client
(AGPLv3/GPLv2) or `bocaletto-luca/Texas-Holdem` (GPLv3) into this repo, per
Section 6 of the tech plan. One thing worth flagging to whoever makes that
call: because this backend now talks to any frontend purely over a network
API (REST/WebSocket) rather than being statically combined into one
artifact, a forked-AGPL frontend calling this backend as a separate service
is the kind of architecture that's commonly treated as *not* creating a
combined work requiring the backend to also be AGPL — that's a favorable
starting position, not a legal conclusion. Get an actual read from counsel
before relying on it, same as every other legal note in the tech plan.

**Concrete recommendation:** pick MIT or Apache-2.0 for this repo now,
before adding a `LICENSE` file, and revisit specifically when/if a PokerTH
fork gets merged in rather than assuming today's choice still holds then.

---

## 6. Fastest path from here to a live GitHub demo link

In rough priority order:

1. **Add a `LICENSE` file** (Section 5) — do this before making the repo
   public, not after.
2. **Push this repo to GitHub as-is.** Everything here already runs from a
   clean checkout (`pip install -r requirements.txt && pytest -q`) — verify
   that on a truly clean clone/venv before pushing, since this session's
   testing all happened in one accumulated environment.
3. **Deploy `api.py` somewhere with a stable URL.** A single-process free
   tier (Render, Fly.io, Railway) is enough for a demo — remember the
   single-worker constraint from Section 3. Point `static/index.html` at
   it via `?api=https://your-deployed-url` in the query string, or just
   let people hit `https://your-deployed-url/app` directly (it's already
   same-origin, no config needed).
4. **Play a full hand yourself against the deployed URL** end to end (two
   browser tabs, like the smoke test in this session) before sending the
   link to anyone external.
5. **Decide whether to invest in a real frontend now or after initial
   feedback.** The minimal client is enough to demo the *rules* (does the
   3rd hole card feel good, is the pacing right); it is not enough to
   demo *product polish* to a casino evaluating whether to spread this
   live. If early feedback on the rules is positive, forking PokerTH's web
   client (Section 3.2 of the plan) is the next real chunk of work.
6. **Start the analytics layer** (Section 4) in parallel with #5 — it's
   independent work and the plan's hypothesis genuinely can't be validated
   without it.

---

## 7. If you're a fresh Claude session picking this up

Read, in order: this document, `README.md`, then
`Hold_em_Plus___Technology_Development_Plan.md` for full product context.
Run `pytest -q` first thing to confirm you're starting from a green
baseline (154 passed) before changing anything. Every module has its own
test file with the same name (`X.py` / `test_X.py`) — when extending a
module, extend its test file in the same pass, the way every prior turn in
this session did; that discipline is the reason the wiring bugs that did
show up (preflop action order, a couple of API redaction gaps) were caught
immediately rather than shipped.
