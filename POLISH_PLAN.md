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
Several sessions in a row have shipped real, tested, working code and
still not cleared that bar. Don't let the next phase become another one.

---

## Phase 0 — Ship what's sitting here, then finally clear the browser bar

**Why first:** everything below this compounds on top of code that
exists locally/in the Claude Project but has a history of drifting from
what's actually live (see `HANDOFF.md` Section 0 for a concrete instance
of exactly that happening between two recent sessions). Closing that gap
once, deliberately, is worth more than any single new feature.

- [ ] Push the currently-pending session's changed files
      (`api.py`, `test_api.py`, `static/index.html`, `README.md`, and
      this file) to `github.com/GameTech-Systems/holdem-plus`. No Claude
      sandbox in this project's history has had push credentials — this
      step needs a human. Given how the last few commits actually
      happened (GitHub web UI "Add files via upload," not a git push),
      the fastest path is probably the same: upload `static/index.html`
      into the **`static/` folder specifically** — the repo's own
      history shows this exact file was accidentally uploaded to the
      repo root once already and had to be deleted and re-added
      correctly.
- [x] ~~Confirm the Render service actually redeploys on push (check
      Render's dashboard for auto-deploy settings) or trigger a manual
      deploy.~~ **Resolved:** confirmed directly by the person running
      this project that Render auto-deploys on every push to `main` --
      see `HANDOFF.md`'s "Deployment note from this session" section.
      No manual deploy step needed once a push actually happens; the
      remaining gap is purely "has anyone pushed yet" (previous
      checkbox), not "will it go live once pushed."
- [ ] Once deployed: load that URL in a real browser (not curl, not
      jsdom) and click through, at minimum: seat two browser tabs at a
      table, play a hand to completion, open the new "Hand history"
      panel and confirm it populates, use Rabbit Runner once and confirm
      it shows up both in the last-hand banner and in the history log,
      and watch the scripted demo end to end. As of the most recent
      session this should also include: face a bet/raise as the
      non-acting player and confirm its size is legible on the felt (not
      just present in the API response), fold a hand and let the next
      one play deep into its own board before checking that the
      rabbit-hunt banner's wording still reads clearly at that point,
      and open the demo's new "Hands played so far" panel after watching
      both showcase hands. **As of this session, additionally:** force
      (shallow stacks make this reliable) a preflop all-in and confirm
      hole cards, flop, 3rd hole card, turn, and river each reveal with
      a visible pause before a showdown beat names each hand and
      highlights the winner against what everyone else had; separately
      confirm a normally-paced hand that reaches a real showdown *also*
      gets that showdown beat (description + winner highlight) even
      though there's no board to animate first; click "Skip" mid-reveal
      and confirm it lands cleanly on the end state; open the persistent
      hand-history panel and confirm each revealed hand now shows its
      description with the winning row visually distinguished; and
      specifically check seat layout at 4+ and 6+ seats, not just
      heads-up, since the new per-seat description line was only
      exercised structurally (jsdom), never visually, and could plausibly
      crowd a seat box at higher counts. Fix anything that looks wrong
      before telling anyone outside the project it's ready.
- [ ] While there: decide the one remaining standing open item from
      `HANDOFF.md` Section 4 that doesn't need code — the
      `TRADEMARKS.md` entity-naming mismatch ("GamingTech, LLC" vs.
      "GameTech Systems") — and post `welcome_message.md`'s content to
      the GitHub Discussions thread (still just sitting as drafted text,
      now across five sessions).

**Definition of done:** the live URL genuinely reflects the most recent
session's work, someone has personally clicked through it (including the
new bet-visibility and demo-history items above), and the remaining
docs-only open item is either resolved or explicitly deferred with a
reason.

---

## Phase 0.5 — Hand reveal & showdown sequence (new top priority)

