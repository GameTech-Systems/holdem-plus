# Hold'em Plus — Session Handoff

**Purpose of this document:** you're picking this up cold, either as the next
Claude session or a human developer. This tells you exactly what exists,
what's been verified, what's deliberately left undone, and the fastest path
from here forward. It supersedes the previous `HANDOFF.md` — that version's
Section 0 (the analytics/instrumentation session) is now historical
background; see Section 0 below for the current state instead.

Start with `README.md` for how to run things. This document is about
*state and decisions*, not setup commands.

---

## 0. Status as of the most recent session — read this first

This session's brief, from chat: close out four open items, and build
something that makes the live demo "good enough to showcase" — specifically
a scripted, automatic playthrough of a couple of hands so a visitor (or a
potential contributor) doesn't have to stumble into the interesting parts
by luck.

**This sandbox had an actual live clone of `github.com/GameTech-Systems/holdem-plus`
already checked out** (confirmed via `git remote -v`), so this session
verified claims against it directly rather than trusting only the
pasted-in chat snapshot — same practice the prior session recommended.

### Verification findings, before any code was written

- The 6 files saved in the Claude Project (`HANDOFF.md`, `analytics.py`,
  `test_analytics.py`, `api.py`, `test_api.py`, `README.md`) were
  **byte-identical** to what's live (`git diff --stat HEAD` on all five
  tracked ones came back empty). No drift there this time.
- **`TRADEMARKS.md` — confirmed fixed.** The live file now reads "The
  Hold'em Plus Poker Variant was first presented by James Tinghitella
  here: https://sites.google.com/view/gametechsystems/home" — the
  previously-bare URL has a proper framing sentence now. This closes open
  item 3 from the prior handoff; verified directly, not just taken on
  faith from the chat request.
- **`CODE_OF_CONDUCT.md` — confirmed still broken.** Live repo still had
  `ToBeUpdated` for the enforcement contact. Fixed this session (below).
- **`static/index.html`'s Rabbit Runner UI is genuinely live** — the
  button/reveal code has been deployed for a while (`git log` shows
  `static/index.html` was last touched several commits back, well before
  this session). This is not a stale-deploy problem.
