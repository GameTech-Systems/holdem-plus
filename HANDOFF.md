# Hold'em Plus: Session Handoff

Current state only. Stable orientation is in `ORIENTATION.md`; the backlog is in `POLISH_PLAN.md`; the audit
record is in `docs/AUDIT_2026-11.md`. Older session write-ups (the Phase 0.5c reveal-sequence notes, the first
audit pass) are in git history: `git show 555ad94:HANDOFF.md`.

If `sim/run_checks.sh` does not exist in the repo you are looking at, the 2026-11-25 update zip has not been
applied yet; see section 1.

---

## 0. Latest session (2026-11-25, second pass): verify the hand upload, make zip updates work

**Starting point.** The previous session's audit work had been uploaded by hand because its zip/workflow attempt
failed. Checked from a fresh clone of `main` at `00a32c9`.

**Verified, all good.**
- Every uploaded file is in the right place and byte-identical to the copy in the Claude project: `static/index.html`,
  `static/strategy.html`, `sim/{holdem_plus_equity.c,README.md,cross_check.py,edge_cases.py,exhaustive_check.py,
  third_card_odds.py,check_published.py}`, `.github/workflows/equity-sim.yml`, `HANDOFF.md`, and the engine, API and
  test files.
- `pytest`: **244 passed**.
- Simulation pipeline, run end to end exactly as the workflow does: clean build, `--selftest`, exhaustive 7,462-hand
  ordering, 24 edge cases, 40,000-showdown cross-check, six invalid-argument rejections, third-card odds
  assertions, then a full default-seed run (41 s) that reproduces `strategy.html`'s embedded data exactly.
- The Strategy Guide's prose numbers match the data (list in `docs/AUDIT_2026-11.md`).

**Found and fixed (in the update bundle; see section 1 for status).**
1. **`sim/run_checks.sh` never existed.** `unpack-zip.yml` calls it, so any zip touching `sim/` or `static/` would
   have failed at validation, and the previous session's "every step passed locally" did not cover this. Created.
2. **The unpack allowlist was far too narrow**: only `sim/*`, `static/strategy.html` and three root docs, so a zip
   containing `static/index.html`, `api.py`, any test, or `orchestrator.py` was refused. Widened (rules in
   `ORIENTATION.md`); legal and deployment files stay protected.
3. **Unsafe paths were silently rewritten.** `../x.py` and `C:/x.py` were treated as a "wrapper folder" and stripped
   to `x.py` before the safety check ran. Now refused first. (Never an escape from the repo, but wrong.)
4. **Zip names with spaces broke the commit step** (`xargs` split on whitespace). Fixed with `xargs -d '\n'`.
5. Validation now matches the change: docs-only zips run nothing, Python changes run pytest, `sim/` or strategy-page
   changes run the full simulation checks, and a failure writes a "nothing was committed" note to the run summary.
6. **`POLISH_PLAN.md` had been deleted** on 2026-09-11 (commit `dab98db`) and never restored, though this file and
   the README lean on it. Restored, condensed and updated.
7. A stray duplicate `unpack-zip.yml` sat in the repo root (the real one is in `.github/workflows/`). Delete it.
8. Root `README.md` predated `sim/` and the Strategy Guide. Updated.
9. New `tests.yml` runs pytest on every push and pull request (nothing did before; only the simulation workflow ran
   automatically, and only for `sim/` paths).

**Rehearsal.** The workflow's real `run:` blocks were extracted from the YAML and run against a local bare git
remote with about 30 zips: good, wrapper-folder, spaces in the name, docs-only, workflow file without a token,
unchanged files, no zip, corrupt zip, symlink, traversal, absolute and drive paths, protected and disallowed
files, oversized, too many files, duplicates across zips, a zip with a failing test, and a zip with a tampered
strategy-page number. The last two were run with the real validation and correctly committed nothing and left the
zip in place. `actionlint` is clean on all three workflows.