**Added from direct product feedback; read this before touching Phase 1
below — this jumps the queue.** Reported after watching real play: when
a hand resolves with no further betting decisions possible (the most
common case: both players shove preflop), `Hand._progress()` (see
`orchestrator.py`) races through every remaining street inside the same
request that triggered it, and calls `_finalize()` before control ever
returns to the caller. The API response the client gets back already
has the finished hand's payouts and a full 5-card board — there is no
moment at which a flop reveal, a 3rd-hole-card reveal, a turn reveal, or
a river reveal is its own event a viewer can actually watch happen.
Right now the only way to reconstruct what happened is to open the
table-activity log or the hand-history panel after the fact. Every real-
money and most play-money poker clients pace this out (hole cards flip
up, then each street turns with a beat in between, then a showdown
highlight) precisely because that pacing *is* the moment of drama in an
all-in pot — jumping straight to the result is a genuinely worse
experience, not a cosmetic nicety.

The full sequence asked for, matching `STREET_ORDER` exactly: all-in
players' hole cards revealed -> beat -> flop -> beat -> 3rd hole card ->
beat -> turn -> beat -> river -> a showdown beat that names each
revealed hand (e.g. "Two Pair, Jacks and Fours") and visually marks the
winner against what everyone else had. The same request also asks for
that showdown beat on *every* hand that reaches a real showdown, not
just fast-forwarded all-ins — that half doesn't depend on the
fast-forward problem at all and is the smaller, standalone piece (0.5b
below).

### Does this call for the PokerTH fork (Phase 4+)? No.

Direct answer to the question raised alongside this feedback: build
this on the current custom client, don't treat it as a reason to start
the fork.

- The fork question (Phase 4+ below) is about replacing the *entire*
  table UI with a battle-tested, general-purpose Hold'em client. That's
  a real option for the felt, seating, and betting controls, which
  genuinely are generic Hold'em concerns PokerTH's client already
  solves well.
- This specific gap isn't generic, though. The reason it needs a 3rd-
  hole-card beat in the middle of the runout — the reason a standard
  7-card Hold'em client's reveal animation has never had to represent
  this sequence at all — is Hold'em Plus's own rule. Forking PokerTH's
  web client would still mean writing this exact sequencing logic from
  scratch inside that fork's reveal code; it doesn't pre-exist anywhere
  to inherit. Forking trades one set of custom code for a different set
  of custom code, on top of a real integration project (PokerTH speaks
  its own network protocol; see the tech plan's Section 3.2) and the
  AGPL/GPL licensing review `LICENSE`/`TRADEMARKS.md` already flag for
  that path.
- Given that, doing this on the existing client is strictly less total
  work for this specific feature, and doesn't foreclose forking later
  for the broader UI overhaul Phase 4+ already describes on its own
  terms.

### Design

Keep `Hand`'s resolution instant and authoritative — do not introduce
artificial delays or pauses into `HandFlow`/`BettingRound`, both
deliberately synchronous, fully-tested state machines this project
treats as audited (see their own module docstrings on why side-pot and
betting-legality bugs get extra scrutiny here). Instead, have `Hand`
record what already happened at each street transition into a new,
purely-descriptive log, and let the *client* animate through that log
at its own pace after the fact:

- [x] **0.5a (backend, no frontend work) — shipped.** Added a
  `RunoutStep` dataclass and a `Hand.runout: List[RunoutStep]` field in
  `orchestrator.py`. `_handle_dealing_for()` calls a new
  `Hand._record_runout_step()` unconditionally at the end, for every
  street transition (not just fast-forwarded ones, so the frontend never
  needs two code paths) — it appends a step only for the four streets
  that actually change what's visible (`orchestrator.RUNOUT_STREETS`:
  `DEAL_FLOP`, `DEAL_THIRD_HOLE_CARD`, `REVEAL_FOURTH_STREET`,
  `REVEAL_FIFTH_STREET`), capturing that street, `community_cards` as of
  that step, and — only from the moment no further betting decision is
  possible — every remaining active player's hole cards. The actual
  condition landed as `len(active) > 1 and all(p.all_in for p in
  active)`, where `active` is this codebase's existing
  not-yet-folded convention (see `Hand._finalize`); the design note
  above phrased it as `all(p.all_in or p.folded for p in the active
  players)`, but since "active" already means non-folded everywhere else
  in this file, that reduces to the same check — worth flagging here in
  case a future reader diffs the two phrasings and wonders. `runout` is
  threaded through `HandResult` (defaults to `[]` so
  `test_analytics.py`'s direct `HandResult(...)` fixtures didn't need
  touching) and serialized by `api.py` onto both `last_hand` and every
  `/tables/{id}/hands` entry as a `runout` list of `{street,
  community_cards, revealed_hole_cards}` objects. Tests:
  `test_orchestrator.py` (an all-in-preflop runout has one step per
  street with the right community-card counts and both hole-card sets
  exposed from the first step onward; a checked-down hand that never
  goes all-in still produces a step per street with nothing revealed
  early; a hand that folds after the flop stops its runout at exactly
  that point; an immediate preflop fold-out has an empty runout) and
  `test_api.py` (the same shape reaches `last_hand` and the history log,
  identically, and is empty for a folded hand). Also hand-verified over
  a real `TestClient` HTTP round trip, both a checked-down hand and a
  heads-up all-in — see `HANDOFF.md` for the exact output. **244 passed**
  (222 + 22 new) after this and 0.5b together, no regressions.
