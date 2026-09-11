# Hold'em Plus — Session Handoff

**Purpose of this document:** you're picking this up cold, either as the next
Claude session or a human developer. This tells you exactly what exists,
what's been verified, what's deliberately left undone, and the fastest path
from here forward. It supersedes the previous `HANDOFF.md` — that version's
Section 0 (the Phase 0.5 design session: the reveal-sequence design itself,
plus four concrete demo/UI fixes) is now historical background; see Section 0
below for the current state instead.

Start with `README.md` for how to run things and `POLISH_PLAN.md` for the
forward-looking backlog. This document is about *state and decisions*.

---

## 0. Status as of the most recent session — read this first

This session picked up the prior handoff's own **Fastest path from here
forward, item 1**: `POLISH_PLAN.md` Phase 0.5a (the hand-runout log) and
0.5b (showdown hand descriptions) — the backend half of the reveal/showdown
sequence the previous session designed but deliberately didn't build (see
that design, still intact, in `POLISH_PLAN.md`). Both are now shipped,
tested, and verified; 0.5c (the actual felt animation) is still open — see
Section 3.

**Verification note that changes standing advice in this doc:** this
session's sandbox *could* reach `github.com` and `codeload.github.com`, and
`git clone https://github.com/GameTech-Systems/holdem-plus.git` succeeded
outright. Every prior handoff has said its own sandbox couldn't do this and
told the next session to "check your own network configuration rather than
assuming" — that hedge turned out to matter: network access apparently does
vary session to session, and this one had it. Cloning the real repo and
running `pytest -q` against it *before touching anything* confirmed **222
passed**, byte-for-byte matching what was pasted into this chat and what the
prior `HANDOFF.md` claimed — no drift to reconcile this time either way, but
confirmed by the strongest available method (a real diff-by-clone) rather
than in-context reconstruction. If your sandbox can also reach `github.com`,
prefer cloning directly over reconstructing from pasted files — see Section 6.

### Phase 0.5a — the runout log (shipped)

