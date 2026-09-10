# Hold'em Plus — Session Handoff

**Purpose of this document:** you're picking this up cold, either as the next
Claude session or a human developer. This tells you exactly what exists,
what's been verified, what's deliberately left undone, and the fastest path
from here forward. It supersedes the previous `HANDOFF.md` — that version's
Section 0 (the rabbit-hunt-banner / bet-visibility / demo-history session) is
now historical background; see Section 0 below for the current state instead.

Start with `README.md` for how to run things and `POLISH_PLAN.md` for the
forward-looking backlog. This document is about *state and decisions*.

---

## 0. Status as of the most recent session — read this first

This session's brief came directly from the person running the project, as a
set of "Polish Notes" covering one bigger design question and four concrete
fixes. The bigger item is now `POLISH_PLAN.md`'s new **Phase 0.5** (inserted
ahead of the old Phase 1-4+, which are otherwise untouched); the four
concrete fixes are shipped, tested, and described below.

**Verified the pasted engine/test/static files against each other the same
way every prior session has recommended** — reconstructed the whole repo in
a fresh sandbox and ran `pytest -q` *before* making any change, to confirm
the starting point actually matches what `HANDOFF.md`/`README.md` claimed.
**222 passed**, matching the prior handoff's stated baseline exactly, so
there was no drift to reconcile this time (this sandbox cannot reach
`github.com/GameTech-Systems/holdem-plus` for a live diff the way some prior
sessions did — see Section 6 — so this in-context reconstruction is the
closest equivalent available here).

### The big item: hand reveal & showdown sequence

**The report:** when a hand resolves with no further betting decisions
possible — the common case is both players shoving preflop — the game jumps
straight to the next hand with a full board and no visible reveal sequence.
The only way to see what happened is the table-activity log or hand history
after the fact. The ask: an all-in (or any early-terminating) hand should
step through all-in players' hole cards revealed -> beat -> flop -> beat ->
3rd hole card -> beat -> turn -> beat -> river -> a showdown beat that names
and highlights the winning hand against what everyone else had, and every
hand reaching showdown (not just fast-forwarded ones) deserves that same
showdown treatment.

**The question alongside it:** whether this is really the PokerTH-fork
conversation (`POLISH_PLAN.md` Phase 4+) in disguise — i.e. whether hand-
building this reveal animation is worth it versus adopting an existing
poker UI that (presumably) already has one.

**Direct answer: no, don't fork for this.** Build it on the current custom
client. Reasoning, in full in `POLISH_PLAN.md`'s new Phase 0.5, summarized
here: the fork question is about replacing the *whole* table UI with a
general-purpose Hold'em client, which is a legitimate option for the felt,
seating, and betting controls — those are genuinely generic concerns PokerTH
already solves well. But the specific gap here isn't generic. The reason it
needs a beat for the 3rd hole card in the middle of the sequence — the
reason a standard 7-card Hold'em client's reveal animation has never had to
represent this at all — is Hold'em Plus's own rule. Forking would still mean
writing this exact sequencing logic from scratch inside the fork's reveal
code; it doesn't pre-exist anywhere to inherit. Forking trades one set of
custom code for a different set of custom code, on top of a real protocol-
integration project and the AGPL/GPL licensing review `TRADEMARKS.md`/
`LICENSE` already flag for that path. Doing this on the existing client is
strictly less total work for this specific feature, and doesn't foreclose
forking later for the broader UI overhaul Phase 4+ already describes on its
own terms.

**Why this is designed, not built, this session:** it's genuinely bigger
than this project's own ~5-hour session sizing once you include the engine
change, its tests, the showdown-description work, and the actual felt
animation (which needs the real-browser verification this project has
chronically struggled to get, not just another jsdom pass). Rather than
rush a partial or unvalidated version of a feature that touches
`orchestrator.py` — code this project explicitly treats as audited, given
how disputed side-pot and betting-sequencing bugs are in real poker
software — this session wrote the concrete design (data model, API surface,
frontend consumption, a suggested 0.5a/0.5b/0.5c split, and an explicit
definition of done) into `POLISH_PLAN.md` so the next session can execute
against it directly instead of re-deriving the approach. Read that section
in full before starting; don't re-litigate the fork question from scratch,
it's already been decided above and there.

### The four concrete fixes (all shipped this session)

1. **"Skip ahead" moved next to "Exit demo."** Both buttons now live
   together in `#demo-panel .demo-head`, inside a new
   `.demo-head-buttons` wrapper, instead of "Skip ahead" sitting alone in
   its own row below the log. The now-empty `.demo-controls` wrapper and
   its CSS rule are removed; `.demo-head`'s `align-items` changed from
   `baseline` to `center` so the title and the two buttons line up
   properly. No JS changes needed — both buttons are still looked up by
   the same element IDs, just relocated in the DOM.