- [x] **0.5b (showdown hand descriptions — smaller, stands alone) —
  shipped.** Added `hand_evaluator.describe_hand_rank(rank: HandRank) ->
  str`, e.g. `"Full House, Aces full of Kings"` or `"Two Pair, Jacks and
  Fours"` — a real branch per `HandCategory`, via two small rank-name
  lookup tables (`_RANK_NAMES`/`_RANK_PLURALS`), raising rather than
  falling back silently if a category is ever added without a matching
  branch. `api.py` recomputes each revealed hand's description the same
  way `analytics.build_hand_record` already recomputes categories (a
  cheap `evaluate_best_of` call per revealed hand, once per finished
  hand, nowhere near a hot path) and adds it as a new
  `"hand_descriptions": {player_id: description}` field alongside
  `revealed_hands` on both `last_hand` and each `/tables/{id}/hands`
  entry — empty for a hand that ended by fold, same as
  `revealed_hands` is. Deliberately did **not** add a separate
  `is_winner` flag: which revealed hand(s) won is already answerable
  from `payouts` (a `player_id` with `payouts.get(player_id, 0) > 0`
  won at least one pot), so 0.5c's "visually mark the winner" can read
  that directly rather than this duplicating it. Tests:
  `test_hand_evaluator.py` (one example per `HandCategory`, parametrized,
  plus the wheel-straight-plays-5-high edge case, plus a dedicated
  full-house trips-before-pair wording check) and `test_api.py` (the
  description dict reaches both `last_hand` and the history log with
  keys matching `revealed_hands`, and is empty for a folded hand).
