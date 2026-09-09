# Hold'em Plus — Session Handoff

**Purpose of this document:** you're picking this up cold, either as the next
Claude session or a human developer. This tells you exactly what exists,
what's been verified, what's deliberately left undone, and the fastest path
from here forward. It supersedes the previous `HANDOFF.md` — that version's
Section 0 (the hand-history-log session) is now historical background; see
Section 0 below for the current state instead.

Start with `README.md` for how to run things and `POLISH_PLAN.md` for the
forward-looking backlog. This document is about *state and decisions*.

---

## 0. Status as of the most recent session — read this first

This session's brief came directly from the person playing the live demo
(via chat, with screenshots), not from `POLISH_PLAN.md`'s own phased
backlog: three real bugs found by actually clicking around the deployed
table and the "Watch the demo" panel. This document covers the fixes for
those three; the phased backlog in `POLISH_PLAN.md` (hand-history
pagination, the third side-pot showcase hand, analytics visualization,
the PokerTH-fork bet) is untouched and still exactly where the prior
session left it.

**Verified the live repo directly before touching anything** — same
practice every prior session has recommended, and this time it paid off
differently than usual: `git clone github.com/GameTech-Systems/holdem-plus`
succeeded (reachable from this session's sandbox, same as prior sessions
found), and every file in it — engine modules, tests, `api.py`,
`static/index.html`, `HANDOFF.md`, `POLISH_PLAN.md`, `README.md`, all of
it — came back **byte-for-byte identical** to what was pasted into this
chat as attachments. Confirmed with full-file diffs on the engine/test
layer and fingerprint greps on the docs and the three files this session
changed. Unlike the session that found stale attachments, there was no
drift to correct here — just a normal starting point. Worth still doing
this check every time rather than assuming it based on a good outcome
once.

**`pytest -q` on the pasted/live snapshot: 218 passed**, confirming the
baseline the prior `HANDOFF.md` stated.

### The three bugs, and what turned out to be true about each

1. **"The rabbit hunt option remains after the hand completes and a new
   hand is dealt. I clicked rabbit hunt on a hand that was fully dealt
   (5 community cards already showing), but it revealed the river card
   from the previous hand."**

   This is **working as designed, not a logic bug** — but the design was
   never labeled clearly enough, and that's a real usability bug worth
   fixing on its own. `last_hand_result` / `last_completed_hand` (and any
   rabbit-hunt offer riding along with them) are documented, on purpose,
   to stay valid for the **entire duration of the next hand**, not just
   until that next hand's board fills up — see `last_completed_hand`'s
   own docstring in `api.py`, which this session left unchanged. That
   next hand can perfectly normally reach a full 5-card board of its own
   while still just being *in progress* (river betting, not yet
   complete), and the "Last hand" banner sitting above the felt was
   giving no indication that it was still talking about an older,
   already-finished hand rather than the live one underneath it. That's
   exactly the confusion in the report. Traced through the reported
   scenario against `api.py`/`orchestrator.py` line by line before
   concluding this — didn't want to paper over an actual eligibility bug
   with a labeling fix, so this took the most verification time of the
   three.

   **Fix, scoped to stay a UI clarity change and not touch the
   documented eligibility window:**
   - `_serialize_hand_result()` (`api.py`) now also returns
     `hand_number` (the same `session.hands_completed` value the
     persistent hand-history log already numbers that hand by), so the
     client can label the banner unambiguously and cross-reference it
     against `/tables/{id}/hands`.
   - `static/index.html`'s banner now reads "Hand #N (previous): ..."
     instead of "Last hand: ...", says "that hand's board:" instead of
     just "board:", and — specifically when a rabbit-hunt offer is
     showing — adds an explicit line underneath the button: *"This is
     the hand that just finished — not the one in progress below."*
     The button itself also gets a `title` tooltip repeating that.
   - Did **not** change when the offer expires. If a future session
     wants to change that (e.g. auto-hide once the live hand's own board
     hits 5 cards), that's a deliberate behavior change to make on
     purpose, not a side effect of a labeling fix — see
     `TableSession.last_completed_hand`'s docstring for why the current
     window is a full hand's length by design.

