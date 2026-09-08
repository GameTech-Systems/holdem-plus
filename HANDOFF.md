# Hold'em Plus — Session Handoff

**Purpose of this document:** you're picking this up cold, either as the next
Claude session or a human developer. This tells you exactly what exists,
what's been verified, what's deliberately left undone, and the fastest path
from here forward. It supersedes the previous `HANDOFF.md` — that version's
Section 0 (the demo-showcase/landing-page session) is now historical
background; see Section 0 below for the current state instead.

Start with `README.md` for how to run things and `POLISH_PLAN.md` for the
forward-looking backlog. This document is about *state and decisions*.

---

## 0. Status as of the most recent session — read this first

This session's brief, from chat: the live demo works, but a table's first
hand plays out and then its info "goes away" the moment the second hand
starts — add a way to review each hand's log in a collapsible box, then
write a phased polish plan for future sessions (assume ~5-hour working
windows), and leave a fresh handoff behind.

**Verified the live repo directly rather than trusting the pasted-in chat
snapshot — same practice every prior session has recommended, and worth
restating because it mattered again this time.** The chat's own attached
file snapshot (`side_pots.py`, `api.py`, `static/index.html`, etc., pasted
in as conversation documents) turned out to predate `analytics.py` and
`demo_showcase.py` entirely — an older state than even the *previous*
`HANDOFF.md`'s own Section 0 described. Cloning
`github.com/GameTech-Systems/holdem-plus` fresh (reachable from this
sandbox's network allowlist, confirmed the same way the prior session
confirmed it) and working from that, not the chat attachments, is what
caught this. If you're reading this in a chat session that has files
pasted into it, assume they may be stale until you've cloned and checked.

### Verification findings, before any code was written

- `pytest -q` on a fresh clone: **206 passed**, matching the previous
  `HANDOFF.md`'s stated baseline exactly. No drift in the engine/API/test
  layers since that session.
- **A live, in-progress upload mistake was caught mid-history and had
  already been corrected minutes before this session started.** `git log`
  on `static/index.html` shows: the demo-showcase UI additions (the
  "Watch the demo" teaser + animated panel) were first uploaded to the
  wrong path — a new file at the repo **root** (`index.html`, 797 lines) —
  then deleted (`Delete index.html`), then correctly re-added as 199 new
  lines appended onto the real `static/index.html` (598 → 797 lines),
  both within the same minute, timestamped today. Net effect: the
  live repo's `static/index.html` does genuinely contain the demo panel
  described in the prior handoff; it just took a false start to get
  there. Flagging this because it's a concrete, just-happened instance of
  exactly the upload-path mistake `POLISH_PLAN.md` Phase 0 now warns
  about — the project's actual git history, not a hypothetical.
- Confirmed live (not just claimed): `TRADEMARKS.md` has the
  `sites.google.com/view/gametechsystems/home` framing sentence;
  `CODE_OF_CONDUCT.md`'s enforcement contact points at the GitHub
  Discussions thread, not `ToBeUpdated`. Both matched the prior
  handoff's description exactly.
- **Open decision 2 from the prior handoff is resolved:** `HANDOFF.md`
  is back in the live repo root (`git log -- HANDOFF.md` shows an
  "Add files via upload" commit adding it back, and a byte-for-byte
  `diff` against the version pasted into this chat came back empty). A
  fresh clone is self-sufficient again; no need to source it from
  anywhere else going forward.
- Did **not** attempt to verify the live Render URL
  (`https://holdem-plus-demo.onrender.com/app/`) reflects this repo
  state — `web_fetch` in this sandbox only allows URLs already surfaced
  by a search or a prior fetch, and a search for the exact Render
  subdomain didn't surface it. This session has no more evidence than
  the prior one about whether pushes to `main` currently auto-deploy;
  see `POLISH_PLAN.md` Phase 0.

### What shipped this session