**Not verified, honestly.**
- **GitHub Actions has never run these workflows.** The rehearsal reproduces the logic, not GitHub's runner,
  permissions or settings. The first real zip upload is the test. Check Settings, Actions, General: workflow
  permissions should allow read and write (the workflow requests `contents: write` itself, but an organization
  policy can cap it).
- The connector used this session was **read-only**, so nothing was pushed. Everything is in the update bundle.
- The live Render site was not reachable from this session; whether it serves the new `strategy.html` is unchecked.
- Nothing has been looked at in a real browser, including the Strategy Guide at phone width and the Phase 0.5c
  reveal sequence from the previous sessions.

---

## 1. Do these next, in order

1. **By hand** (workflow files cannot be installed by the workflow itself without a token secret): upload
   `unpack-zip.yml` and `tests.yml` into `.github/workflows/` (the first replaces the installed one), and delete
   the stray root `unpack-zip.yml`.
2. Upload the update zip at the repo root. In Actions, "Unpack uploaded zip" should go green in about 3 minutes and
   commit `Unpack ...`. This is the first real test of the mechanism. If it fails, nothing was committed: read
   the summary, delete the zip, fix, retry.
3. Actions, "Equity simulation", Run workflow: should be green and attach `results.json`.
4. Optional: add a `WORKFLOW_PAT` secret so future zips may also carry workflow files.
5. Open `/app/strategy.html` on a phone and a desktop; expand "Show the chart data as a table". Then the Phase 0
   click-through in `POLISH_PLAN.md`, which still blocks calling Phase 0.5 done.
6. Open decisions: the `TRADEMARKS.md` entity-name mismatch ("GamingTech, LLC" vs "GameTech Systems"), and posting
   `welcome_message.md` to GitHub Discussions.

---

## 2. Facts that save time

**Engine.** Dealing is front-loaded: `STREET_ORDER` is DEAL_HOLE_CARDS, PREFLOP_BETTING, DEAL_FLOP,
DEAL_THIRD_HOLE_CARD, DEAL_FOURTH_STREET_FACEDOWN, DEAL_FIFTH_STREET_FACEDOWN, FLOP_BETTING, REVEAL_FOURTH_STREET,
TURN_BETTING, REVEAL_FIFTH_STREET, RIVER_BETTING, SHOWDOWN, HAND_COMPLETE. The flop, the third hole card and both
facedown cards are all dealt before flop betting opens. `orchestrator.RUNOUT_STREETS` says *which* streets get a
runout step, not *when* they happen; trust `STREET_ORDER` for timing. A new dealing step gets no runout coverage
unless added to `RUNOUT_STREETS`.

**Reveal sequence (`static/index.html`).** `render()` is a dispatcher. `revealChainActive` is the only mutual-
exclusion guard; `revealedHandNumber` stops a hand's reveal re-running on every poll (set it before deciding
whether there is anything to animate); every pause must go through `revealSleep()` or Skip cannot cut it short;
`runRevealSequence()` re-enters via `render(latestReceivedState)`. Rebuild jsdom fixtures from real `TestClient`
output, never from memory of the shape. jsdom checks structure, not layout: seat crowding at 4+ and 6+ seats is
still unseen.

**Strategy Guide data.** `sim/holdem_plus_equity.c` produces `results.json`; the same JSON is embedded in
`static/strategy.html` as `const D=...`; `sim/check_published.py` fails if they differ (default seed and trial
counts only). If you change the simulator or the guide's numbers, regenerate and re-embed together, and run
`bash sim/run_checks.sh sim`.

**Equity numbers are raw strength, not profit.** Keep that wording wherever they appear.

---

## 3. Not built

No real frontend fork (Phase 4+), no persistence, no multi-table routing in the public API, no rate limiting or
auth beyond guest ids, no third (side-pot) showcase hand, no hand-history pagination, no analytics screen, no
conditional third-card calculator, no position-aware or fold-equity simulation. Details and sizing are in
`POLISH_PLAN.md`.