- [ ] **0.5c (frontend, needs 0.5a) — code shipped and jsdom-verified
  this session; still needs the real-browser watch-through before this
  phase counts as done.** In `static/index.html`: when a hand's
  `last_hand` arrives with `last_hand.runout` steps longer than what the
  client actually observed live (the fast-forwarded case), the felt now
  plays the extra steps back with a short pause between each — hole
  cards for any all-in player(s), then that step's community cards,
  whichever changed at that particular step (some steps only move one of
  the two — see `HANDOFF.md`'s STREET_ORDER note for why, and why that
  makes the exact "hole cards → flop → 3rd hole card → turn → river"
  cadence fall out of the data without needing per-street special-
  casing). `last_hand.hand_descriptions` now lands at the settle-in
  moment next to each revealed hand, winner(s) visually marked
  (cross-referencing `last_hand.payouts`, per 0.5b's note above — no new
  field was needed for that part, as planned).
  One deliberate divergence from this bullet's original wording, worth
  flagging explicitly: it said a normally-paced hand has "nothing new to
  animate... so this never fires for it," but the Design section above it
  also explicitly asked for the showdown beat "on *every* hand that
  reaches a real showdown, not just fast-forwarded all-ins." Shipped
  behavior follows the Design section: a normally-paced hand has no
  *runout* steps to replay (true, and confirmed empirically — see
  `HANDOFF.md`), but it still gets the showdown beat itself, since
  opponent hole cards are never visible to this client before real
  showdown regardless of how the hand was paced. Read literally, the
  original bullet would have meant 0.5b's `hand_descriptions` field
  never actually gets displayed for the common (non-all-in) case, which
  didn't seem like the intent.
  Verified via a jsdom scaffold built from real `TestClient`-captured
  API output (not guessed shapes) — 8 scenarios, 41 assertions, covering
  the fast-forwarded-all-in case, the normally-paced-showdown case, a
  flop (not preflop) all-in exercising the harder branch of the unseen-
  steps detection, first-connect/reconnect (must not replay history
  nobody watched live), repeat-poll dedup, and the existing rabbit-hunt
  banner still working through the restructured render() dispatcher.
  Scaffold deleted at the end of the session per this project's standing
  practice. **What jsdom can't tell you, and what's still open:** actual
  visual layout (does the new per-seat description line crowd a seat at
  6+ players?), whether the pacing feels right, whether "Skip" is
  discoverable — see `HANDOFF.md` for the full list of what still
  genuinely needs a human on a real browser.

### Suggested split

Bigger than one session at this project's own ~5-hour sizing (see this
document's intro) — this is why it was split. 0.5a and 0.5b (engine +
API + tests, no UI) shipped together in one session. 0.5c (the frontend
animation) was its own session, per the plan — its code is now shipped
and jsdom-verified, but the real-browser watch-through that closes out
this whole phase still hasn't happened; see `HANDOFF.md` for exactly
what to check.

**Definition of done:** an all-in preflop hand, watched live in a real
browser, visibly reveals hole cards, then flop, then 3rd hole card, then
turn, then river, each with a pause, before landing on a showdown that
names and highlights the winning hand against what everyone else had —
matching the sequence in this phase's originating feedback exactly, not
a paraphrase of it. **Not yet met.** 0.5a/0.5b/0.5c are all now code-
complete and each verified as rigorously as this project's tools allow
short of an actual browser (0.5a/0.5b over a real HTTP round trip and
244 passing tests; 0.5c via a jsdom scaffold built from that same real
output) — but per this document's own ground rule, none of that
substitutes for someone actually watching it happen. That's the one
remaining step.

---

## Phase 1 — Hand-history follow-through

The log itself shipped several sessions ago (`GET /tables/{id}/hands`,
the collapsible panel in `static/index.html`, tests in `test_api.py`).
What didn't:

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
- [ ] **Multi-way side-pot coverage.** Every hand-history test so far
      has used heads-up hands. The feature reuses `HandResult`
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

Flagged as an open decision across several `HANDOFF.md`s now and still
not built. Now that Phase 1 forces a rigged multi-way side-pot deck to
exist anyway, this is a natural, low-marginal-cost follow-on rather than
a separate investigation.

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
      entry should Just Work, including in the "Hands played so far"
      history panel added this session (it's built generically off
      whatever `demoScript` contains, not hardcoded to two hands) — but
      confirm the demo-seats layout (`.demo-seat` flexbox) doesn't get
      cramped at 4 seats, and that the narration makes the side-pot
      mechanic legible to someone who's never seen one (this is the one
      place in the whole demo where a plain-English explanation earns
      its keep more than a UI treatment would).
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
Hold'em baseline, player feedback) for several sessions now, and nothing
has ever displayed them anywhere a person would look. This is explicitly
called out as a "longer-standing priority" in more than one prior
`HANDOFF.md` and has been carried forward, unbuilt, the whole time.

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