2. **"When a bet is made, the opponent isn't shown the bet amount, just
   provided the option to call/raise/fold."**

   This one **was** a real gap, and it wasn't just a frontend styling
   problem — `api.py`'s live `hand` payload never sent the bet size
   anywhere at all. There was no `current_bet`, no `pot_total`, and no
   per-player "how much have they put in this street" field for the
   frontend to have rendered even if it had wanted to. An opponent
   facing a raise had genuinely no way to see its size from the API
   response, full stop.

   **Fix:**
   - `api.py`'s live `hand` payload gained three fields: `current_bet`
     (the amount every player on the current street needs to match,
     gated the same way `Hand.current_actor_id` already gates on
     `BETTING_STREETS`), `pot_total` (everything committed to the pot so
     far this hand, across every street), and, per player,
     `bet_this_street` (`PlayerState.committed_this_street`, unredacted
     for every viewer — this is public information at a real table, the
     same way stack size already was).
   - `static/index.html`: each seat now shows a `Bet: N` line when
     nonzero; the pot line now reads `Blinds X/Y · Pot: Z`; the "waiting
     on…" and "your turn" hints now say `Current bet: N (M to call)`;
     and the CALL button's label becomes `call M` instead of a bare
     `call` once there's actually something to call.
   - New tests in `test_api.py`: `test_live_hand_reports_current_bet_and_pot_total_preflop`,
     `test_bet_amount_is_visible_to_the_non_acting_player` (raises to 20,
     asserts the *other* player's view shows `current_bet: 20` and the
     actor's `bet_this_street: 20`), and
     `test_bet_this_street_resets_between_streets`.
   - Verified over a real HTTP round trip (not just `TestClient`) with a
     live `uvicorn` process and `requests`, not only via pytest — see
     Section 2 below for the exact numbers.

3. **"On 'watch demo,' the first hand goes quick and disappears after the
   2nd hand is dealt. It'd be nice to have that history accessible,
   similar to the real game's collapsible box."**

   Confirmed by reading `playDemoScript()`: it wipes `#demo-log`'s
   `innerHTML` at the start of every hand in the script, with nothing
   anywhere retaining the previous hand's narration once that happens.
   Exactly the reported behavior, and there was no history object for it
   at all going into this session — this needed building from scratch,
   not patching.

   **Fix:** `static/index.html`'s demo panel gained a
   `demoHandHistory` array (JS-only, scoped to the current "Watch the
   demo" run-through — this data was never going to survive a page
   reload, and it doesn't need to) and a collapsible
   `<details id="demo-history-panel">` panel, reusing the exact same
   `.history-entry` / `.history-detail` / `.history-row` /
   `historyRow()` / `historyCards()` CSS classes and helper functions the
   real table's hand-history panel already used — no new CSS needed
   beyond a couple of spacing rules for the nested-panel case. Each
   showcase hand, once its playback finishes, gets archived with its
   title, final board, payout, both players' revealed hole cards, any
   rabbit-hunt line, and the **full play-by-play narration transcript**
   (every `DemoEvent.narration` in order) inside the expandable row —
   more detail than the real game's history panel shows, since a
   `DemoHand`'s entire `events` array is already fully known up front
   (nothing to fetch), unlike the real game's history which is
   necessarily summary-only over the network.

### How this session verified the frontend changes (no real browser here either — see Section 3)

Same limitation every session has had: no way to open a real browser
from this sandbox. What this session did instead, in increasing order of
rigor:
1. Extracted the `<script>` block and ran `node --check` on it — plain
   syntax validation, catches nothing behavioral.
2. Built a throwaway `jsdom` scaffold (same tool, same "build it, use
   it, delete it before finishing" discipline the two prior frontend
   sessions used) that loaded the real `static/index.html` via
   `JSDOM(..., { runScripts: "dangerously" })` and called the actual
   `render()`, `renderSeats()`, `renderActions()`,
   `renderLastHandBanner()`, and `renderDemoHandHistory()` functions
   directly with hand-built state objects mirroring exactly what
   `api.py` now sends, then asserted on the resulting DOM: the pot line,
   the per-seat bet amounts, the CALL button's label, the banner's exact
   wording (hand number + "that hand's board" + the "not the one in
   progress below" clarifying line + a working rabbit-hunt button), and
   the demo history entry's title/payout/narration/hole cards. All
   assertions passed after fixing one real thing this caught early: a
   stray `#` where a `//` belonged inside a JS comment block, which
   would have been a silent syntax error in a real browser too (`node
   --check` had already caught the general shape of that, but the jsdom
   pass is what actually exercised the surrounding code paths).
   Deleted the scaffold (`node_modules`, `package.json`, the script
   itself) before finishing, per the standing practice — not part of the
   repo.
3. Also drove the *backend* half of bug 2 over a real HTTP round trip —
   an actual `uvicorn` process on a local port, hit with `requests` (not
   `TestClient`), confirming `current_bet`/`pot_total`/`bet_this_street`
   come back correctly shaped over the wire, not just through in-process
   ASGI. Output, for the record: preflop heads-up showed
   `current_bet: 2`, `pot_total: 3` (sb 1 + bb 2); after the acting
   player raised to 25, the *other* player's own `/state` call showed
   `current_bet: 25` and the actor's `bet_this_street: 25`.

**This still isn't a real browser.** Whoever picks this up next and can
actually load the deployed URL should specifically re-check: the
rabbit-hunt banner wording reads naturally (not just structurally
correct) once you've actually folded a hand and watched the next one
play out under it; the bet amounts render legibly at actual seat-box
size on the felt, not just present in the DOM; and the demo history
panel's nested `<details>` rows don't look cramped next to the existing
outer panel border. None of these are things a jsdom assertion can
tell you.

### Test suite

**222 passed** (218 prior + 4 new, all in `test_api.py`; no other test
file needed changes — the fixes were additive fields/markup, not
behavior changes to anything the existing 218 tests already covered).
`example_usage.py`, all engine modules, and every other test file are
untouched and still byte-identical to the live repo.

### What did NOT change this session

- The rabbit-hunt eligibility *window* itself (still the full next
  hand's duration, by design — see bug 1's writeup above).
- Anything in `orchestrator.py`, `betting_state_machine.py`,
  `side_pots.py`, `hand_evaluator.py`, `poker_types.py`,
  `tournament_structure.py`, `tournament_balancing.py`,
  `analytics.py`, or `demo_showcase.py`. All three bugs were fully
  addressable at the `api.py` serialization layer and the
  `static/index.html` rendering layer; nothing about the actual game
  logic was wrong.
- `POLISH_PLAN.md`'s phased backlog (Phase 1 pagination/multi-way-pot
  test, Phase 2 third showcase hand, Phase 3 analytics visualization,
  Phase 4+ the PokerTH fork) — see that file for the one line this
  session did touch (the Phase 0 auto-deploy checkbox, next section).

---

## 1. Deployment note from this session

The person running this project confirmed directly (not something this
session could verify itself): **Render does auto-deploy on every push to
`main`.** This resolves the open question `POLISH_PLAN.md` Phase 0 and
the prior `HANDOFF.md` both flagged ("nothing in this repo's history
confirms one way or the other whether pushes to `main` currently reach
the live URL automatically"). `POLISH_PLAN.md`'s Phase 0 checklist has
been updated to reflect this — see that file. Practically: once
`api.py`, `test_api.py`, `static/index.html`, and `README.md` from this
session are pushed to `main`, the live demo should update on its own,
no manual redeploy step needed.

Same limitation as every prior session on the push itself: this sandbox
has no push credentials for `github.com/GameTech-Systems/holdem-plus`
(it *can* read the repo, which is how Section 0's verification above
happened, but reading and writing are different permissions and only
the former is available here). A human still needs to actually commit
these four files.

---

## 2. What exists right now

Unchanged from the prior handoff except the four files this session
touched:

```
poker_types.py, hand_evaluator.py, betting_state_machine.py,
side_pots.py, tournament_structure.py, tournament_balancing.py
  -> orchestrator.py (Hand + Tournament)
  -> analytics.py (hands/hour, pot-vs-blinds, showdown frequency,
                    hand-strength distribution, player feedback)
  -> demo_showcase.py (two scripted, deterministic showcase hands,
                        built on top of orchestrator.Hand directly)
  -> api.py (REST + WebSocket, /analytics, /feedback, /demo/script,
             /tables/{id}/hands, and -- new this session -- current_bet /
             pot_total / bet_this_street on the live hand payload, and
             hand_number on last_hand)
  -> static/index.html (vanilla JS client, served at /app/: table play,
                         bet/pot visibility on every seat, a clearly-
                         labeled previous-hand/rabbit-hunt banner,
                         the collapsible real-table "Hand history" panel,
                         and -- new this session -- a matching
                         collapsible history panel inside the demo)
```

Changed this session: `api.py`, `static/index.html`, `test_api.py`,
`README.md` (test count + three short new sections documenting the
fixes), `POLISH_PLAN.md` (one checkbox). Everything else — every other
module, every other test file, `example_usage.py`, all governance/
deployment docs — is untouched and confirmed byte-identical to the live
repo (see Section 0).

The live instance is `https://holdem-plus-demo.onrender.com/app/` —
**this session's changes are not deployed there yet**; see Section 1.

---

## 3. What's explicitly NOT built — read this before promising anything

Carried forward, all still true: no real frontend fork, no persistence,
no multi-table routing in the API, no rate limiting/auth beyond opaque
guest IDs, the known engine simplifications documented in their own
modules, the Monte Carlo baseline is Hold'em-only, demo mode is fixed at
exactly two hands (the third, side-pot-focused one is still
`POLISH_PLAN.md` Phase 2, unstarted), no hand-history pagination in the
UI (`POLISH_PLAN.md` Phase 1), and `welcome_message.md`'s content has
still never been posted to GitHub Discussions.

New from this session:

- **No real-browser click-through of any of the three fixes** — see
  Section 0's verification writeup for exactly what substitute
  verification was done instead (jsdom + a live HTTP round trip), and
  what it can't tell you.
- **The rabbit-hunt banner's clarity fix is a labeling change, not a
  timing change.** If user feedback after this ships says the banner is
  *still* confusing even with the new wording, the next lever to pull is
  changing when it disappears (e.g., tying it to the live hand reaching
  a certain point rather than only to the live hand *completing*) — but
  that's a deliberate behavior change against a documented design
  decision, not a follow-on tweak to make lightly. Read
  `TableSession.last_completed_hand`'s docstring in `api.py` in full
  first.
- **`bet_this_street` and `current_bet` are not retroactively available
  in `/tables/{id}/hands` (the persistent hand-history log) or in the
  demo script** — they only exist on the *live* hand payload, which is
  the only place they were ever missing/needed. A finished hand's
  history entry has no ongoing "current street" to report a bet against,
  so this isn't a gap, just worth being explicit about scope.
- **This session's changes are not pushed or redeployed** — see Section 1.

---

## 4. Open decisions (not bugs — need a person to decide, not a fix)

1. **Entity naming mismatch** (`TRADEMARKS.md`) — still unresolved, now
   four handoffs running. Untouched again this session; nobody has
   picked this up despite `POLISH_PLAN.md` Phase 0 listing it as a
   quick, code-free decision.
2. ~~Does Render auto-deploy on push to `main`?~~ — resolved this
   session; see Section 1.
3. **How far to extend demo mode** — still `POLISH_PLAN.md` Phase 2's
   concrete, unstarted plan for a third (side-pot) showcase hand.

---

## 5. Fastest path from here forward

1. **Push `api.py`, `static/index.html`, `test_api.py`, `README.md`,
   and `POLISH_PLAN.md` from this session to `main`.** Given the
   auto-deploy confirmation in Section 1, this alone should get the
   fixes live without a separate manual deploy step — but confirm the
   live URL actually reflects them afterward (see next item), since
   this session has no way to check that itself.
2. **Finally do the real-browser click-through every prior session has
   flagged and none has closed** — now five bug-fix/feature sessions in
   a row without one. Specifically for this session's changes: fold a
   hand on the turn, let the next hand play deep into its own board, and
   confirm the rabbit-hunt banner's new wording actually reads clearly
   in the moment rather than just passing a jsdom assertion; face a
   raise as the non-acting player and confirm the bet amount is legible
   at real seat-box size; and watch the full demo end to end, then open
   the new "Hands played so far" panel and confirm both showcase hands'
   transcripts are there and readable.
3. **`POLISH_PLAN.md` Phase 1** — hand-history pagination, a fetch-
   failure state, and the multi-way side-pot test the feature is still
   missing. Untouched this session, still next in line per that
   document's own ordering.
4. **`POLISH_PLAN.md` Phase 2** — the third (side-pot) demo showcase
   hand. Also untouched.
5. **Phase 3 / Phase 4+** — analytics visualization, then the real
   frontend fork. Also untouched, same as every session before this one.

---

## 6. If you're a fresh Claude session picking this up

Clone `https://github.com/GameTech-Systems/holdem-plus` and diff it
against whatever's pasted into your chat before trusting either one —
this session did, and for once found no drift at all (see Section 0),
but that's not a reason for the *next* session to skip the check; it's
one data point, not a new standing guarantee.

Run `pytest -q` first thing; the baseline as of this session is **222
passed**.

If your task also touches the frontend: build the jsdom scaffold the
same way this session did (`JSDOM(html, { runScripts: "dangerously" })`,
call the real render functions directly with hand-built state objects,
assert on the resulting DOM, delete the scaffold before finishing). It's
meaningfully better than a syntax check and catches real mistakes (this
session's stray `#`-instead-of-`//` typo, for instance) without needing
a real browser. It is still not a substitute for one — the standing
advice from every prior handoff about actually loading the live URL
applies here exactly as much as it always has.