- **New finding: `HANDOFF.md` was deleted from the live repo.**
  `git log --oneline --all -- HANDOFF.md` shows it existed, then a commit
  titled `Delete HANDOFF.md` removed it, and nothing has re-added it since
  (`git status` shows it as untracked in this checkout — it only exists
  here because it's separately saved in the Claude Project). The actual
  GitHub repo currently has **no handoff doc at all**. See open decision 3
  below.
- The GitHub Discussions thread the chat pointed at
  (`.../discussions/1`) is real and reachable, and currently holds only
  GitHub's generic auto-generated welcome post from `BetterToBest` — a
  real welcome message replaces something meaningful there, not a blank
  page.

### Diagnosis: "the game doesn't show the rabbit runner update"

Not a bug, and not a stale deploy. **Rabbit Runner eligibility requires
folding on the turn or river** (`orchestrator.Hand.is_eligible_for_rabbit_hunt`),
and `orchestrator.default_bot_action` — the reference bot policy used to
fill seats and drive simulations — checks or calls whenever it legally
can, and only ever reaches `FOLD` as an absolute last resort. Since
`ALL_IN` is a legal action any time a player still has a stack, that last
resort is essentially never reached while a bot has chips. A bot-filled
table, or a human just clicking check/call, can run for a long time
without a single qualifying fold — so the feature can look "not there"
purely by never coming up, even though the UI code for it has been
deployed for a while.

**Fix approach:** did *not* modify `default_bot_action` — several existing
tests depend on its exact "never folds while it has chips" behavior (e.g.
`test_checked_down_hand_conserves_total_chips` asserts all 5 community
cards get dealt, which requires nobody folding early). Changing shared
engine-adjacent code for a cosmetic demo concern risked breaking that
contract for no good reason. Instead, this session built a separate,
additive, fully **scripted** demo mode that guarantees showing the
feature every time, without touching bot behavior at all.

### What shipped this session

1. **`demo_showcase.py`** (new) — two fully scripted, deterministic hands:
   - *"The Extra Card"* — 3 players, checked down to showdown; one
     player's 3rd hole card completes a straight that isn't reachable
     from the same deal with only 2 hole cards (a cleaner, from-scratch
     version of the scenario `test_hand_evaluator.py`'s
     `test_third_hole_card_enables_a_hand_unreachable_with_two_hole_cards`
     already proves works at the evaluator level).
   - *"Rabbit Runner"* — heads-up; one player folds on the turn facing a
     bet, the hand ends, and `Hand.rabbit_hunt()` is called immediately
     after to reveal the river that would have come.

   Both hands are built with a rigged deck (`_build_scripted_deck`,
   generalizing `test_orchestrator.py`'s `_build_rigged_heads_up_deck` to
   any seat count) and played through the *real*
   `Hand`/`HandFlow`/`BettingRound`/`side_pots`/`hand_evaluator` stack —
   nothing here reimplements game logic. Deterministic by design, not
   bot-driven or random, specifically so the demo shows the same two
   things every single time it's requested. See the module's own
   docstring for the full reasoning.

2. **`test_demo_showcase.py`** (new) — 14 tests: category/payout
   correctness for both scripted hands, chip conservation (including
   confirming the Rabbit Runner fee is the *only* expected discrepancy —
   see `orchestrator.Hand.rabbit_hunt`'s own docstring on why that fee
   isn't modeled as going anywhere), board-reveal staging, and
   determinism across repeated calls.

3. **`api.py`** — new `GET /demo/script` endpoint, cached process-wide
   after first computation (same pattern as the existing
   `_standard_holdem_baseline`, since the script is a pure function of no
   input). Creates no table, no guest, no `Tournament`; never touches
   `TABLES`/`GUESTS`.

4. **`test_api.py`** — 4 new endpoint tests, including one that calls
   `/demo/script` with zero prior `/guest` or `/tables` calls, to pin
   down that it genuinely stands on its own.

5. **`static/index.html`** — a "Watch the demo" teaser panel plus an
   animated demo panel (skip-ahead and exit controls), reusing the
   existing dark felt/gold CSS variables and the existing
   `renderCard()`/`suitInfo()` helpers so demo cards look identical to
   real ones. The Rabbit Runner reveal renders as a visually distinct
   "ghost card" (dashed outline, dimmed) appended after the real board,
   so it never reads as a genuine 5th community card.

   Verified two ways: `node --check` on the extracted script (syntax),
   and a throwaway Node + jsdom smoke test that loaded the real file,
   mocked `fetch` to serve the real `/demo/script` payload, and actually
   clicked through the whole flow (watch demo → skip hand 1 → skip hand
   2 → "that's the demo" message → exit demo) — zero thrown errors, seats
   and log and community cards all populated as expected. That's
   meaningfully stronger than a syntax check, but **it is still not the
   same as loading the real deployed URL in a real browser** — see
   Section 3. The jsdom scaffolding itself (`node_modules`, a throwaway
   `package.json`, the smoke-test script) was verification-only and was
   deleted before finishing up; it's not part of the repo and isn't in
   the delivered files.

6. **`CODE_OF_CONDUCT.md`** — `ToBeUpdated` replaced with the GitHub
   Discussions link
   (`https://github.com/GameTech-Systems/holdem-plus/discussions/1`),
   with a short added note reconciling "this is a public thread" against
   the paragraph immediately below it promising reporter privacy (the
   note tells reporters to ask for a private follow-up rather than
   posting sensitive specifics in the open thread).

7. **`welcome_message.md`** (new — not a repo file; content meant to be
   pasted as a comment on Discussion #1, or used to replace the generic
   default post there).

8. **`README.md`** — new "Watch the demo" section explaining the feature
   and why it exists, updated file listing (`demo_showcase.py` added),
   and the test count bumped to match.

**Test suite: 206 passed** (188 prior + 18 new: 14 in
`test_demo_showcase.py`, 4 added to `test_api.py`). Verified via
`pytest -q` run clean multiple times across this session, including
immediately after the doc-only edits (README/CODE_OF_CONDUCT don't affect
tests, but re-ran anyway rather than assuming).

### The four open items from the handoff conversation

1. **CODE_OF_CONDUCT.md contact → GitHub Discussions:** done (above).
2. **Entity naming mismatch** ("GamingTech, LLC" vs. "GameTech Systems" in
   `TRADEMARKS.md`): still open, untouched this session — see Section 4.
3. **Trademarks bare URL:** confirmed already resolved on the live repo
   (verified directly, not just taken on the chat's word).
4. **"Repo is live, deploy seems to have updated, but rabbit runner
   doesn't show":** explained above — not a deploy problem, a
   discoverability problem, now directly addressed by demo mode.

---

## 1. What exists right now

Everything from the prior session, plus a scripted demo landing feature:

```
poker_types.py, hand_evaluator.py, betting_state_machine.py,
side_pots.py, tournament_structure.py, tournament_balancing.py
  -> orchestrator.py (Hand + Tournament)
  -> analytics.py (hands/hour, pot-vs-blinds, showdown frequency,
                    hand-strength distribution, player feedback)
  -> demo_showcase.py (two scripted, deterministic showcase hands,
                        built on top of orchestrator.Hand directly)
  -> api.py (REST + WebSocket, /analytics, /feedback, /demo/script)
  -> static/index.html (vanilla JS client, served at /app/, now with a
                         "Watch the demo" teaser + animated playback)
```

Every module above the API layer is still dependency-free standard-library
Python (`demo_showcase.py` included). Deployment configs are unchanged
(`Dockerfile`/`.dockerignore`, `render.yaml`, `fly.toml`, `Procfile`,
`DEPLOYMENT.md`). The live instance is
`https://holdem-plus-demo.onrender.com/app/` — **this session's changes are
not deployed there yet**; see Section 5.

Governance/legal scaffolding: `LICENSE` (Apache 2.0), `NOTICE`,
`TRADEMARKS.md` (bare-URL issue now resolved; entity-naming note still
open), `CODE_OF_CONDUCT.md` (contact now points at Discussions;
enforcement-guideline text unchanged), `CONTRIBUTING.md` (DCO-based
sign-off flow, unchanged).

---

## 2. Architecture decisions worth knowing before you touch this

Carried forward from prior sessions (still accurate):

- Preflop action order is hand-built, not from the generic helper
  (`Hand._start_preflop_betting()`'s comment).
- Heads-up blind posting is a special case (`Hand._post_blinds()`).
- Chips live in `Tournament`, not `tournament_balancing`.
- The API is single-table-per-game.
- State is in-memory, single-process (`TABLES`/`GUESTS` module-level
  dicts; single worker everywhere by design).
- Verify a fix landed in the file that's actually served/imported, not
  just that the content exists somewhere in the repo.
- `analytics.py` is a read-only consumer of `HandResult`, never a
  producer or mutator.
- The blind clock is synced lazily (`_sync_tournament_clock`), only right
  before a new hand is dealt, not via a background task.
- The standard-Hold'em baseline is a cached, process-wide, seeded Monte
  Carlo estimate, not recomputed per request.

New this session:

- **`demo_showcase.py` is deliberately scripted and deterministic, not
  bot-driven or random.** See the diagnosis above for why: a
  bot/random-driven demo could easily run its two or three hands without
  ever surfacing a turn/river fold at all. `_build_scripted_deck`
  generalizes the rigged-deck technique `test_orchestrator.py` already
  established (`_build_rigged_heads_up_deck`) to arbitrary seat counts —
  if a future session adds a third showcase hand, reuse that helper
  rather than hand-building another deck from scratch.
- **Demo events always do a full-reveal snapshot** — every seat's hole
  cards, regardless of fold/all-in status (`demo_showcase._snapshot`).
  This is intentionally different from `api.py`'s real
  `_serialize_state`, which still redacts normally for actual tables.
  It's a demo-only, spectator/teaching convention, not a change to real
  hidden-information rules — `/demo/script` is a separate, stateless,
  read-only endpoint that never touches `TABLES`/`GUESTS` or any real
  `Hand`. Don't let a future edit blur this line by, say, routing real
  table state through the same full-reveal snapshot helper.
- **`default_bot_action` was deliberately left unmodified**, even though
  making it occasionally fold would also help real bot-filled tables
  surface Rabbit Runner sometimes. Multiple existing tests
  (`test_orchestrator.py`, `test_api.py`) depend on its exact "never
  folds while it has chips" behavior. If a future session wants that
  behavior for bot-filled (non-demo) tables, add a new, separate,
  opt-in policy function — don't change the shared default.
- **`/demo/script` is cached process-wide**, same reasoning and same
  pattern as `_standard_holdem_baseline`: it's a pure function of no
  input, so there's no reason it would ever produce different output
  within a process.

---

## 3. What's explicitly NOT built — read this before promising anything

Carried forward (all still true): no real frontend fork, no persistence,
no multi-table routing in the API, no rate limiting/auth beyond opaque
guest IDs, the known engine simplifications documented in their own
modules, no analytics UI, the Monte Carlo baseline is Hold'em-only (no
single "here's the delta" endpoint).

New from this session:

- **Demo mode is fixed at exactly 2 hands.** A natural next addition,
  flagged but not built: a 3rd showcase hand demonstrating multi-way side
  pots (`side_pots.compute_side_pots`/`award_pots`) — arguably the other
  genuinely easy-to-get-wrong piece of this codebase, and it would round
  out the "prove the hard parts work" pitch. Would need a 3-or-4-handed
  rigged deck with at least one short stack forced all-in;
  `_build_scripted_deck` should handle it as-is, it just needs the right
  card/action script written against it.
- **No real browser click-through happened this session.** Verification
  was the full pytest suite (206 passed) plus a throwaway Node+jsdom
  smoke test (see Section 0) that is meaningfully stronger than a syntax
  check but is still not "loaded the actual deployed URL in a real
  browser." Do that before pointing anyone outside the project at it —
  this is the same standing gap the prior two handoffs both flagged and
  neither session was able to close from this sandbox.
- **`welcome_message.md` is drafted but not posted** — someone needs to
  actually paste it into Discussion #1 (or use it to replace the generic
  default post there).
- **This session's changes are not pushed or redeployed.** Same "no push
  credentials / no deploy access from here" limitation as
  `DEPLOYMENT.md` already documents.
- **No frontend test harness was added to the repo.** The jsdom smoke
  test was created and deleted within this session purely as
  verification scaffolding — no `package.json`, no `node_modules`, no
  committed JS test file. Real frontend test coverage, if this project
  wants it, is still a from-scratch addition for a future session.

---

## 4. Open decisions (not bugs — need a person to decide, not a fix)

1. **Entity naming mismatch** ("GamingTech, LLC" vs. "GameTech Systems"
   in `TRADEMARKS.md`) — still unresolved.
2. **`HANDOFF.md` is currently absent from the live repo** (deleted at a
   past commit, never restored — see Section 0). Decide whether to commit
   this version back to the actual repo at the root as `HANDOFF.md`
   (recommended — keeps a fresh session's `git clone` self-sufficient,
   matching this project's own stated practice in Section 6 below) or
   keep it Claude-Project-only going forward. If it goes back into the
   repo, this exact file is what to commit.
3. **How far to extend demo mode** — a 3rd (side-pot) showcase hand, an
   interactive bot-filled demo table instead of a fixed script, a
   "replay" control, etc. None of this was built this session; all of it
   is just flagged as options for whoever picks this up next.

---

## 5. Fastest path from here forward

1. **Get this session's changes live**: add/update `demo_showcase.py`,
   `test_demo_showcase.py`, `api.py`, `test_api.py`, `static/index.html`,
   `CODE_OF_CONDUCT.md`, `README.md`, and (per open decision 2) this
   `HANDOFF.md` in the actual repo; confirm `pytest -q` shows 206 passing
   on a clean clone; push; redeploy to Render.
2. **Post `welcome_message.md`'s content** as a comment on Discussion #1
   (or use it to replace the generic default post there).
3. **Do the live-URL audit pass this session couldn't do**: once
   deployed, load `https://holdem-plus-demo.onrender.com/app/` in an
   actual browser, click "Watch the demo," and confirm both hands
   actually play through and the Rabbit Runner ghost-card reveal renders
   correctly outside of jsdom.
4. **Decide open items 1 and 2** from Section 4.
5. **Consider the side-pot 3rd showcase hand** as the next demo-mode
   addition (Section 3).
6. **Longer-standing priorities, unchanged from before**: surface
   analytics somewhere a human actually looks at it, and evaluate
   committing to a real frontend fork (PokerTH web client or
   `bocaletto-luca/Texas-Holdem`) — still the biggest lever for a
   casino/poker-room contact taking the demo seriously.

---

## 6. If you're a fresh Claude session picking this up

**Read Section 0 in full, then verify it yourself before trusting it.**
`git clone https://github.com/GameTech-Systems/holdem-plus` is reachable
from a sandboxed environment with this session's network allowlist
(confirmed both via an already-present clone and independently via
`web_fetch` against `github.com`) — clone it, don't assume a handoff
doc's claims are still true without checking. This session found real
drift a purely pasted-in snapshot wouldn't have shown on its own
(`HANDOFF.md`'s own deletion from the repo).

Run `pytest -q` first thing; the baseline as of this session is **206
passed**. If `HANDOFF.md` isn't in the clone, that's not a surprise — see
open decision 2.

Standing advice, still exactly right, and still not fully closed out:
don't stop at "the code exists, the tests pass, and it looks right in
isolation" — load the actual live URL and click through real behavior
before calling anything shipped. This session got closer than either
prior one (a real jsdom click-through, not just a syntax check) but still
didn't clear that bar. Whoever picks this up next should be the session
that finally does.
