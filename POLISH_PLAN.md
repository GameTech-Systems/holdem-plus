# Hold'em Plus — Polish Plan

**Purpose:** a prioritized, session-sized backlog for taking this demo
from "the engine and API are solid, the UI works" to "genuinely good
enough to hand a casino or poker-room contact without caveats." Written
assuming whoever executes a phase — human or a fresh Claude session — has
roughly a 5-hour working window and will hand off to the next phase
rather than trying to do everything in one sitting. Each phase is scoped
to fit that window, is independently shippable, and ends with `pytest -q`
passing and a short handoff note appended to `HANDOFF.md`.

Read `HANDOFF.md` first for what already exists and what's already been
tried. This document is the forward-looking backlog; `HANDOFF.md` is the
record of what happened.

**Ground rule carried over from every session so far, stated bluntly
because it keeps not happening:** nothing here is "done" until someone
loads the actual deployed URL in a real browser and clicks through it.
Three sessions in a row have shipped real, tested, working code and
still not cleared that bar. Don't let phase 4 become a fourth.

---

## Phase 0 — Ship what's sitting here, then finally clear the browser bar

**Why first:** everything below this compounds on top of code that
exists locally/in the Claude Project but has a history of drifting from
what's actually live (see `HANDOFF.md` Section 0 for a concrete instance
of exactly that happening between two recent sessions). Closing that gap
once, deliberately, is worth more than any single new feature.

- [ ] Push this session's three changed files (`api.py`,
      `test_api.py`, `static/index.html`) plus the two new docs
      (`README.md` update, this file, the refreshed `HANDOFF.md`) to
      `github.com/GameTech-Systems/holdem-plus`. No Claude sandbox in
      this project's history has had push credentials — this step needs
      a human. Given how the last few commits actually happened (GitHub
      web UI "Add files via upload," not a git push), the fastest path
      is probably the same: upload `static/index.html` into the
      **`static/` folder specifically** — the repo's own history shows
      this exact file was accidentally uploaded to the repo root once
      already and had to be deleted and re-added correctly.
