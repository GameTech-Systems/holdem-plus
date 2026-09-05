# Hold'em Plus — Session Handoff

**Purpose of this document:** you're picking this up cold, either as the next
Claude session or a human developer. This tells you exactly what exists,
what's been verified, what's deliberately left undone, and the fastest path
from here to a live GitHub demo poker rooms and casinos can actually click
through.

Start with `README.md` for how to run things. This document is about
*state and decisions*, not setup commands.

---

## -1. Status as of the session that fixed Bug 1 and Bug 2 — read this first

Both bugs flagged in Section 0 below (kept intact beneath this note as the
diagnostic record) are now **fixed and tested**. Per this document's own
instruction ("write the test before fixing it"), a failing regression test
was written and confirmed to fail against the old code *before* either fix
landed:

- **Bug 2 (hand-completion summary) — fixed.** `TableSession` gained a
  `last_hand_result: Optional[HandResult]` field. Both completion sites
  (`apply_action` and `_handle_ws_message`) now do
  `session.last_hand_result = session.tournament.complete_hand(...)`
  *before* `_start_next_hand_if_needed()` overwrites `hands_by_table["T1"]`,
  instead of discarding the return value. `_serialize_state()` now includes
  a top-level `"last_hand"` field (via a new `_serialize_hand_result()`
  helper), populated from `last_hand_result` whenever it's set. This was a
  deliberate choice over a one-off `{"type": "hand_result", ...}` WS message
  (the alternative this doc originally floated): a persistent field means
  the REST response to the very action that ended the hand carries the
  result *and* a client that reconnects or polls a moment later still sees
  it, not just clients that happened to be listening at the exact instant
  the hand completed. `static/index.html`'s `render()` was updated to read
  `state.last_hand` and show a "Last hand: ..." banner, keyed off
  `payouts`+`community_cards` so it only logs each completed hand once even
  though the field stays populated across subsequent state pushes.
  Three new tests in `test_api.py`
  (`test_hand_completion_response_includes_last_hand_payout`,
  `test_last_hand_persists_on_subsequent_polls_until_next_hand_finishes`,
  `test_websocket_broadcast_after_hand_completion_includes_last_hand`) cover
  the REST response, a later poll, and the WS broadcast respectively; all
  three were confirmed failing against the pre-fix code first.
- **Bug 1 (`/app` redirect leaking `localhost`) — fixed.** Added an explicit
  `@app.get("/app")` route, registered ahead of the `StaticFiles` mount,
  that returns `RedirectResponse(url="/app/")` -- a bare relative path, no
  scheme or host. This sidesteps the underlying problem entirely rather
  than trying to teach Starlette/uvicorn to trust proxy-forwarded headers:
  Starlette's own mount-level redirect builds an *absolute* URL from the
  server's own view of its host (confirmed by comparison during this
  session -- against a non-default `base_url` it produced
  `http://example-public-host.test/app/`, baking the host in), which is
  exactly what goes wrong behind a proxy that doesn't forward the original
  Host header. A relative redirect can't have this problem, because the
  browser resolves it against whatever origin it's actually talking to.
  New test: `test_app_redirect_is_relative_not_host_aware` in `test_api.py`,
  which deliberately uses a non-default `base_url` so it would catch a
  regression back to the host-aware mount redirect.

**Verification done this session:**
- Full suite: **158 passed** (154 baseline + 3 for Bug 2 + 1 for Bug 1),
  confirmed with a real `pytest -q` run against the reconstructed repo.
