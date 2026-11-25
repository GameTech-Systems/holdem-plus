# Hold'em Plus — Session Handoff

**Purpose of this document:** you're picking this up cold, either as the next
Claude session or a human developer. This tells you exactly what exists,
what's been verified, what's deliberately left undone, and the fastest path
from here forward. It supersedes the previous `HANDOFF.md` — that version's
Section 0 (the Phase 0.5a/0.5b session: the backend runout log and showdown
descriptions) is now historical background; see Section 0 below for the
current state instead.

Start with `README.md` for how to run things and `POLISH_PLAN.md` for the
forward-looking backlog. This document is about *state and decisions*.

---

## 0. Latest session: audit of the equity simulation and Strategy Guide

An outside (GPT) audit of `sim/` and `static/strategy.html` was checked finding by finding against the actual
code, with the simulator rebuilt and rerun, rather than accepted or dismissed as written. **Nothing below is
pushed yet** (no sandbox here has push credentials), and **the GitHub Actions workflow has not been run**:
every step in it was executed locally and passed, which is not the same thing.

**Baseline first.** A clean clone matched the pasted files. A fresh default-seed run reproduces every number
embedded in `strategy.html` exactly (all 169 hands x h/p/pr/su/mi, both table sizes, all 14 shapes). The C
evaluator also checked out: see Finding 3.

| # | Audit finding | Verdict | What was done |
|---|---|---|---|
| 1 | Standard error understated | **Partly valid.** The README did say "standard error", and ±0.1 is fair heads-up (max 0.091). Six-handed max is 0.129, and the guide's footer said "about ±0.1 points" with no label. | Simulator now outputs per-hand SE for Hold'em, Plus and the paired difference, plus shape SEs and a `meta` block. Guide tooltips, a data table and the footer show them. |
| 2 | Raw equity is not strategic EV | **Valid, but already disclosed** in the README and footer. | Added a note directly above the chart, "vs random hands" and "all-in EV" wording in tooltips, and the EV formula's assumptions (equal stacks, no rake, nobody folds). |
| 3 | Evaluator validation is only a random cross-check | **Valid, and demonstrated.** No evaluator defect was found. | Added `--selftest` (exact 5- and 7-card counts; 8-card consistency), `exhaustive_check.py` (all 7,462 five-card hands), `edge_cases.py` (24 hand-derived showdowns). Planted bugs showed each layer misses something another catches (sim/README lists this). |
| 4 | Third-card odds (2/47, 6/47, 11/47) misleading | **Valid, confirmed by full enumeration.** Averaged over flops the odds are exactly 2/50, 6/50, 11/50 (4%, 12%, 22%); 2/47 etc. hold only when the flop contains none of your outs. The footer's "exact draws from the 47 unseen cards" was wrong as written. | Guide text now gives both, plus the conditional flush figures (21%, 19%, 17%). New `sim/third_card_odds.py` reproduces and asserts them. A conditional-odds calculator (reads your cards and the flop) was **not** built. |
| 5 | `--seed 0` makes every deal identical | **Valid, and broader:** a non-numeric `--seed` silently became 0, and zero or non-numeric trial counts printed `-nan` (invalid JSON) with exit code 0. | Arguments are validated and rejected with exit code 2; CI asserts this. |
| 5b | Modulo bias in `rnd() % n` | **Not accepted.** Bias is about 1e-18 for n <= 50 on a 64-bit generator, far below sampling error. | Documented in sim/README; code unchanged. |
| 6 | Separate evaluator / deal / equity validation; exact-enumeration benchmark | **Partly done.** Layers are separated and documented. Deck integrity holds by construction (swap-based shuffle of distinct cards). | An exact Hold'em Plus equity benchmark was **not** built (AA vs random is about 2 billion boards). The known-Hold'em-equity assertion in CI was tightened from 1.0 to 0.5 points. |