`orchestrator.py` gained a `RunoutStep` dataclass, a module-level
`RUNOUT_STREETS` constant (`{DEAL_FLOP, DEAL_THIRD_HOLE_CARD,
REVEAL_FOURTH_STREET, REVEAL_FIFTH_STREET}` — the only streets that change
what's actually visible), and `Hand.runout: List[RunoutStep]`.
`Hand._handle_dealing_for()` now calls a new `Hand._record_runout_step()`
unconditionally at the end, for *every* street transition, so a normally-
paced hand and a fast-forwarded all-in hand build up the identical shape of
runout — a client never needs two code paths. Each step captures the street,
`community_cards` as of that point, and — only from the moment no further
betting decision is possible — every remaining active player's hole cards.
`runout` is threaded through `HandResult` (defaulted to `[]` so
`test_analytics.py`'s direct `HandResult(...)` fixtures needed no changes)
and serialized by `api.py` onto both `last_hand` and every
`/tables/{id}/hands` entry via a new `_serialize_runout()` helper.

One implementation note worth flagging explicitly: the design in
`POLISH_PLAN.md` phrased the "no further betting possible" condition as
`all(p.all_in or p.folded for p in the active players)`. It shipped as
`len(active) > 1 and all(p.all_in for p in active)`, where `active` is this
codebase's existing not-yet-folded convention (see `Hand._finalize`) — since
"active" already excludes folded players everywhere else in this file, the
two phrasings reduce to the same check. Called out here and in
`POLISH_PLAN.md` itself in case a future session diffs the two and wonders
whether something was missed; nothing was.

New tests in `test_orchestrator.py` (all passing): an all-in-preflop hand's
runout has exactly one step per relevant street, with the right
community-card counts (`[3, 3, 4, 5]`) and both hole-card sets exposed from
the very first step onward; a checked-down hand that never goes all-in
produces the identical step sequence with nothing revealed early; a hand
that folds down to one player after the flop stops its runout at exactly
that point, with no fabricated turn/river steps; an immediate preflop
fold-out has a fully empty runout.

### Phase 0.5b — showdown hand descriptions (shipped)

`hand_evaluator.py` gained `describe_hand_rank(rank: HandRank) -> str`, e.g.
`"Full House, Aces full of Kings"` or `"Two Pair, Jacks and Fours"` — a real
branch per `HandCategory` (via two small rank-name lookup tables, not a
pluralization algorithm), raising rather than silently falling back if a
future `HandCategory` is ever added without a matching branch here.
Deliberately kept separate from `HandRank.__repr__` (`poker_types.py`),
which stays the compact programmer-facing repr used for engine debugging —
changing this wording should never risk changing that one, or vice versa.

`api.py` recomputes each revealed hand's description the same way
`analytics.build_hand_record` already recomputes categories (one cheap
`evaluate_best_of` call per revealed hand, once per finished hand, nowhere
near a hot path), and adds it as `"hand_descriptions": {player_id:
description}` alongside `revealed_hands`, on both `last_hand` and every
`/tables/{id}/hands` entry. Empty for a hand that ended by fold, matching
`revealed_hands`. Deliberately did **not** add a separate `is_winner` flag —
which revealed hand(s) won is already answerable from `payouts` (a
`player_id` with `payouts.get(player_id, 0) > 0` won at least one pot), so
0.5c can cross-reference that directly instead of this field duplicating it.

New tests in `test_hand_evaluator.py`: one example per `HandCategory`
(parametrized, 10 cases including the wheel-straight-plays-5-high edge
case), plus a dedicated full-house trips-before-pair wording check.

### Both, reaching the actual API surface

New tests in `test_api.py` (7): `runout` and `hand_descriptions` both reach
`last_hand` and the persistent hand-history log, identically between the
two; an all-in hand's history entry has both hole-card sets in its first
runout step; a hand that ends by a preflop fold has an empty `runout` and an
empty `hand_descriptions` in both places.

### How this was verified (beyond the 22 new assertions)

1. `pytest -q` before touching anything (222 passed, confirmed against the
   real clone) and after every file edit, not just at the end.
2. The full suite run **5 times in a row** after all changes landed, since
   two of the new `test_api.py` tests don't pin an RNG seed (the all-in
   scenario doesn't need a specific card outcome, just the shape of the
   reveal) — no flakiness across any run. **244 passed** every time.
3. Direct smoke tests against a real `TestClient` HTTP round trip (not just
   pytest's assertions) for both a checked-down hand and a heads-up all-in,
   printing and eyeballing the actual JSON shape before writing the formal
   tests against it — e.g. confirmed a real all-in hand's first runout step
   came back as `{"street": "DEAL_FLOP", "community_cards": [...],
   "revealed_hole_cards": {<both player ids>: [...]}}`  and
   `hand_descriptions` came back as `{"...": "Two Pair, Aces and Sixes",
   "...": "Two Pair, Aces and Kings"}` for a real dealt hand.
4. `python3 example_usage.py` re-run end to end (single hand + a 9-player,
   96-hand tournament) to confirm the orchestrator API is unaffected outside
   of what changed.
5. `GET /openapi.json` and `GET /docs` both still load — confirms the new
   dict fields didn't upset FastAPI's schema generation (neither endpoint
   declares an explicit `response_model`, so this was a real risk worth
   checking, not a formality).

### What did NOT change this session

`betting_state_machine.py`, `side_pots.py`, `poker_types.py`,
`tournament_structure.py`, `tournament_balancing.py`, `analytics.py`,
`demo_showcase.py`, `static/index.html`, `CONTRIBUTING.md` — none of these
needed a change for 0.5a/0.5b. Nothing in `HandFlow`/`BettingRound` was
touched; both stay fully synchronous, matching `POLISH_PLAN.md`'s explicit
instruction not to introduce delays into the audited engine core itself —
the runout is a passive record of what already happened, not a mechanism
that changes when or how anything happens.

---

## 1. Deployment note (carried forward, unchanged)

The person running this project confirmed directly, several sessions back:
**Render does auto-deploy on every push to `main`.** Practically: once
`orchestrator.py`, `hand_evaluator.py`, `api.py`, `test_orchestrator.py`,
`test_hand_evaluator.py`, `test_api.py`, `POLISH_PLAN.md`, `README.md`, and
this file are pushed, the live demo's *backend* should update on its own —
but note Phase 0.5's actual reveal-sequence animation (0.5c) isn't in this
push at all, so the live demo won't *look* any different yet; see Section 3.
This sandbox still has no push credentials for
`github.com/GameTech-Systems/holdem-plus` (it can clone/read, per the note
in Section 0, but reading and writing are different permissions and only
the former was available here) — a human still needs to actually commit
these files.

---

## 2. What exists right now

```
poker_types.py, betting_state_machine.py, side_pots.py,
tournament_structure.py, tournament_balancing.py
  -> hand_evaluator.py  *** CHANGED (describe_hand_rank, Phase 0.5b) ***
  -> orchestrator.py    *** CHANGED (RunoutStep/RUNOUT_STREETS/Hand.runout,
                             Phase 0.5a) ***
  -> analytics.py (hands/hour, pot-vs-blinds, showdown frequency,
                    hand-strength distribution, player feedback)
  -> demo_showcase.py (three -- no, still two -- scripted showcase hands;
                        untouched this session, Phase 2's third hand is
                        still unbuilt)
  -> api.py  *** CHANGED (runout / hand_descriptions on last_hand and
             /tables/{id}/hands, Phase 0.5a+0.5b) ***
  -> static/index.html (untouched this session -- Phase 0.5c, next)

test_orchestrator.py    *** CHANGED (+4 tests, runout) ***
test_hand_evaluator.py  *** CHANGED (+11 tests incl. 10 parametrized,
                             describe_hand_rank) ***
test_api.py             *** CHANGED (+7 tests, runout + hand_descriptions
                             over the real API surface) ***
POLISH_PLAN.md  *** CHANGED (Phase 0.5's 0.5a/0.5b marked shipped with
                    exact field/file references; 0.5c's definition of done
                    updated to "not yet met") ***
README.md  *** CHANGED (new "Hand runout & showdown descriptions" section;
              test counts 222 -> 244) ***
```

**244 passed** (222 prior + 22 new this session — 4 in `test_orchestrator.py`,
11 in `test_hand_evaluator.py`, 7 in `test_api.py`).

The live instance is `https://holdem-plus-demo.onrender.com/app/` — **this
session's changes are not deployed there yet**; see Section 1. Even once
pushed, nothing about the live demo's *appearance* changes yet — 0.5a/0.5b
are new fields on API responses nothing currently reads; see Section 3.

---

## 3. What's explicitly NOT built — read this before promising anything

Carried forward, all still true: no real frontend fork (Phase 4+, separate
from and lower-priority than Phase 0.5c specifically — see the prior
session's fork-question answer, still valid, in `POLISH_PLAN.md`), no
persistence, no multi-table routing in the public API, no rate
limiting/auth beyond opaque guest IDs, the known engine simplifications
documented in their own modules, the Monte Carlo baseline is Hold'em-only,
demo mode is fixed at exactly two hands (`POLISH_PLAN.md` Phase 2's third,
side-pot-focused hand is still unstarted), no hand-history pagination in the
UI (Phase 1), the `TRADEMARKS.md` entity-naming mismatch is still
unresolved, and `welcome_message.md`'s content has still never been posted
to GitHub Discussions.

New/updated from this session:

- **Phase 0.5c — the actual felt animation — is the only remaining piece of
  Phase 0.5, and it's still entirely unbuilt.** `last_hand.runout` and
  `last_hand.hand_descriptions` are live on both `/tables/{id}/state` and
  `/tables/{id}/hands`, verified over a real HTTP round trip and covered by
  22 passing tests — but nothing in `static/index.html` reads either field
  yet. An all-in hand watched in the actual demo today still jumps straight
  to its final state with no reveal sequence, exactly as before this
  session. See `POLISH_PLAN.md`'s updated Phase 0.5 section for exactly
  what 0.5c needs to consume and how.
- **No real-browser verification of anything this session** — there was
  nothing to check in a browser, since nothing frontend-facing changed. The
  standing Phase 0 browser-click-through item is still open regardless, same
  as every prior handoff.
- **This session's changes are not pushed or redeployed** — see Section 1.

---

## 4. Open decisions (not bugs — need a person to decide, not a fix)

Unchanged from the prior handoff; none of this session's work touched any
of these:

1. **Entity naming mismatch** (`TRADEMARKS.md`) — still unresolved, now
   several handoffs running.
2. **How far to extend demo mode** — still `POLISH_PLAN.md` Phase 2's
   concrete, unstarted plan for a third (side-pot) showcase hand.
3. **Whether to build the optional multi-street Rabbit Runner reveal** for
   earlier folds (preflop/flop) — documented as a real v2 idea in
   `CONTRIBUTING.md`'s "Known extension points," explicitly not needed for
   this demo.

---

## 5. Fastest path from here forward

1. **Push this session's files** (`orchestrator.py`, `hand_evaluator.py`,
   `api.py`, `test_orchestrator.py`, `test_hand_evaluator.py`,
   `test_api.py`, `POLISH_PLAN.md`, `README.md`, this file) to `main`. Given
   the auto-deploy confirmation in Section 1, this alone gets the new API
   fields live — but see the next item, since nothing will *look* different
   yet.
2. **`POLISH_PLAN.md` Phase 0.5c** — the actual reveal-sequence animation in
   `static/index.html`. Now fully unblocked: `last_hand.runout` and
   `last_hand.hand_descriptions` are shipped, live-tested, and don't require
   touching `orchestrator.py` or `api.py` again for this phase. This is the
   piece that genuinely needs the real-browser click-through this project
   has chronically struggled to actually do — build with the jsdom-scaffold
   discipline described in Section 6, but don't call Phase 0.5 done without
   someone watching an actual all-in hand animate on an actual screen.
3. **The standing Phase 0 real-browser click-through** — still open across
   many handoffs now, independent of Phase 0.5c specifically.
4. **`POLISH_PLAN.md` Phase 1** — hand-history pagination, a fetch-failure
   state, and the multi-way side-pot test. Untouched this session.
5. **`POLISH_PLAN.md` Phase 2** — the third (side-pot) demo showcase hand.
   Also untouched; note `hand_descriptions` (0.5b, now shipped) makes this
   phase's "narration makes the side-pot mechanic legible" goal
   meaningfully easier, since a real description string is now available
   to build that narration around instead of just raw category enums.
6. **Phase 3 / Phase 4+** — analytics visualization, then the real frontend
   fork question. Also untouched.

---

## 6. If you're a fresh Claude session picking this up

**Try `git clone https://github.com/GameTech-Systems/holdem-plus.git`
first, before reconstructing anything from pasted files.** It worked in
this session's sandbox (see Section 0) despite prior sessions reporting it
didn't work in theirs — network access appears to vary session to session,
so don't assume either way; just try it, and fall back to reconstructing
from whatever's pasted into your own chat only if it fails. If it succeeds,
diff a couple of files you'd expect to be stable (this `HANDOFF.md`,
`POLISH_PLAN.md`) against what's pasted into your chat before trusting
either source completely — this session did, found no drift, but that's one
data point, not a standing guarantee for yours.

Run `pytest -q` first thing either way. Baseline going into your session:
**244 passed.**

If your task is Phase 0.5c: read `POLISH_PLAN.md`'s Phase 0.5 section in
full first, including the 0.5a/0.5b implementation notes now folded into
it. The fork question was already answered by the prior session and
doesn't need re-litigating. The jsdom-scaffold approach from earlier
frontend sessions (`JSDOM(html, { runScripts: "dangerously" })`, call the
real render functions with hand-built state mirroring what `api.py` now
actually returns, assert on the resulting DOM, delete the scaffold before
finishing) is the right tool here — this is genuinely new JS behavior (an
animated sequence, not a static render), not a small enough change to
downgrade to a lighter syntax-only check the way a couple of past sessions
reasonably did for smaller edits. It is still not a substitute for a real
browser — Phase 0.5's definition of done in `POLISH_PLAN.md` explicitly
requires someone watching this happen live, and no amount of jsdom rigor
changes that bar.

If your task touches the engine (`orchestrator.py` in particular): this
session's `_record_runout_step()` is now one more thing to keep in sync if
you ever change `_handle_dealing_for()`'s street-handling logic — it's
called unconditionally at the end of that method for every street, so a new
dealing step would silently get no runout coverage unless it's also added
to `RUNOUT_STREETS`. Not a trap exactly (nothing breaks silently; it would
just under-report), but worth knowing it's there.