1. **`api.py`** — a persistent, per-hand log, separate from both the
   existing "last finished hand" concept and from the analytics layer:
   - `HandHistoryEntry` (new dataclass): `hand_number`, `small_blind`,
     `big_blind`, the hand's own `HandResult`, and an optional
     `rabbit_hunt` dict filled in later if one gets used.
   - `TableSession.hand_history: List[HandHistoryEntry]` (bounded at the
     new `MAX_HAND_HISTORY = 500`, oldest dropped first) and
     `TableSession.hands_completed: int` (a true lifetime counter that
     keeps incrementing past that bound, so hand numbering never resets
     or repeats once old entries age out).
   - `_record_hand_history_entry()` / `_record_rabbit_hunt_in_history()`
     — called from the exact same call sites
     `_record_analytics_for_completed_hand()` already was (both the REST
     action handler and the WebSocket handler), for the same reason:
     those are the only two places a hand can actually finish. The
     WebSocket `rabbit_hunt` branch previously discarded
     `completed_hand.rabbit_hunt(player_id)`'s return value entirely —
     now captures it (`river = ...`) so it can be recorded.
   - New endpoint: `GET /tables/{table_id}/hands?limit=50` — most-recent-
     first, no per-viewer redaction needed (every card it can return
     already went to a real public showdown, same reasoning
     `_serialize_hand_result` already documented). Returns
     `{"hands": [...], "total_hands_played": N}`. 400 on
     `limit <= 0`, 404 on an unknown table, `{"hands": [], "total_hands_played": 0}`
     (200, not an error) for a real table that just hasn't played a hand
     yet.
   - `_serialize_state()` now always includes `hands_completed` (a plain
     int) so the client can show a log size without a separate round
     trip just to learn it.
2. **`static/index.html`** — a collapsible "Hand history" panel
   (`<details class="panel history-panel">`) below the existing "Table
   activity" log, each hand itself a nested `<details>` row (hand
   number, board, winner — reusing the existing em-dash-separated phrasing
   convention from the last-hand banner) that expands to show revealed
   hole cards (rendered as real mini card sprites via the existing
   `renderCard()` helper, not just text), folded players, and any
   Rabbit Runner outcome. The full list is fetched only while the panel
   is open — opening it, a genuinely new hand finishing while it's
   already open, and a rabbit hunt succeeding while it's open all
   trigger a refresh; a closed panel costs nothing beyond the cheap
   `hands_completed` count that rides along on every existing `/state`
   poll/push. Reuses the established dark-felt/gold theme's CSS
   variables throughout; no new colors or fonts introduced.