Strategy-guide items: opening ranges are now labelled provisional, with UTG/hijack labels and a note on why the
big blind has no opening row (it never opens an unraised pot, so the audit's request for a separate BB row does
not apply to an opening table). The cash/tournament advice was qualified (bankroll, rebuy, 15-20x set-mining,
under-10-BB push/fold, the vague "coin-flip" line). The set-mining rule now cites an exact figure: a pocket pair
is a set or better by flop betting 1 time in 6.4 (15.5%) here against 1 in 8.5 in Hold'em. The rule of 2 and 4
got an "outs are not clean" caveat, and the hand-tier section a board-relative note. The audit's "tables are not
accessible" point was partly an artefact of its browser not running JavaScript; the real gap was that the chart
is `role="img"`, so screen-reader users got no data. A collapsible data table (with SEs) now fixes that.

**Found in this review, not in the audit:**
- The guide said suited and connected hands gain most from the plus card. They do not: base equity and gain
  correlate at -0.93, the biggest gainers are simply the weakest hands (54s +7.7, 52o +7.3), and a suited
  connector gains only about 0.3 points more than the same connector offsuit. Reworded.
- The README and footer called Plus-minus-Hold'em differences "exact" with "much less noise". Pairing cuts the
  error by about 30% (SE about 0.09, not zero). Still, 166 of 169 heads-up differences are more than 2 SE from zero.
- The two shape equities in each `sh` entry were computed inside one `printf`, whose argument evaluation order
  C leaves unspecified, so the published numbers depended on gcc's right-to-left habit. Now explicit; numbers
  unchanged.
- `T7s` is in the Speculative tier but was missing from the button opening range. Added.
- The build now needs `-lm` (the SE uses `sqrt`); a false `-Warray-bounds` warning was silenced with a range
  guard (an ASan/UBSan run was clean).

**Files changed/added:** `sim/holdem_plus_equity.c`, `sim/README.md`, `static/strategy.html`,
`.github/workflows/equity-sim.yml`, `HANDOFF.md`; new `sim/exhaustive_check.py`, `sim/edge_cases.py`,
`sim/third_card_odds.py`, `sim/check_published.py`. Old results are bit-identical (`hu`, `six` and the shape
equities); `results.json` gains `se` and `meta`, and each `sh` row gains two SE entries.

**Zip unpacking.** `.github/workflows/unpack-zip.yml` unpacks a `.zip` uploaded to the repo root into the right
folders (allowlist: `sim/*`, `static/strategy.html`, `HANDOFF.md`, `POLISH_PLAN.md`, `README.md`,
`.github/workflows/*.yml`), runs `sim/run_checks.sh`, and only then commits to `main` and deletes the zip. A bad
zip changes nothing. Install it by hand first: GitHub's built-in token cannot push `.github/workflows/` files, so
workflow files inside a zip are skipped with a warning unless a `WORKFLOW_PAT` secret (PAT with `workflow`
scope) exists. Rehearsed against a local git remote (15 adversarial unpack cases, a full run, and two failing
zips); never run on real GitHub Actions.

**Still open from the audit:** a conditional third-card calculator; position-aware or fold-equity simulation
(the audit's Phase 2) and any solver; a glossary and unified "plus card / third card" terminology; a worked
example of one hand before and after the plus card. **Needs a human:** push the files (strategy page into
`static/`, scripts into `sim/`, workflow into `.github/workflows/`), run the workflow once on GitHub, and look
at the strategy page in a real browser. This session used jsdom only, so the new data table and the longer odds
cells have never been seen at phone width.

---

## 0b. Previous session (Phase 0.5c): still the current state of the engine and game UI

This session picked up the prior handoff's **Fastest path from here
forward, item 2**: `POLISH_PLAN.md` Phase 0.5c, the felt-side reveal-
sequence animation in `static/index.html`. **The code is now written** —
but, importantly, **Phase 0.5's own definition of done (a human actually
watching this happen in a real browser) is still not met.** Don't read
anything below as "Phase 0.5 is done" — it isn't yet, for the same reason
0.5a/0.5b weren't enough on their own. See "How this was verified" below
for exactly what was and wasn't checked, and Section 3 for what's still
open.