2. **Rabbit Runner's summary text was inaccurate.** The old copy — "Fold
   on the turn or river, and you can still pay to see the river you'd have
   faced" — implied folding on the river itself was a meaningful case for
   this feature, but the river is already showing on the board by the time
   a river fold is possible, so there'd be nothing left to reveal. Changed
   `demo_showcase.py`'s `Rabbit Runner` `DemoHand.summary` to: "If folding
   ends the hand before the river's revealed, you can still pay to see
   what it would have been" — describing the case that's actually
   meaningful, matching the phrasing suggested directly. The underlying
   eligibility logic (`Hand.is_eligible_for_rabbit_hunt`, still turn-or-
   river) is untouched; this was a copy fix, not a rules change. Also
   lightly touched up the similar aside in the `#demo-teaser` paragraph in
   `static/index.html` for consistency ("pay to reveal the river when a
   fold ends the hand before it's shown").

3. **The "front-loaded deal is the whole point" aside is gone.** That
   sentence, in the Rabbit Runner reveal narration, was explaining an
   *implementation* detail (the deck is dealt front-loaded, face down,
   which is why the river is always available to reveal) as if it were
   something an online player should care about. It's a live-dealer
   convenience, not an online-play concept, and a player doesn't need the
   "why" to use the feature — removed, per direct feedback that it
   "only pertains to live poker with real cards, not the online games."
   (Checked the rest of the repo for the same pattern: every other mention
   of front-loaded dealing is either scoped correctly to the live-casino
   section of the tech plan, or is internal engine/test documentation
   explaining *why the code is written the way it is* to a future
   developer — not player-facing copy — so nothing else needed to change.)

4. **The Rabbit Runner demo hand itself was rebuilt** so the fold and the
   rabbit hunt both mean something, instead of an arbitrary bet/fold:
   - **Rio** (button/SB) holds `8d 7s`, draws `6c` as his 3rd hole card.
     Board through the turn is `9s 3c 2c` (flop) `Td` (turn). Verified via
     `hand_evaluator.evaluate_best_of`: Rio is high-card-only through the
     flop, and the turn card (`Td`) completes a ten-high straight
     (`9s`-`Td` from the board plus `8d 7s 6c` from his own cards) — so
     "Rio bets 6, that ten on the turn just gave him a straight" is
     literally true at the moment he bets, not asserted after the fact.
   - **Sam** (BB) holds `Kh Jd`, draws `4d`. Through the turn he has
     exactly a king-high gutshot needing a queen (`K _ J T 9`, the `Q`
     being the only card that connects the board's `T`/`9` to his `K`/`J`)
     — verified the same way: no pair, no straight, and adding a queen
     (checked directly) produces `K-Q-J-T-9`, a king-high straight that
     *beats* Rio's ten-high one. Sam folds to Rio's bet (a sound fold —
     a single-card gutshot with one card left to come isn't good odds
     against a bet), then rabbit hunts and the scripted river genuinely
     is `Qh` — so the reveal is "yes, you would have caught it, and it
     would have been good enough," not a coin flip either way.
   - This flips which player folds and rabbit hunts (Sam, not Rio;
     Rio wins the uncontested pot of 10, not Sam) — `test_demo_showcase.py`
     updated to match (`test_rabbit_hunt_showcase_rio_folds_on_the_turn`
     -> `test_rabbit_hunt_showcase_sam_folds_on_the_turn`, asserting
     `actor == "Sam"`; `test_rabbit_hunt_showcase_sam_wins_uncontested`
     -> `test_rabbit_hunt_showcase_rio_wins_uncontested`, asserting
     `{"Rio": 10}`). The fee-conservation and river-reveal tests needed no
     numeric changes — the blind amounts, and therefore the fee, don't
     depend on which seat wins.
   - Verified end to end three ways before trusting any of this: (a) the
     card math directly against `evaluate_best_of` at each street, shown
     above; (b) the actual scripted hand run through the real engine
     (`Hand`, not a mock) via a throwaway script, confirming the printed
     narration and payouts matched what was intended; (c) the full
     `pytest -q` suite, both immediately after the `demo_showcase.py`
     edit and again after every subsequent file change this session.

5. **`CONTRIBUTING.md` got a new "Known extension points" section**,
   per the explicit request to note — but not build — the idea that a real
   casino operator might want Rabbit Runner to reveal *both* remaining
   streets (not just the river) for a player who folds even earlier
   (preflop or on the flop), since neither card has been shown yet at that
   point. Framed as a real v2 feature needing its own pricing/eligibility/
   accounting design, not a quick addition, consistent with how this file
   already talks about the DAT-hardware and real-money exclusions.

### How this session verified the frontend change (still no real browser — see Section 3)

Same standing limitation as every session before this one: no way to open
an actual browser from this sandbox. In increasing order of rigor:

1. `node --check` on the extracted `<script>` block — clean.
2. A Python `html.parser`-based tag-balance check across the whole file —
   confirmed no unclosed/mismatched tags from the `.demo-head`
   restructuring (open-tag stack empty at end of parse).
3. The full `pytest -q` suite (222 passed, see below) — doesn't touch the
   frontend directly, but confirms the `api.py`/`demo_showcase.py` side
   that feeds it is correct.

This is a smaller, lower-risk change than prior frontend sessions (moving
two existing buttons into a shared wrapper, plus two copy edits — no new
JS logic, no new state, no new event handlers), so this session judged the
jsdom-scaffold treatment from the prior session's Bug 1-3 fixes to be more
machinery than this specific change warranted. **Still flagging for the
next real-browser pass, as always:** confirm the two demo-panel buttons
sit next to each other and don't wrap awkwardly at a narrow (mobile) width,
and confirm the rebuilt Rabbit Runner hand reads naturally at real
animation speed, not just correctly in the JSON.

### Test suite

**222 passed** — same count as the prior handoff. Two tests in
`test_demo_showcase.py` were rewritten (not added or removed) to match the
rebuilt hand; every other test file is untouched. `example_usage.py` and
every engine module besides `demo_showcase.py` are untouched.

### What did NOT change this session

- `orchestrator.py`, `betting_state_machine.py`, `side_pots.py`,
  `hand_evaluator.py`, `poker_types.py`, `tournament_structure.py`,
  `tournament_balancing.py`, `analytics.py`, `api.py` — none of these
  needed a code change for the four concrete fixes. (Phase 0.5's `runout`
  work, once someone picks it up, *will* touch `orchestrator.py` and
  `api.py` — see `POLISH_PLAN.md`.)
- `Hand.is_eligible_for_rabbit_hunt()`'s actual eligibility logic — only
  the demo's prose describing it changed, not the rule itself.
- Everything Section 3 of the prior `HANDOFF.md` already flagged as not
  built (still true, carried forward in Section 3 below).
- This session's changes are, as always, not pushed or redeployed — see
  Section 1, carried forward unchanged.

---

## 1. Deployment note (carried forward, unchanged)

The person running this project confirmed directly: **Render does
auto-deploy on every push to `main`.** Practically: once the files this
session touched (`demo_showcase.py`, `test_demo_showcase.py`,
`static/index.html`, `CONTRIBUTING.md`, `POLISH_PLAN.md`, and this file)
are pushed, the live demo should update on its own, no manual redeploy
step needed. This sandbox still has no push credentials for
`github.com/GameTech-Systems/holdem-plus` — a human needs to actually
commit these files, same as every session before this one.

---

## 2. What exists right now

Unchanged in shape from the prior handoff; the five files this session
touched are marked:

```
poker_types.py, hand_evaluator.py, betting_state_machine.py,
side_pots.py, tournament_structure.py, tournament_balancing.py
  -> orchestrator.py (Hand + Tournament)
  -> analytics.py (hands/hour, pot-vs-blinds, showdown frequency,
                    hand-strength distribution, player feedback)
  -> demo_showcase.py  *** CHANGED (Rabbit Runner hand rebuilt) ***
  -> api.py (REST + WebSocket, /analytics, /feedback, /demo/script,
             /tables/{id}/hands, current_bet/pot_total/bet_this_street,
             hand_number on last_hand)
  -> static/index.html  *** CHANGED (demo button layout, two copy edits) ***

test_demo_showcase.py  *** CHANGED (2 tests updated for the rebuilt hand) ***
CONTRIBUTING.md  *** CHANGED (new "Known extension points" section) ***
POLISH_PLAN.md  *** CHANGED (new Phase 0.5 inserted ahead of old Phase 1) ***
```

The live instance is `https://holdem-plus-demo.onrender.com/app/` — **this
session's changes are not deployed there yet**; see Section 1.

---

## 3. What's explicitly NOT built — read this before promising anything

Carried forward, all still true: no real frontend fork (see Phase 0.5's
answer above for why that's not the lever for the reveal-sequence gap
specifically; Phase 4+ is still the separate, larger, not-yet-started
question), no persistence, no multi-table routing in the API, no rate
limiting/auth beyond opaque guest IDs, the known engine simplifications
documented in their own modules, the Monte Carlo baseline is Hold'em-only,
demo mode is fixed at exactly two hands (the third, side-pot-focused one
is still `POLISH_PLAN.md` Phase 2, unstarted), no hand-history pagination
in the UI (`POLISH_PLAN.md` Phase 1), and `welcome_message.md`'s content
has still never been posted to GitHub Discussions.

New from this session:

- **The reveal/showdown sequence itself is designed, not built** — see
  Section 0 above and `POLISH_PLAN.md` Phase 0.5 in full. A hand that
  resolves without further betting decisions (typically an all-in) still
  jumps straight to its final state with no animated runout; that's
  exactly the gap Phase 0.5 exists to close, and it hasn't been closed
  yet.
- **No showdown hand-strength descriptions anywhere yet** (Phase 0.5b) —
  a revealed hand's category (e.g. "Full House, Aces full of Kings") isn't
  surfaced by `api.py` or rendered by `static/index.html` at all today,
  for any hand, fast-forwarded or not.
- **No real-browser check of the button-layout change** — see the
  verification writeup above for what substitute checks were run instead.

---

## 4. Open decisions (not bugs — need a person to decide, not a fix)

1. **Entity naming mismatch** (`TRADEMARKS.md`) — still unresolved, now
   several handoffs running. Untouched again this session.
2. **How far to extend demo mode** — still `POLISH_PLAN.md` Phase 2's
   concrete, unstarted plan for a third (side-pot) showcase hand.
3. **Whether to build the optional multi-street Rabbit Runner reveal**
   for earlier folds (preflop/flop) — newly documented as a real v2 idea
   in `CONTRIBUTING.md`'s "Known extension points," explicitly not needed
   for this demo. Nobody needs to decide anything about it now; it's
   flagged so a future contributor doesn't have to rediscover the idea
   from scratch, and so it doesn't get bolted on hastily if it comes up
   in an issue or PR.

---

## 5. Fastest path from here forward

1. **`POLISH_PLAN.md` Phase 0.5** — the reveal/showdown sequence. This is
   the person's stated top priority; start with 0.5a (the `runout` field
   on `Hand`/`HandResult`, threaded through `api.py`, with its own tests —
   no frontend work in that slice) since 0.5c depends on it. 0.5b
   (showdown hand descriptions) can ride along with 0.5a or be its own
   short session; it doesn't depend on the runout work at all.
2. **Push this session's files and finally do the real-browser
   click-through** — still true every session: `POLISH_PLAN.md` Phase 0's
   own checklist has been sitting unresolved across many handoffs now.
   Specifically for this session's changes: confirm the demo-panel button
   pair looks right at a narrow width, and watch the rebuilt Rabbit Runner
   hand play out at real animation speed.
3. **`POLISH_PLAN.md` Phase 1** — hand-history pagination, a fetch-failure
   state, and the multi-way side-pot test. Untouched this session.
4. **`POLISH_PLAN.md` Phase 2** — the third (side-pot) demo showcase hand.
   Also untouched; note it now shares groundwork with Phase 0.5 (both want
   a rigged multi-way deck / a richer showdown moment), so whoever does
   Phase 0.5b's hand-description work might find Phase 2 meaningfully
   cheaper as a result.
5. **Phase 3 / Phase 4+** — analytics visualization, then the real
   frontend fork question (for the *general* table UI, not as a fix for
   Phase 0.5's specific gap — see Section 0). Also untouched.

---

## 6. If you're a fresh Claude session picking this up

This sandbox could not reach `github.com` to diff against the live repo
directly (network access here is limited to package registries, GitHub's
code-hosting domains for `pip`/`npm`-style installs, and Anthropic's own
API — not arbitrary `git clone` traffic in every environment; check your
own session's network configuration rather than assuming). What this
session did instead: reconstructed the whole repo from the files pasted
into this chat, ran `pytest -q` *before* touching anything to confirm the
starting point matched the prior handoff's stated baseline (222 passed,
it did), and only then made changes — re-running the full suite after each
file edit, not just at the end. If your environment *can* reach the real
repo, still diff it before trusting either source, the same standing advice
every prior handoff has given.

Baseline going into your session: **222 passed.**

If your task touches the frontend: the jsdom-scaffold approach from two
sessions ago (`JSDOM(html, { runScripts: "dangerously" })`, call the real
render functions with hand-built state, assert on the resulting DOM,
delete the scaffold before finishing) is still the right tool for anything
that changes rendering *logic*. This session judged its own change (moving
two buttons, two copy edits) small enough for a lighter check instead
(`node --check` plus a tag-balance pass) — use your judgment on which a
given change actually needs, but default to the fuller scaffold once
there's any new JS behavior involved, which Phase 0.5c (the actual runout
animation) very much will have.

If your task is Phase 0.5: read that section of `POLISH_PLAN.md` in full
before writing any code. The fork question has already been answered
there and in Section 0 above — don't re-open it from scratch.