3. **`test_api.py`** — 12 new tests: empty-state behavior (both "table
   exists, never started" and "started, no hands yet"), unknown-table
   404, the `hands_completed` counter, multi-hand ordering (proving
   earlier hands' info doesn't disappear once later ones finish — the
   specific report this answers), entry shape (board/payouts/no rabbit
   hunt by default), a fold-without-showdown entry, the `limit` param
   (including rejecting `<= 0`), rabbit hunt reflected into history via
   both REST and WebSocket, and the `MAX_HAND_HISTORY` cap (via
   `monkeypatch`, so it doesn't need to actually play 500 hands).
4. **`README.md`** — new "Hand history" section, file listing and test
   count updated to 218.

**Test suite: 218 passed** (206 prior + 12 new, all in `test_api.py`;
no other module needed changes). Verified three ways, in increasing
order of how close to "real" they get: the full `pytest -q` run; a
live-server smoke test over actual HTTP (`uvicorn` + `curl`, not just
`TestClient`, to rule out anything that only works via in-process ASGI);
and a throwaway Node + jsdom smoke test of the real `static/index.html`
file — mocked `fetch`, dispatched a real `toggle` event on the panel,
and asserted on the resulting DOM (entry count, ordering, board text,
mini `<div class="card">` elements actually present, detail rows for
revealed hands/folded/rabbit-hunt) rather than just checking the script
parses. That jsdom scaffolding (`node_modules`, throwaway `package.json`,
the check script itself) was deleted before finishing up, same as the
prior session did for its own frontend check — not part of the repo.

**This did not include loading the live URL in an actual browser** — see
Section 3. That gap is now unresolved across three consecutive sessions
in a row; `POLISH_PLAN.md` Phase 0 makes it the explicit first item for
whoever picks this up next.

### The two open items from the prior handoff conversation

1. **Entity naming mismatch** (`TRADEMARKS.md`): still open, untouched
   this session — see Section 4.
2. **`HANDOFF.md` absent from the live repo:** resolved (confirmed above,
   independent of this session's own work — it had already been re-added
   before this session started).

---

## 1. What exists right now

Everything from prior sessions, plus the hand-history log:

```
poker_types.py, hand_evaluator.py, betting_state_machine.py,
side_pots.py, tournament_structure.py, tournament_balancing.py
  -> orchestrator.py (Hand + Tournament)
  -> analytics.py (hands/hour, pot-vs-blinds, showdown frequency,
                    hand-strength distribution, player feedback)
  -> demo_showcase.py (two scripted, deterministic showcase hands,
                        built on top of orchestrator.Hand directly)
  -> api.py (REST + WebSocket, /analytics, /feedback, /demo/script,
             /tables/{id}/hands [new])
  -> static/index.html (vanilla JS client, served at /app/: table play,
                         "Watch the demo" teaser + animated playback,
                         and now a collapsible "Hand history" panel)
```

Every module above the API layer is still dependency-free standard-library
Python. Deployment configs are unchanged (`Dockerfile`/`.dockerignore`,
`render.yaml`, `fly.toml`, `Procfile`, `DEPLOYMENT.md`). The live instance
is `https://holdem-plus-demo.onrender.com/app/` — **this session's
changes are not deployed there yet**; see Section 5 / `POLISH_PLAN.md`
Phase 0.

Governance/legal scaffolding unchanged from the prior session: `LICENSE`
(Apache 2.0), `NOTICE`, `TRADEMARKS.md` (bare-URL issue resolved;
entity-naming note still open), `CODE_OF_CONDUCT.md` (contact points at
Discussions), `CONTRIBUTING.md` (DCO-based sign-off flow).

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
- `demo_showcase.py` is deliberately scripted/deterministic, not
  bot-driven; `default_bot_action` is deliberately left unmodified (see
  prior handoff for the full reasoning — still applies unchanged).

New this session:

- **`hand_history` is a third, deliberately distinct thing from two
  concepts that already existed** — see `HandHistoryEntry`'s own
  docstring in `api.py` for the full reasoning, but briefly:
  `last_hand_result`/`last_completed_hand` only ever describe the single
  most-recently-finished hand (by design — that's what made Rabbit
  Runner's timing work in the first place, see the prior handoff's Bug
  3), and `analytics.HandRecord` is aggregate-only with no player
  identities or actual cards (by design — see `analytics.py`'s module
  docstring). Neither was reusable for "let a person look back at what
  happened in hand #12." Don't try to collapse these three into one
  structure later without re-reading why each is shaped the way it is.
- **`hands_completed` is the true lifetime counter; `hand_history`'s
  length is not.** The list is capped (`MAX_HAND_HISTORY`) and drops the
  oldest entry once full; the counter never resets. `hand_number` on a
  retained entry is always meaningful and never reused, even once older
  entries have aged out of the list itself.
- **Rabbit hunt's history mirroring always targets `hand_history[-1]`,
  never looks it up by hand number.** This only works because
  `rabbit_hunt()` itself is already constrained to `last_completed_hand`
  (the single most-recently-finished hand — see that field's own
  long-standing docstring) and both are written from the same handful of
  call sites in the same order. If a future session ever changes rabbit
  hunt to work retroactively on an older hand, this mirroring logic needs
  to change with it, not just the eligibility check.
- **The frontend fetches the history list lazily, on open, not on every
  poll/WS push.** Only the cheap `hands_completed` int rides along on
  every `/state` response unconditionally. Don't change `/state` to
  inline the full hand list "for convenience" — that reintroduces the
  exact unbounded-payload-growth problem the lazy fetch was designed to
  avoid on a long-running table.

---

## 3. What's explicitly NOT built — read this before promising anything

Carried forward (all still true): no real frontend fork, no persistence,
no multi-table routing in the API, no rate limiting/auth beyond opaque
guest IDs, the known engine simplifications documented in their own
modules, the Monte Carlo baseline is Hold'em-only (no single "here's the
delta" endpoint), demo mode is fixed at exactly two hands, and the
`welcome_message.md` draft has still never been posted to GitHub
Discussions.

New from this session — full detail and priority order in
`POLISH_PLAN.md`, summarized here:

- **No pagination in the hand-history UI.** The endpoint accepts
  `limit`; the client always requests the default and has no "load
  older hands" control. Not a problem yet at demo scale; will be the
  moment a table runs past ~50 hands in one sitting.
- **No explicit multi-way side-pot test of the history feature.** Every
  new test this session used heads-up hands. `HandHistoryEntry` wraps
  `HandResult` verbatim, so the risk of it mishandling multiple `Pot`s
  is low, but "low risk" isn't "tested" — see `POLISH_PLAN.md` Phase 1.
- **No real-browser click-through of the new panel** (or of anything
  else — see below). The jsdom check is meaningfully stronger than a
  syntax check but is still not a real browser.
- **This session's changes are not pushed or redeployed.** Same
  "no push credentials / no deploy access from here" limitation every
  prior session has hit.
- **Still no committed frontend test harness.** The jsdom scaffolding
  was, again, created and deleted within this session, purely as
  verification — matching (not improving on) the prior session's own
  practice. A real, repo-committed frontend test setup is still a
  from-scratch addition for whoever eventually wants it enough to own
  the `package.json`/`node_modules` maintenance that comes with it.

---

## 4. Open decisions (not bugs — need a person to decide, not a fix)

1. **Entity naming mismatch** ("GamingTech, LLC" vs. "GameTech Systems"
   in `TRADEMARKS.md`) — still unresolved, now three handoffs running.
2. ~~`HANDOFF.md` absent from the live repo~~ — resolved; see Section 0.
3. **How far to extend demo mode** — no longer just "flagged as an
   option": `POLISH_PLAN.md` Phase 2 has a concrete plan for a third,
   side-pot-focused showcase hand, sequenced right after the multi-way
   test work Phase 1 already needs to do anyway. Still needs someone to
   actually pick it up.

---

## 5. Fastest path from here forward

Full detail, in order, with definitions of done, is in
`POLISH_PLAN.md`. Short version:

1. **Phase 0 — get this session's changes live, then finally do the
   real-browser click-through** every prior session has flagged and
   none has closed. This is the loudest recommendation in this document.
2. **Phase 1** — hand-history pagination, a failure state for a bad
   fetch, and the multi-way side-pot test the feature is still missing.
3. **Phase 2** — the third (side-pot) demo showcase hand, using the
   rigged deck Phase 1's test work already needs to build.
4. **Phase 3** — an actual visual surface for `/analytics`, which has
   returned real numbers since the analytics session and has never been
   looked at by a human anywhere but raw JSON.
5. **Phase 4+** — the real frontend fork (PokerTH web client or similar)
   the tech plan has recommended since Section 3.2 and every handoff
   since has called "the biggest lever," still not started. Its own plan,
   not a bullet here, whenever someone actually commits to it.

---

## 6. If you're a fresh Claude session picking this up

**Read Section 0 in full, then verify it yourself before trusting it —
including this version.** `git clone
https://github.com/GameTech-Systems/holdem-plus` was reachable from this
sandbox's network allowlist again this session, worked cleanly, and
caught real drift (the pasted-chat-snapshot staleness, and the
just-happened upload-path mistake, both described above) that trusting
either the chat attachments or a handoff doc's prose alone would have
missed. Clone it. Don't assume anything in this file is still true
without checking, the same way this session didn't assume the prior
file was.

Run `pytest -q` first thing; the baseline as of this session is **218
passed**.

Standing advice, now stated for the fourth time because it keeps not
happening: don't stop at "the code exists, the tests pass, it looks
right in isolation, and a jsdom check didn't throw." Load the actual
live URL and click through real behavior in a real browser before
calling anything shipped. Every session so far has gotten a little
closer (syntax check → jsdom click-through → jsdom click-through of a
second feature) without ever actually clearing the bar. Whoever picks
this up next should be the one who finally does.