- Both fixes were also verified against a real `uvicorn` process (not just
  FastAPI's `TestClient`) over real HTTP: played a full hand end-to-end via
  plain `requests` calls and confirmed the completing action's JSON
  response contained a populated `last_hand` (real payouts, revealed
  hands, community cards); separately confirmed `GET /app` on that live
  process returns `307` with `Location: /app/` (relative, no host).
- The static mount itself was confirmed still working normally after
  adding the explicit redirect route ahead of it (`GET /app/` and
  `GET /app/index.html` both still serve the real file, `200`, correct
  content-type/length) -- i.e. the new route didn't shadow or break the
  mount for anything other than the exact bare `/app` path it targets.

**One important caveat on how this session worked:** the actual GitHub repo
(`GameTech-Systems/holdem-plus`, private) could not be cloned in this
session -- no GitHub credentials/connector were available, and
`git clone https://github.com/...` failed with an auth error. Everything
above was done by reconstructing the repo's files locally from the content
pasted into the conversation (which matches what this HANDOFF describes as
current), running the real test suite and a real `uvicorn` process against
that reconstruction, and producing exact diffs. **The next session (or you,
right now) still needs to actually apply these changes to the real repo and
commit/push them** -- that part could not be done from here. The diffs are
small and self-contained (all in `api.py`, `test_api.py`, and
`static/index.html`).

**What's next, given this:**
1. Apply the `api.py` / `test_api.py` / `static/index.html` changes to the
   real repo (copy the reconstructed files, or apply the diff) and confirm
   `pytest -q` still says 158 passed there.
2. Do the real audit-testing pass this doc's Section 6 calls for (item 3):
   multi-way all-ins, rabbit hunts, folds at every street, two tabs acting
   rapidly -- now with `last_hand` in place, this is the first time that
   audit pass can actually *see* what happened at showdown while doing it,
   which was the whole blocker before.
3. Everything else in Sections 4-6 below (analytics layer, persistence,
   multi-table routing, a real frontend) is unchanged and still open.

---

## 0. Status as of the most recent session — read this first

*(This section is the diagnostic record from the session that first found*
*Bug 1 and Bug 2, kept as-is below Section -1's update for full context.)*

The repo is live at `github.com/GameTech-Systems/holdem-plus` (private, MIT
licensed) and has been verified **outside my own sandbox**, which matters —
this is the first real confirmation the project works on infrastructure
other than the one it was built in:

- Cloned into a **GitHub Codespace**, `pip install -r requirements.txt` +
  `pytest -q` → **154 passed, 2 warnings** (the one warning is Starlette's
  test client noting its own internal `anyio` deprecation — unrelated to
  this project's code).
- Server started with `python3 -m uvicorn api:app --reload` (not plain
  `uvicorn` — see the bug below) and reached both `/docs` and `/app`
  through Codespaces' port-forwarding proxy.
- **A real hand was played end to end across two browser tabs** (two
  separate guest sessions, same table, both browsers hitting the same
  forwarded Codespaces URL) and completed successfully.

**Bottom line: the game is operational.** The engine, API, and client all
work together on a real deployment, not just in tests. What it needs next
is **audit testing** — playing more hands deliberately looking for
mismatches between what the engine computed and what the UI shows, rather
than more unit tests of individual modules (those are already thorough;
154 of them pass). Two concrete issues surfaced already:

### Bug 1: `/app` redirect leaks `localhost` behind a proxy

FastAPI/Starlette's static-files mount redirects a no-trailing-slash
request (`/app`) to the slashed version (`/app/`), and builds that
redirect using the server's view of its own address. Behind Codespaces'
(or Render's, or Fly.io's) reverse proxy, that's `localhost`, not the
public URL — so the browser was told to go to `localhost:8000` and
(correctly) refused to connect, since the browser isn't inside the
container. **Workaround used this session:** type the trailing slash
yourself (`/app/` instead of `/app`). **Not yet fixed in code** — the real
fix is telling `uvicorn`/Starlette to trust forwarded-host headers from
the proxy so the redirect resolves to the public URL. Worth doing before
handing this link to anyone external, since "the demo doesn't load unless
you know to add a slash" is exactly the kind of friction that loses a
casino contact's attention in the first ten seconds.

> **Update (see Section -1 above): fixed.** The fix actually used was
> simpler than "trust forwarded-host headers" — an explicit relative
> redirect sidesteps host-detection entirely rather than depending on it.

### Bug 2 (diagnosed, not yet fixed): no hand-completion / winner summary shown

**This is the one to prioritize next.** The symptom: play a hand to
showdown, and the client just moves straight into the next hand — no
"X wins with a flush" moment, no visible summary of what happened.

**Root cause, found by re-reading `api.py`:** in both `apply_action()`
(REST) and `_handle_ws_message()` (WebSocket), the sequence on hand
completion is:

```python
if hand.is_complete:
    session.tournament.complete_hand(INTERNAL_TABLE_ID)   # (a)
    _start_next_hand_if_needed(session)                    # (b)
# ... then, only after both (a) and (b) have already run:
await _broadcast_state(session)                            # (c)
```

`complete_hand()` at (a) computes and returns the finished hand's
`HandResult` (payouts, revealed hands, community cards) — but nothing
holds onto it. `_start_next_hand_if_needed()` at (b) immediately overwrites
`session.tournament.hands_by_table["T1"]` with a **brand-new** `Hand`. By
the time `_broadcast_state()` runs at (c) and calls `_serialize_state()`,
`_current_hand(session)` already returns the *new* hand — the just-finished
hand's payouts/showdown/community-cards are gone. They were computed
correctly by the engine (that part's fully tested) but never actually sent
to any client. The static demo client's `render()` function in
`static/index.html` does have code to display a "Hand complete — ..." line
and log it (`if hand.is_complete { ... }`) — that code is simply never
reached, because the state it receives never has `is_complete: true` on it.

**Suggested fix direction (not yet implemented):** don't let step (b)
happen before step (c) has a chance to show the completed hand. Concretely,
either:
- add a `last_hand_result` field to `_serialize_state()`'s output (captured
  before starting the next hand) so the client can show a summary banner
  even once a new hand is already live, or
- broadcast a distinct, one-time `{"type": "hand_result", ...}` message
  right after (a) and before (b), so it's structurally separate from the
  ongoing `"state"` messages the client already treats as transient log
  lines — this is probably the cleaner fix, since it matches how
  `static/index.html`'s `log()` function already expects one-off events
  rather than a persistent field it has to remember to diff against.

Either way: **write the test for this before fixing it.** `test_api.py`
currently has no test that asserts a hand-completion response/broadcast
actually contains the finished hand's payout info — that gap is exactly
how this shipped unnoticed through 154 passing tests. Add
`test_hand_completion_broadcast_includes_winner_and_payout` (or similar)
that plays a hand to completion via the REST `/actions` endpoint and
asserts the *response to that final action* (not the next poll) contains
non-empty `payouts` and `is_complete: true` for the hand that just ended.

> **Update (see Section -1 above): fixed.** Went with the persistent-field
> approach (`last_hand`) rather than a one-off message, specifically
> because it also satisfies "the response to that final action must carry
> the result" without needing separate REST/WS-specific plumbing. Test
> added as described, plus two more covering later polls and the WS
> broadcast.

---

## 1. What exists right now

A complete, tested, working backend for Hold'em Plus, plus a minimal
functional web client. Concretely:

- **154 passing tests** across 8 modules (`pytest -q`), confirmed both in
  this session's sandbox and independently in a GitHub Codespace.
- **A real FastAPI server** (`api.py`) that runs with
  `python3 -m uvicorn api:app --reload` and has now been verified four
  ways: FastAPI's in-process `TestClient` (the 22 tests in `test_api.py`),
  a real `uvicorn` process hit with `curl`, a real `uvicorn` process driven
  through a full hand via plain HTTP requests, and a live two-tab browser
  session through a real Codespaces deployment.
- **A minimal static web client** (`static/index.html`) served at `/app/`
  by the same FastAPI process (note the trailing slash — Bug 1 above).
  This is explicitly a *placeholder*, not the recommended final client —
  see Section 5.

### Module map (see `README.md` for the same list with descriptions)

```
poker_types.py, hand_evaluator.py, betting_state_machine.py,
side_pots.py, tournament_structure.py, tournament_balancing.py
  -> orchestrator.py (Hand + Tournament)
  -> api.py (REST + WebSocket)
  -> static/index.html (vanilla JS client, served at /app/)
```

Each module was built and tested independently before being wired into the
next layer up — if something breaks, the fastest diagnosis is usually
"run that module's own test file in isolation" before assuming the bug is
in the wiring. (Bug 2 above is a good example of the exception: it's purely
a wiring/sequencing bug in `api.py` — every module it touches is correct
and fully tested on its own.)

---

## 2. What changed in the session that built this

The revised plan (`Hold_em_Plus___Technology_Development_Plan.md`)
answered the open rules questions from the original plan. Two of those
answers had real implementation consequences, both done:

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
implemented from the first draft. The "no equity-guidance / trainer mode
for v1" answer has no code implication.

---

## 3. Architecture decisions worth knowing before you touch this

- **Preflop action order is hand-built, not from the generic helper.**
  `BettingRound`'s "start left of the button" logic (in
  `betting_state_machine.py`) is correct for every postflop street but
  wrong for preflop, which starts left of the *big blind*. `Hand`
  constructs the preflop round directly instead of routing through
  `HandFlow.start_betting_round()`. Read the comment in
  `Hand._start_preflop_betting()` before touching betting order logic.
- **Heads-up blind posting is a special case.** Button posts the small
  blind and acts first preflop, in `Hand._post_blinds()`. Real poker rule,
  not a demo shortcut.
- **Chips live in `Tournament`, not `tournament_balancing`.** Seating and
  elimination (`tournament_balancing.py`) deliberately know nothing about
  chip counts — `Tournament` in `orchestrator.py` owns the `stacks` dict
  and writes it back after every hand. Keep this separation if you extend
  either module.
- **The API is single-table-per-game.** `Tournament` already supports
  multi-table balancing and breaking (tested in
  `test_tournament_balancing.py`), but `api.py` always creates a
  `Tournament` with `max_table_size` equal to the table's seat count, so it
  only ever produces one internal table (`"T1"`).
- **State is in-memory, single-process.** `TABLES` and `GUESTS` in
  `api.py` are module-level dicts. Fine behind one `uvicorn` worker. **Not**
  safe with `--workers > 1` or a load balancer without replacing that
  storage.
- **`TableSession.last_hand_result` (new, this session) follows the same**
  **single-process/in-memory constraint as everything else in `api.py`.**
  It's just one more field on the same module-level dict-backed session
  object — no new persistence story, no new scaling story. If/when
  `TableSession` moves to a real store (Redis/DB), this field goes with it.
- **The hand-completion sequencing bug (Bug 2, now fixed) is the clearest**
  **illustration yet of why "the engine is fully tested" and "the product
  is fully tested" are different claims.** Every module below `api.py` was
  correct; the bug was entirely in the order two lines ran in a request
  handler, and in nothing capturing complete_hand()'s return value. Audit
  testing from here should specifically look for more of this category —
  sequencing/ordering issues at the API layer that unit tests of
  individual modules can't catch.

---

## 4. What's explicitly NOT built — read this before promising anything

- **No real frontend.** `static/index.html` is a deliberately minimal,
  single-file vanilla JS/CSS client. The original plan's recommendation to
  fork the PokerTH web client (or `bocaletto-luca/Texas-Holdem`) still
  stands as the right move for anything shown to an actual poker room or
  casino. Treat the current client as a bridge, not the destination.
- **No analytics/instrumentation layer.** Hands-per-hour, pot-size-vs-blinds,
  hand-strength distribution at showdown, player-reported excitement — none
  of it exists yet. This is a real gap: without it, the demo can prove the
  game *works* but not that it's *better*. Start with logging every
  `HandResult` from `Tournament.hand_history` (already populated).
- **No persistence.** Restarting `uvicorn` loses every table.
- **No multi-table routing in the API**, even though `Tournament` supports
  it.
- **No rate limiting, no abuse protection, no real auth.**
- **Known, documented simplifications inside the engine itself** (each has
  a comment at the point in the code where it matters, and a test covering
  the edge case rather than leaving it silent):
  - `side_pots.py`: a pot layer where every contributor folded merges into
    the prior pot rather than incremental uncalled-bet return per street.
  - `betting_state_machine.py`: no side-pot math here by design (lives in
    `side_pots.py`).
  - `tournament_balancing.py`: player moves happen immediately on
    elimination, not delayed to the moved player's next big blind. No
    "avoid reseating players who were just broken apart" rule.

None of these are blockers for a fake-money demo. All are real
conversations before anyone discusses real money.

---

## 5. Licensing — resolved this session

**Done:** the repo is MIT licensed (chosen at repo-creation time). Every
module is original code with no forked dependencies, so this was a free
choice — see the tech plan's Section 6 for why that freedom disappears the
moment a PokerTH or `bocaletto-luca` fork gets merged in, and revisit the
license specifically at that point rather than assuming MIT still fits.

---

## 6. Fastest path from here to a live, shareable demo link

Updated priority order, given this session's findings:

1. ~~**Fix Bug 2 (hand-completion summary)**~~ **Done — see Section -1.**
2. ~~**Fix Bug 1 (`/app` proxy redirect)**~~ **Done — see Section -1.**
3. **Do a real audit-testing pass**, not more unit tests: play many hands
   deliberately trying to break the sequencing (multi-way all-ins, rabbit
   hunts, folds at every street, rapid actions from two tabs at once) and
   watch for mismatches between engine state and what the UI shows, the
   way Bug 2 was found. Log anything that looks off even if you can't
   immediately explain it. **This is now the top of the list.**
4. **Deploy somewhere with a stable, non-Codespaces URL.** Codespaces was
   great for verification but isn't meant to be a durable public link —
   it's tied to being logged into your GitHub account and isn't designed
   to run unattended. A single-process free tier (Render, Fly.io, Railway)
   is the right target for an actual shareable demo link (remember the
   single-worker constraint from Section 3).
5. **Decide whether to invest in a real frontend now or after initial
   feedback.** The minimal client is enough to demo the *rules*; not
   enough to demo *product polish* to a casino evaluating whether to
   spread this live.
6. **Start the analytics layer** (Section 4) — independent work, can run in
   parallel with #5.

---

## 7. If you're a fresh Claude session picking this up

**Read Section -1, then Section 0, in full** — Section -1 is the most
current information (both previously-open bugs are now fixed and tested);
Section 0 is the diagnostic record of how they were found and is still
useful background, especially for the audit-testing pass in Section 6.

### If you can connect GitHub directly (recommended)

Point the connector at `GameTech-Systems/holdem-plus` and pull the whole
repo — the file count stops being a cost once you're not copy-pasting.
**Note:** the session that wrote Section -1 did *not* have GitHub access
and worked from pasted file contents instead — if that's still true for
you, the Section -1 fixes exist as verified diffs/file contents but may
not yet be applied to the actual repo. Check before assuming they're live.

### If you can't connect GitHub and someone's pasting files in by hand

Ask for these, in this order, and treat everything else as "pull in only
if a specific task needs it":

1. **`HANDOFF.md`** (this file) — always first, always in full.
2. **`README.md`** — run commands, one screen.
3. **`api.py`**, **`test_api.py`**, and **`static/index.html`** — Bugs 1
   and 2 lived entirely in the interaction between these files; nothing
   else was needed to fix them, and nothing else should need touching for
   closely-related follow-up work (e.g. the audit-testing pass).
4. **`orchestrator.py`** — needed to understand what `Hand.result` /
   `HandResult` actually contain, since that's the data both the `"hand"`
   and new `"last_hand"` fields in `api.py` route through.

Everything else (`poker_types.py`, `hand_evaluator.py`,
`betting_state_machine.py`, `side_pots.py`, `tournament_structure.py`,
`tournament_balancing.py`, and all nine `test_*.py` files other than
`test_api.py`) is fully tested, stable, and not implicated in either
now-fixed issue — only pull those in if a new task specifically touches
that layer. Run `pytest -q` first thing regardless of how you got the
files, to confirm the **158**-passed baseline (154 original + 4 from this
session) before changing anything.