**Verification note, continuing the last two sessions' thread on this:**
this session's sandbox could also reach `github.com`/`codeload.github.com`,
and `git clone https://github.com/GameTech-Systems/holdem-plus.git`
succeeded again. Diffed all 9 files pasted into this chat's context
against the fresh clone (`HANDOFF.md`, `POLISH_PLAN.md`, `README.md`,
`api.py`, `hand_evaluator.py`, `orchestrator.py`, and all three test
files) — **byte-for-byte identical, no drift**, confirming the previous
session's Phase 0.5a/0.5b work is already live in the repo. Also ran
`pytest -q` against the real clone before touching anything: **244
passed**, matching every prior claim. Network access continuing to vary
session to session (as both prior handoffs noted) still holds — keep
doing what Section 6 says: try the clone first, don't assume either way.

### A real-engine surprise worth flagging before anything else

Going in, this session assumed (from `orchestrator.RUNOUT_STREETS`'
ordering — `DEAL_FLOP, DEAL_THIRD_HOLE_CARD, REVEAL_FOURTH_STREET,
REVEAL_FIFTH_STREET`) that the 3rd hole card gets dealt sometime *between*
flop betting and turn betting. **That's wrong.** Checked
`betting_state_machine.STREET_ORDER` directly rather than assuming, and
then confirmed it empirically against a real `Hand`:

```
DEAL_HOLE_CARDS, PREFLOP_BETTING, DEAL_FLOP, DEAL_THIRD_HOLE_CARD,
DEAL_FOURTH_STREET_FACEDOWN, DEAL_FIFTH_STREET_FACEDOWN, FLOP_BETTING,
REVEAL_FOURTH_STREET, TURN_BETTING, REVEAL_FIFTH_STREET, RIVER_BETTING,
SHOWDOWN, HAND_COMPLETE
```

The flop, the 3rd hole card, *and* the (still-facedown) 4th/5th street
cards are **all** dealt before flop betting ever opens — the dealing is
front-loaded across the board, not just for 4th/5th street. Practically,
for a normally-paced hand, this means a single state push right after
preflop betting closes already carries both the flop **and** everyone's
grown-to-3 hole cards, confirmed directly:

```
after preflop closes (ONE push):
  community_cards: ['3s', '9s', '9c']
  p0 hole cards: ['Jc', '3c', '8c']
  runout so far: [('DEAL_FLOP', 3), ('DEAL_THIRD_HOLE_CARD', 3)]
```

And for a real preflop all-in, both players' hole cards are already
revealed at the `DEAL_FLOP` runout step (2 cards each — the 3rd hasn't
been dealt yet) and *grow* to 3 cards at the `DEAL_THIRD_HOLE_CARD` step
right after, confirmed directly against `Hand.runout`:

```
step 0: DEAL_FLOP        community=[Tc,Jd,5c]  p0: [Ts,9d]     p1: [9c,Ad]
step 1: DEAL_THIRD_HOLE_CARD community=[Tc,Jd,5c]  p0: [Ts,9d,9h]  p1: [9c,Ad,Kh]
step 2: REVEAL_FOURTH_STREET community=[Tc,Jd,5c,Js] (hole cards unchanged)
step 3: REVEAL_FIFTH_STREET  community=[Tc,Jd,5c,Js,3h] (hole cards unchanged)
```

This turned out to matter a lot for 0.5c: it's *why* the reveal sequence
below can just walk `runout` in order, diffing each step's hole-card
count and community-card count against what was already shown, and get
the exact "hole cards → beat → flop → beat → 3rd hole card → beat → turn
→ beat → river → beat → showdown" cadence the original feedback asked
for, with no special-casing per street. If you're touching this again,
trust `STREET_ORDER` over `RUNOUT_STREETS`' ordering alone for *when*
things actually happen — `RUNOUT_STREETS` only tells you *which* streets
get a step, not where those steps sit relative to betting.

### Phase 0.5c — the felt reveal sequence (code shipped this session)

`static/index.html` — the only file this session changed. Added:

- **The reveal system itself** (new section, right after `renderCardBack()`):
  `unseenRunoutSteps(runout, seenCommunityCount)` — finds the first
  `last_hand.runout` step this client's felt hasn't effectively already
  shown live (checking both community-card length *and*
  `revealed_hole_cards` presence, since — per the STREET_ORDER note above
  — `DEAL_FLOP` and `DEAL_THIRD_HOLE_CARD` share the same community-card
  count, so a hole-card-only change can land on a step whose board count
  didn't move); `revealSleep(ms)` — a pause that resolves early once
  skipped; `findSeatEl(playerId)` — looks up an existing `.seat` element
  by the `data-player-id` attribute `renderSeats()` now tags each seat
  with (new this session; the reveal mutates existing seat DOM in place
  rather than re-rendering the whole seats list, since by the time
  there's something to reveal about a just-finished hand, the live
  `hand` already refers to the *next* one — there's no player list for
  the finished hand to rebuild from); `applyRevealedHoleCards` /
  `applyRevealedCommunityCards` — the actual DOM mutations, each
  revealed card tagged `.reveal-in` for a small CSS fade/scale-in;
  `applyShowdownBeat` — shows each `revealed_hands` entry with its
  `hand_descriptions` string underneath and a `.showdown-winner` /
  `wins`-badge highlight (cross-referencing `payouts`, exactly as
  `POLISH_PLAN.md`'s 0.5b note said 0.5c should); `runRevealSequence` —
  walks the unseen steps in order, each step split into up to two
  sub-beats (hole cards, then community cards — skipped if that part
  didn't actually change at this step), then the showdown beat if
  `revealed_hands` is non-empty, with a "Skip" button in the actions bar
  the whole time.
- **`render()` is now a dispatcher, not the renderer.** It still updates
  the hand-history count and tracks the latest state unconditionally,
  then either falls through to the old rendering logic (extracted
  unchanged into a new `renderLiveState(state)`) or hands off to
  `runRevealSequence()` when `state.last_hand` is a hand this client
  hasn't resolved yet (tracked via `revealedHandNumber`, since
  `last_hand` itself stays non-null on every poll until the *next* hand
  finishes) **and** either has unseen runout steps or reached a real
  showdown (`revealed_hands` non-empty) — matching `POLISH_PLAN.md`'s
  note that the showdown beat fires on *every* real showdown, not just
  fast-forwarded ones, since opponent hole cards are never sent to this
  client before that point regardless of pacing. A hand that ends by
  fold has neither, so nothing new fires for it — same static banner as
  before, same timing as before.
- **First-connect / reconnect guard:** if `#seats` has no children yet
  (this client's very first render, and it already has a `last_hand` from
  before it connected), the reveal is skipped — there's no live felt
  state to animate on top of, so it just catches up to the plain summary
  instead of reconstructing a reveal for history nobody here watched
  happen.
- **Small companion fix, same underlying data:** `renderHandHistory()` in
  the *persistent* hand-history panel now shows each revealed hand's
  `hand_descriptions` string next to its cards, and highlights the
  winning row (`.history-winner-row`) — this field has been on
  `/tables/{id}/hands` since last session's 0.5b, but nothing anywhere in
  this file displayed it until now. Not originally scoped to 0.5c, but
  same data, same session, low risk — flagging it explicitly here rather
  than folding it in silently.
- **CSS:** `.seat.showdown-winner`, `.showdown-desc`,
  `@keyframes reveal-card-in` / `.card.reveal-in`, and the matching
  `.history-hand-desc` / `.history-winner-row` pair for the panel above.

**A bug testing caught, worth knowing about if you touch this again:**
the first version of `revealSleep()` only checked whether skip had been
requested *at call time* — so clicking "Skip" while a pause was already
in flight did nothing until the *next* pause started, meaning skip
effectively didn't work until the very last beat. Fixed by having
`revealSleep()` register its own `resolve` in a module-level
`pendingRevealResolve`, which the Skip button's click handler now
resolves immediately in addition to setting the flag. **If you add a new
pause anywhere in this sequence, route it through `revealSleep()` rather
than a bare `setTimeout` — anything else won't be skippable.**

### How this was verified (and, just as importantly, how it wasn't)

1. Confirmed the exact JSON shape of `last_hand`, a completed hand's
   `/tables/{id}/hands` entry, and the live `hand` payload for the
   freshly-dealt next hand — all captured by actually driving hands
   through the real `orchestrator.Hand` and the real `api.py` (via
   `TestClient`), not reconstructed from memory of the source. This is
   what the jsdom fixtures below are built from.
2. Built a throwaway jsdom scaffold (`JSDOM(html, { runScripts:
   "dangerously" })`, per the prior session's own stated approach) and
   called `render(state)` directly with hand-built state objects
   mirroring that real output. Eight scenarios, 41 assertions, all
   passing:
   - a fold-ended hand never starts a reveal (unchanged behavior);
   - a normally-paced hand reaching a real showdown gets the showdown
     beat (descriptions + winner highlight) even though it has zero
     unseen runout steps to replay;
   - a fast-forwarded preflop all-in replays the full sequence (sampled
     mid-flight to confirm it's genuinely staged, not instant) and lands
     on the same showdown beat;
   - a fresh connect whose very first state already has a `last_hand`
     skips the reveal (no live felt to animate on top of) and just
     shows the static summary;
   - a repeat poll of the same `last_hand` doesn't re-trigger anything;
   - an all-in that happens *on the flop* (not preflop) — the harder
     branch of `unseenRunoutSteps`, where the first unseen step has to
     be found via `revealed_hole_cards` rather than a community-card-
     count change, since the board was already fully visible live;
   - the hand-history panel's new description/winner-row display;
   - a rabbit-hunt-eligible fold still renders its button correctly
     through the new `render()` dispatcher.
   Scaffold deleted at the end of the session, per the standing practice
   this project has used for frontend verification passes before.
3. `pytest -q` against the real clone, both before touching anything and
   again after (nothing to change, since this session touched no Python
   file): **244 passed**, unchanged.

**What this does NOT cover, and genuinely can't from this sandbox:**
jsdom verifies DOM structure and text content, not actual visual layout,
spacing, or paint. In particular: the `.seat` box is absolute-positioned
with a fixed vertical offset and a `min-width` that didn't account for
the new `.showdown-desc` line, so at higher seat counts (this was only
exercised 2-handed) the extra line could plausibly crowd or overlap a
neighboring seat — genuinely unknown until someone looks at it in a
browser. Same for whether 1400ms/2400ms pacing actually *feels* right,
whether the "Skip" button is discoverable, whether the reveal-in fade is
noticeable at all against the felt, and everything else this project's
own `POLISH_PLAN.md` has repeatedly and correctly insisted only a real
browser can answer. **Nothing here should be read as clearing that bar.**

### What did NOT change this session

Every Python file, every test file, `demo_showcase.py`, `CONTRIBUTING.md`
— none of it. This was a frontend-only session by design (per
`POLISH_PLAN.md`'s own note that 0.5c doesn't need to touch
`orchestrator.py` or `api.py` again), and it stayed that way: the only
file in the diff is `static/index.html`.

---

## 1. Deployment note (carried forward, unchanged)

The person running this project confirmed directly, several sessions
back: **Render does auto-deploy on every push to `main`.** This
session's clone confirms the *previous* session's files (0.5a/0.5b:
`orchestrator.py`, `hand_evaluator.py`, `api.py`, three test files,
`POLISH_PLAN.md`, `README.md`, prior `HANDOFF.md`) are already live in
the repo — so that push already happened. **This session's own change
(`static/index.html`) is not pushed yet** — a human still needs to do
that; no Claude sandbox in this project's history has had push
credentials (this one can clone/read, per the note above, but not
write). Given how recent pushes have actually happened (GitHub web UI
"Add files via upload," per `POLISH_PLAN.md` Phase 0's note), the
fastest path is probably the same again: upload the new
`static/index.html` into the **`static/` folder specifically** — the
repo's history already shows this exact file landing in the wrong place
once before.

---

## 2. What exists right now

```
poker_types.py, betting_state_machine.py, side_pots.py,
tournament_structure.py, tournament_balancing.py, hand_evaluator.py,
orchestrator.py, analytics.py, demo_showcase.py, api.py
  -> all unchanged this session (see "What did NOT change" above)

static/index.html  *** CHANGED (Phase 0.5c: felt reveal sequence --
                       runout replay + showdown beat -- plus a small
                       companion fix surfacing hand_descriptions in the
                       persistent hand-history panel) ***

test_*.py  -> all unchanged this session (still 244 passed; no new
              Python tests, since nothing Python changed)

POLISH_PLAN.md  *** CHANGED (0.5c filled in: code shipped, jsdom-
                    verified, real-browser verification still the open
                    item; Phase 0's browser checklist gained this
                    session's specific items to check) ***
README.md  *** CHANGED (Hand runout & showdown descriptions section
              updated to reflect 0.5c existing now) ***
```

**244 passed** (unchanged from last session — this one added zero new
Python tests, by design).

The live instance is `https://holdem-plus-demo.onrender.com/app/` —
**this session's change is not deployed there yet**; see Section 1. Once
it is, this is the piece that finally needs a human's eyes on an actual
all-in hand, not just another round of "tests pass."

---

## 3. What's explicitly NOT built — read this before promising anything

Carried forward, all still true: no real frontend fork (Phase 4+), no
persistence, no multi-table routing in the public API, no rate
limiting/auth beyond opaque guest IDs, the known engine simplifications
documented in their own modules, the Monte Carlo baseline is Hold'em-only,
demo mode is fixed at exactly two hands (`POLISH_PLAN.md` Phase 2's
third, side-pot-focused hand is still unstarted), no hand-history
pagination in the UI (Phase 1), the `TRADEMARKS.md` entity-naming
mismatch is still unresolved, and `welcome_message.md`'s content has
still never been posted to GitHub Discussions.

Updated from this session:

- **Phase 0.5c's code is written, not "done."** `static/index.html` now
  has a full reveal-sequence implementation, verified structurally via
  jsdom (see above) — but Phase 0.5's actual definition of done requires
  someone watching an all-in hand's hole cards, flop, 3rd hole card,
  turn, and river each reveal with a pause on an actual screen, in an
  actual browser, and that still hasn't happened. Don't let "the code
  exists and jsdom likes it" get rounded up to "Phase 0.5 shipped" —
  this project's own `POLISH_PLAN.md` has made that exact mistake-to-
  avoid explicit from the start (see its intro: "nothing here is 'done'
  until someone loads the actual deployed URL in a real browser").
- **Visual layout at higher seat counts is genuinely unverified** — see
  the "what this does NOT cover" note above. Worth specifically checking
  at 6+ seats, not just heads-up.
- **This session's change is not pushed or redeployed** — see Section 1.

---

## 4. Open decisions (not bugs — need a person to decide, not a fix)

Unchanged from the prior handoff; none of this session's work touched
any of these:

1. **Entity naming mismatch** (`TRADEMARKS.md`) — still unresolved, now
   several handoffs running.
2. **How far to extend demo mode** — still `POLISH_PLAN.md` Phase 2's
   concrete, unstarted plan for a third (side-pot) showcase hand.
3. **Whether to build the optional multi-street Rabbit Runner reveal**
   for earlier folds (preflop/flop) — documented as a real v2 idea in
   `CONTRIBUTING.md`'s "Known extension points," explicitly not needed
   for this demo.

---

## 5. Fastest path from here forward

1. **Push this session's one changed file** (`static/index.html`) plus
   this handoff, `POLISH_PLAN.md`, and `README.md` to `main`. Given the
   auto-deploy confirmation in Section 1, this alone gets the reveal
   sequence live — but see the next item, since "live" and "verified"
   are not the same thing here.
2. **The real-browser click-through is now the single most important
   thing standing between this and an actually-finished Phase 0.5.**
   Specifically, on the deployed URL:
   - Force (or wait for) a preflop all-in — shallow stacks make this
     easy and reliable — and confirm hole cards, then flop, then 3rd
     hole card, then turn, then river each visibly reveal with a pause,
     landing on a showdown that names each hand and highlights the
     winner.
   - Play (or bot-simulate) a normally-paced hand through to a real
     showdown and confirm it *also* gets the showdown beat — description
     + winner highlight — even though there's no board animation to
     watch first.
   - Click "Skip" partway through a reveal and confirm it jumps cleanly
     to the end state rather than getting stuck or double-rendering.
   - Open the hand-history panel and confirm expanded rows now show each
     hand's description next to its cards, with the winning row visually
     distinguished.
   - Specifically check seat layout at 4+ and 6+ seats, not just
     heads-up — this is the one thing flagged above as genuinely
     unverified even structurally.
   - Fold this into the rest of the standing Phase 0 checklist
     (`POLISH_PLAN.md` already has the full list) rather than treating it
     as a separate pass.
   Fix anything that looks wrong before calling Phase 0.5 done. If it all
   looks right, *that's* the moment to flip Phase 0.5's definition-of-done
   line in `POLISH_PLAN.md` from "Not yet met" to met — not before, and
   not on the strength of this session's jsdom run alone.
3. **`POLISH_PLAN.md` Phase 1** — hand-history pagination, a fetch-
   failure state, and the multi-way side-pot test. Untouched this
   session, same as every session since it was written.
4. **`POLISH_PLAN.md` Phase 2** — the third (side-pot) demo showcase
   hand. Also untouched.
5. **Phase 3 / Phase 4+** — analytics visualization, then the real
   frontend fork question. Also untouched.

---

## 6. If you're a fresh Claude session picking this up

**Try `git clone https://github.com/GameTech-Systems/holdem-plus.git`
first, before reconstructing anything from pasted files.** Worked for
the last two sessions in a row now (including this one), despite an
earlier session reporting it didn't work in theirs — network access
still appears to vary session to session, so don't assume either way;
just try it. If it succeeds, diff a couple of files you'd expect to be
stable against what's pasted into your own chat before trusting either
source completely (this session did — all 9 pasted files matched
byte-for-byte — but that's one more data point, not a standing
guarantee for yours).

Run `pytest -q` first thing either way. Baseline going into your
session: **244 passed.**

**If your task touches `static/index.html`'s reveal sequence again:**
read the "Phase 0.5c" section above in full first, including the
STREET_ORDER surprise — it's easy to get the reveal cadence subtly wrong
by trusting `RUNOUT_STREETS`' ordering alone without checking
`STREET_ORDER` for where those streets actually sit relative to betting.
The key invariants to preserve, in one place:
- `revealChainActive` is the single mutual-exclusion guard — `render()`
  bails immediately if it's true, and only `runRevealSequence()` sets it
  true/false. Don't add a second path that can start a reveal.
- `revealedHandNumber` is what stops the same hand's reveal (or
  no-op-decision) from re-running on every subsequent poll, since
  `last_hand` itself stays non-null until the *next* hand finishes. Set
  it *before* deciding whether there's anything to animate, not after —
  otherwise a hand with nothing to reveal would get re-evaluated forever.
- Any new pause needs to go through `revealSleep()`, not a bare
  `setTimeout`, or the Skip button won't be able to cut it short (see
  the bug note above).
- `runRevealSequence()` re-enters through `render(latestReceivedState)`
  at the end, not by calling `renderLastHandBanner`/`renderLiveState`
  directly — this is what lets a hand that finished *while* a previous
  one's reveal was still playing correctly get its own reveal afterward,
  instead of being silently skipped.
- Rebuild the jsdom scaffold from scratch rather than trusting old
  fixtures if the API shape changes — this session built its fixtures
  from real captured `TestClient` output specifically because guessing
  the shape (or trusting memory of `api.py`) would have been a real risk
  here, and it's what caught the STREET_ORDER assumption being wrong
  before any JS got written around it.

If your task is the real-browser check itself: that one's not something
a Claude session can do from this sandbox at all — it needs an actual
human on an actual deployed URL. If you're a Claude session and this is
your assigned task, say so plainly rather than attempting a jsdom
approximation of it and calling that equivalent; it isn't, and this
project's own docs have been explicit about that from the start.

If your task touches the engine (`orchestrator.py` in particular): the
prior session's `_record_runout_step()` note still applies unchanged —
it's called unconditionally at the end of `_handle_dealing_for()` for
every street, so a new dealing step would silently get no runout
coverage unless it's also added to `RUNOUT_STREETS`. Not a trap exactly,
just worth knowing it's there.
