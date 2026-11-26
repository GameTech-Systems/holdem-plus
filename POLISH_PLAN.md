# Hold'em Plus: Polish Plan

A prioritized backlog for taking this demo from "the engine and API are solid, the UI works" to "good enough to
hand a casino or poker-room contact without caveats". Each phase is sized for roughly one 5-hour session, is
independently shippable, and ends with `bash sim/run_checks.sh py` passing and a short note in `HANDOFF.md`.

Read `ORIENTATION.md` first, then `HANDOFF.md` for what already exists. This file is forward-looking.

**Ground rule, stated bluntly because it keeps not happening:** nothing here is "done" until someone loads the
deployed URL in a real browser and clicks through it. Several sessions have shipped real, tested code without
clearing that bar.

*Restored 2026-11-25: this file was deleted on 2026-09-11 (commit `dab98db`) and not re-added. Shipped work below
is summarized; the long write-ups are in git history (`git show dab98db^:POLISH_PLAN.md`).*

---

## Phase 0: get the pending work live, then clear the browser bar

- [ ] Apply the 2026-11-25 update (steps in `HANDOFF.md` section 1): workflow files by hand, then the zip.
- [ ] Run the "Equity simulation" workflow once on GitHub and confirm it is green.
- [ ] Load the deployed URL in a real browser and click through, at minimum:
  - seat two tabs at a table, play a hand to completion, open "Hand history", use Rabbit Runner once and confirm it
    shows in the last-hand banner and the history log; watch the scripted demo end to end, including "Hands
    played so far";
  - face a bet or raise as the non-acting player and confirm its size is legible on the felt; fold a hand and let
    the next play deep before checking the rabbit-hunt banner still reads clearly;
  - force a preflop all-in (shallow stacks make this reliable) and confirm hole cards, flop, 3rd hole card, turn
    and river each reveal with a visible pause, then a showdown beat that names each hand and highlights the
    winner; confirm a normally paced showdown also gets the beat; click Skip mid-reveal and confirm a clean end
    state; confirm the hand-history rows show descriptions with the winner distinguished;
  - check seat layout at **4+ and 6+ seats**: the per-seat description line has only been checked structurally and
    could crowd a seat;
  - **Strategy Guide** (`/app/strategy.html`): phone and desktop, every chart view, the heads-up and 6-handed
    switch, the "Show the chart data as a table" disclosure, and the longer odds cells on the 3-card tab at phone
    width.
- [ ] Docs-only decisions: the `TRADEMARKS.md` entity-name mismatch ("GamingTech, LLC" vs "GameTech Systems"), and
  posting `welcome_message.md` to GitHub Discussions (drafted across many sessions, never posted).

**Done when:** the live URL reflects the latest work, someone has personally clicked through the items above, and
the docs-only items are resolved or explicitly deferred with a reason.

---

## Phase 0.5: hand reveal and showdown sequence (code shipped; browser check pending)

**Why:** when no further betting is possible (most commonly both players shove preflop), `Hand._progress()` races
through every street inside one request, so a client only ever sees the finished hand. Real poker clients pace
this out because that pacing is the drama of an all-in. Target sequence: all-in hole cards revealed, beat, flop,
beat, 3rd hole card, beat, turn, beat, river, then a showdown beat naming each hand and marking the winner.

**Not a reason to fork PokerTH.** The 3rd-hole-card beat is Hold'em Plus's own rule, so a forked 7-card client would
need this sequencing written from scratch anyway, on top of a protocol integration and an AGPL/GPL review.

- [x] **0.5a** `Hand.runout` / `RunoutStep` in `orchestrator.py`, serialized on `last_hand` and every history entry.
- [x] **0.5b** `describe_hand_rank()` and `hand_descriptions` on the same payloads (winner is read from `payouts`,
  no separate flag).
- [x] **0.5c** Felt-side replay and showdown beat in `static/index.html`, with Skip. jsdom-verified only.
- [ ] **Real-browser watch-through** (Phase 0 list above). Until then this phase is **not** done.

---

## Phase 1: hand-history follow-through

- [ ] Pagination in the UI ("show 50 more"; the endpoint already takes `limit`).
- [ ] A failure state for `refreshHandHistory()` (it currently swallows errors and can sit on the empty
  placeholder forever).
- [ ] A rigged 3+ player side-pot test through the real API/history path (a forced short-stack all-in producing
  more than one `Pot` with different winners per pot), in the style of `_build_rigged_heads_up_deck`.

**Done when:** that test passes, the panel answers "more than 50 hands" and "the fetch failed", and it has been seen
working in a browser.

## Phase 2: third showcase hand (side pots)

- [ ] A third `DemoHand` in `demo_showcase.py`: 3 to 4 seats, one short stack all-in, a genuine main pot and side
  pot with different winners, narration clear enough for someone who has never seen a side pot.
- [ ] `test_demo_showcase.py` coverage at the rigor of the existing two hands; teaser copy and README say "three".
- [ ] Check the `.demo-seat` layout is not cramped at 4 seats.

## Phase 2.5: Strategy Guide follow-ups (new)

From the outside audit (`docs/AUDIT_2026-11.md`, "Still open"). Ordered by value for effort:

- [ ] **Link the pages to each other.** `/app/` does not link to `/app/strategy.html` and vice versa. Small edit to
  both; needs the browser check.
- [ ] **Conditional third-card calculator**: pick your two cards and the flop, get the exact chance the plus card is
  each kind of out (`sim/third_card_odds.py` already enumerates this; the page needs a small client-side version).
- [ ] A worked example of one hand before and after the plus card, a short glossary, and one consistent term for the
  third card.
- [ ] Position-aware, fold-equity, multi-street simulation as a **separate** program beside the equity simulator
  (which stays the simple, auditable baseline). Only then revisit the opening ranges and tiers, which are
  provisional judgment today.
- [ ] Exact Hold'em Plus equity benchmark: full enumeration is infeasible (about 2 billion boards for AA alone);
  consider exact hand-versus-hand benchmarks on a restricted deck instead.

## Phase 3: analytics, visualized

`/tables/{id}/analytics` returns real numbers (hands/hour, pot in big blinds, showdown frequency, category
distribution against a standard-Hold'em baseline, thumbs feedback) and nothing displays them.

- [ ] A read-only panel or `static/analytics.html` showing those numbers, with the category distribution against
  `standard_holdem_baseline` given the most visual weight (it is the hypothesis test from the tech plan).
- [ ] No charting dependency: `<div>` bars or inline SVG are enough.

**Done when:** one screen answers "is Hold'em Plus producing bigger, more varied hands than standard Hold'em at
this table" without reading JSON.

## Phase 4+: the bigger bet

Forking a mature open-source client (PokerTH's web client, or a lighter one) for the table UI, per the tech plan's
Section 3.2. A multi-session commitment with its own integration layer and licensing review; deserves its own plan
if it is ever started. Also open, lower urgency: no persistence (a restart loses every table), no multi-table
routing in the public API, no rate limiting or abuse protection on a public unauthenticated demo.
