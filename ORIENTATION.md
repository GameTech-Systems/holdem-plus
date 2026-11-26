# Hold'em Plus: orientation (read this first)

This file changes rarely. For what happened most recently read `HANDOFF.md`; for what to do next read
`POLISH_PLAN.md`. Last reviewed 2026-11-25.

## What this project is

A play-money demo of **Hold'em Plus** (Texas Hold'em plus a third hole card dealt after the flop; showdown is
best 5 of 8), built so poker rooms and casinos can try it. Three parts:

1. **Game engine + API** (Python, FastAPI): plays real hands, tournaments, side pots, Rabbit Runner.
2. **Demo client** (`static/index.html`, vanilla JS): the table at `/app/`, a scripted demo, hand history.
3. **Equity simulation + Strategy Guide** (`sim/`, C and Python; `static/strategy.html`): every number on the
   guide comes from `sim/holdem_plus_equity.c`.

Live: https://holdem-plus-demo.onrender.com/app/ (Render auto-deploys on every push to `main`).
Repo: https://github.com/GameTech-Systems/holdem-plus

## Repo map

| Path | What it is |
|---|---|
| `poker_types.py`, `hand_evaluator.py`, `betting_state_machine.py`, `side_pots.py` | Engine primitives. Dependency-free, heavily tested. |
| `tournament_structure.py`, `tournament_balancing.py`, `orchestrator.py` | Blinds clock, multi-table balancing; `Hand` and `Tournament` wire everything together. |
| `analytics.py`, `demo_showcase.py` | Instrumentation; two scripted showcase hands. |
| `api.py` | REST + WebSocket layer. In-memory, single process. |
| `test_*.py` | 244 tests (`pytest -q`). |
| `static/index.html` | The table client. `static/strategy.html` is the Strategy Guide (data embedded as `const D=...`). |
| `sim/` | C simulator, evaluator validation scripts, `run_checks.sh`, `README.md` (replication notes). |
| `.github/workflows/` | `equity-sim.yml` (simulation), `tests.yml` (pytest), `unpack-zip.yml` (zip updates). |
| `HANDOFF.md`, `POLISH_PLAN.md`, `docs/` | Current state, backlog, audit records. |
| `Dockerfile`, `render.yaml`, `fly.toml`, `Procfile`, `DEPLOYMENT.md` | Deployment. |
| `LICENSE`, `NOTICE`, `TRADEMARKS.md`, `CODE_OF_CONDUCT.md` | Legal. Edit by hand only. |

## First five minutes in a new session

1. `git clone https://github.com/GameTech-Systems/holdem-plus.git` (network access has varied between sessions;
   try it before assuming either way). If it works, the clone is the source of truth, not any pasted copy.
2. `bash sim/run_checks.sh py` should end `244 passed`. `bash sim/run_checks.sh sim` (about 2 minutes) runs every
   simulator and evaluator check and confirms `static/strategy.html` still matches a fresh simulation exactly.
3. Read `HANDOFF.md` section 0 and 1.

## How changes reach the repo

Sessions usually cannot push (no credentials, or a read-only GitHub connector). The standard path is a zip:

- Upload one `.zip` to the **repository root** (GitHub: Add file, Upload files). It may contain the files with
  their repo-relative paths, or one wrapper folder around them.
- `unpack-zip.yml` unpacks it, runs the validation that fits what changed, and only then commits to `main` and
  deletes the zip. If anything is wrong **nothing is committed and the zip stays**; read the failed run's summary,
  delete the old zip, upload a corrected one.
- Accepted: root `*.py`, `requirements.txt`, `.gitignore`, root `*.md`, `docs/*.md`, `sim/*.{c,py,md,sh}`,
  `static/*.{html,css,js,svg}`. Refused: legal and deployment files, anything outside those, unsafe paths.
- It can only add or replace. Deleting a file is done in the GitHub UI.
- Workflow files (`.github/workflows/*.yml`) are skipped unless the repo secret `WORKFLOW_PAT` (a personal access
  token with `workflow` scope) exists. Without it, upload those by hand.

## Rules of the project

- **"Done" means a person clicked through the deployed URL in a real browser.** Passing tests and jsdom runs are
  necessary, never sufficient. Say plainly which of the two a piece of work has reached.
- **Raw equity is not profit.** Every simulator number is all-in equity against random hands that never fold. The
  Strategy Guide's tiers and opening ranges are judgment informed by it, labelled provisional.
- Keep everything above `api.py` dependency-free. Keep the equity simulator simple and auditable; build any
  strategic simulation separately beside it.
- When a doc and the code disagree, believe the code, then fix the doc.
- Every session: run the checks first, append to `HANDOFF.md` section 0 last, and do not let it grow without
  bound (move old session notes to git history, as the 2026-11-25 rewrite did).

## What belongs in the Claude project's "context box"

Keep only the three small, stable documents: `ORIENTATION.md`, `HANDOFF.md`, `POLISH_PLAN.md`. Do **not** keep
code, tests, or the HTML pages there: the repo is authoritative, copies in the box go stale silently (this has
already caused one drift incident), and they spend context on files a session can clone in seconds. Refresh the
three documents from the repo at the start of each session.