- [ ] Confirm the Render service actually redeploys on push (check
      Render's dashboard for auto-deploy settings) or trigger a manual
      deploy. Nothing in this repo's history confirms one way or the
      other whether pushes to `main` currently reach
      `https://holdem-plus-demo.onrender.com/app/` automatically.
- [ ] Once deployed: load that URL in a real browser (not curl, not
      jsdom) and click through, at minimum: seat two browser tabs at a
      table, play a hand to completion, open the new "Hand history"
      panel and confirm it populates, use Rabbit Runner once and confirm
      it shows up both in the last-hand banner and in the history log,
      and watch the scripted demo end to end. Fix anything that looks
      wrong before telling anyone outside the project it's ready.
- [ ] While there: decide the two standing open items from `HANDOFF.md`
      Section 4 that don't need code —
      the `TRADEMARKS.md` entity-naming mismatch ("GamingTech, LLC" vs.
      "GameTech Systems"), and posting `welcome_message.md`'s content to
      the GitHub Discussions thread (still just sitting as drafted text).

**Definition of done:** the live URL genuinely reflects this session's
work, someone has personally clicked through it, and the two docs-only
open items are either resolved or explicitly deferred with a reason.

---

## Phase 1 — Hand-history follow-through

The log itself shipped this session (`GET /tables/{id}/hands`, the
collapsible panel in `static/index.html`, 12 new tests). What didn't:

- [ ] **Pagination in the UI.** The endpoint already accepts `limit`;
      the frontend always requests the default (50) and has no "load
      older hands" control. Add one once a real table plausibly runs
      past 50 hands — a simple "show 50 more" button that requests
      `limit=` a running total and re-renders is enough; no need for
      real cursor-based pagination on a table this size.
- [ ] **Failure state.** `refreshHandHistory()` currently swallows a
      failed fetch silently (`catch (e) { /* leave the panel as-is */ }`)
      — fine as a default (don't blow away a working list over a
      transient network blip), but the panel should show *something* if
      it's never successfully loaded at all, rather than sitting on the
      static "Hands will show up here" placeholder forever.
- [ ] **Multi-way side-pot coverage.** Every hand-history test this
      session used heads-up hands. The feature reuses `HandResult`
      verbatim, so risk is low, but nothing specifically confirms a
      3+ way all-in with multiple side pots (`side_pots.compute_side_pots`
      producing more than one `Pot`) records and serializes correctly
      into a `HandHistoryEntry` and renders sensibly in the panel (in
      particular: a pot where the eligible winners differ pot-to-pot,
      like `test_side_pot_awarded_separately_from_main_pot` in
      `test_side_pots.py`, but exercised through the actual API/history
      path rather than the engine directly). A rigged deck in the style
      of `test_orchestrator._build_rigged_heads_up_deck` or
      `demo_showcase._build_scripted_deck`, extended to 3+ players with
      a forced short-stack all-in, is the way to get this
      deterministically rather than hoping blind-pressure produces one.
- [ ] Real-browser check specifically of the panel (folds into Phase 0's
      click-through, but call it out explicitly so it isn't skipped).

**Definition of done:** a rigged multi-way side-pot test exists and
passes, the panel has a real (even if simple) answer for "more than 50
hands" and "the fetch failed," and it's been seen working in a browser.

---

## Phase 2 — The third showcase hand (side pots)

Flagged as an open decision in the prior `HANDOFF.md` (Section 4, item
3) and still not built. Now that Phase 1 forces a rigged multi-way
side-pot deck to exist anyway, this is a natural, low-marginal-cost
follow-on rather than a separate investigation.

- [ ] Build a third `DemoHand` in `demo_showcase.py`: 3–4 seats, one
      short stack forced all-in, at least one other player continuing
      to bet after — enough to produce a genuine main pot + side pot
      split with different winners at each layer (mirror
      `test_side_pots.test_side_pot_awarded_separately_from_main_pot`'s
      setup for the actual chip math, then script the corresponding
      hole cards/actions against it via `_build_scripted_deck`).
- [ ] `test_demo_showcase.py`: category/payout correctness for the new
      hand, same rigor as the existing two (chip conservation, board-
      reveal staging, determinism).
- [ ] `api.py` / `static/index.html`: `/demo/script` already returns a
      list, and the demo panel already iterates it generically — a third
      entry should Just Work, but confirm the demo-seats layout
      (`--demo-seat` flexbox) doesn't get cramped at 4 seats, and that
      the narration makes the side-pot mechanic legible to someone who's
      never seen one (this is the one place in the whole demo where a
      plain-English explanation earns its keep more than a UI treatment
      would).
- [ ] Update `README.md`'s "Watch the demo" section and the teaser copy
      in `static/index.html` (`#demo-teaser p`) to mention three hands,
      not two.

**Definition of done:** `/demo/script` returns three hands, the third
demonstrably shows a main-pot/side-pot split with different winners, and
it's been watched end-to-end in a real browser.

---

## Phase 3 — Analytics, visualized

`/tables/{id}/analytics` has returned real numbers (hands/hour, pot size
in big blinds, showdown frequency, category distribution vs. a standard-
Hold'em baseline, player feedback) since the analytics session, and
nothing has ever displayed them anywhere a person would look. This is
explicitly called out as a "longer-standing priority" in the prior
`HANDOFF.md` (Section 5, item 6) and has been carried forward, unbuilt,
across at least two sessions now.

- [ ] A read-only panel or separate page (`static/analytics.html`, or a
      tab within the existing page — either is fine, pick based on how
      much you want it competing for attention with the live table) that
      polls `/analytics` and renders: hands/hour as a number, pot-in-BB
      as a number, showdown frequency as a percentage, and the category
      distribution as a simple bar comparison against
      `standard_holdem_baseline` — this last one is the actual
      hypothesis-testing payoff from the tech plan (Section 3.3) and
      deserves the most visual weight, not the least.
- [ ] No new charting dependency needed — this project has stayed
      dependency-free above the API layer on principle (see multiple
      module docstrings); a couple dozen `<div>`s with `width: X%`
      inline styles, or a small inline `<svg>`, does a bar comparison
      fine without pulling in a charting library. If a future session
      disagrees and wants something richer, that's a deliberate
      dependency decision to make consciously, not default into.
- [ ] Feed the thumbs-up/down feedback tally in too — it's already in
      the `/analytics` response and currently invisible anywhere.

**Definition of done:** a person can look at one screen and answer "is
Hold'em Plus actually producing bigger/more varied hands than standard
Hold'em at this table" without reading raw JSON.

---

## Phase 4+ — The bigger bet, not a single session

Everything above is incremental polish on the existing custom
engine + vanilla-JS client. The tech plan's own Section 3.2 recommended
forking a mature open-source poker client (PokerTH's web client, or
`bocaletto-luca/Texas-Holdem` as a lighter alternative) rather than
hand-building table UI indefinitely, and every handoff since has
repeated some version of "this is still the biggest lever for a
casino/poker-room contact taking the demo seriously" without anyone
actually starting it. That's a multi-session commitment on its own —
new UI framework, a real integration layer between the fork and this
project's WebSocket/REST API, almost certainly its own licensing
homework (`static/index.html`'s current from-scratch client sidesteps
the AGPL/GPL questions `LICENSE`/`TRADEMARKS.md` already flag for that
path) — and deserves its own dedicated plan once someone actually
decides to start it, not a bullet point at the bottom of this one.

Also still open, lower urgency than the above but real: no persistence
(`TABLES`/`GUESTS` are in-memory, single-process — a restart loses every
table), no multi-table routing in the public API (`Tournament` supports
it internally; `api.py` deliberately doesn't expose it yet), no rate
limiting or abuse protection on a fully public, unauthenticated demo.
None of these block a "let people try Hold'em Plus" pitch; they'd matter
a lot the moment this stops being a small-scale demo.
