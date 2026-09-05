# Contributing to Hold'em Plus

Thanks for looking at this project. This repo is the open, reference
implementation of the Hold'em Plus rules engine and demo API — the part
of the project meant to be forked, read, and built on with as little
friction as possible.

## Scope of this repo

This repo contains the generic game engine and demo API only: hand
evaluation, betting/side-pot logic, tournament structure, and a
FastAPI/WebSocket demo server. It does **not** contain, and will not
accept PRs adding:

- Dealer Assist Technology (DAT) hardware integration
- Regulatory audit logging or compliance modules
- Secure/certified shuffler implementations intended for real-money use
- Real-money payment, rake, or tournament-network fee logic

Those live in separate, private repositories maintained by GameTech
Systems, because they require independent certification (e.g. GLI or
iTech Labs testing) before any real-money deployment. If you're
interested in that side of the project, open an issue and we'll point
you in the right direction rather than merging it here.

## Getting set up

```bash
git clone <this-repo>
cd holdem-plus
pip install -r requirements.txt --break-system-packages   # if needed
pytest -q                     # should show all tests passing
python3 example_usage.py      # runs a hand + a small tournament, no network
uvicorn api:app --reload      # real server at http://127.0.0.1:8000
```

Interactive API docs are at `/docs` once the server's running.

## Before you open a PR

- **Every module has a test file** (`test_*.py`). If you're changing
  behavior, add or update tests in the matching file rather than
  relying on manual testing — `pytest -q` is the bar for merging.
- **Read the module docstrings first.** Several modules document
  deliberate simplifications and *why* they exist (e.g. the side-pot
  merge-on-all-folded-layer behavior in `side_pots.py`, or why preflop
  action order is hand-built in `orchestrator.py` instead of using the
  generic helper in `betting_state_machine.py`). If your change touches
  one of these, either respect the documented reasoning or update the
  docstring to explain why it no longer applies.
- **Keep engine code dependency-free.** Everything below `api.py` is
  intentionally standard-library Python so it's easy to audit — poker
  side-pot bugs are one of the most disputed bug classes in real poker
  software, and auditability matters more than convenience here.
- **Small, focused PRs** are much easier to review than large ones,
  especially for anything touching betting legality or pot math.

## Developer Certificate of Origin (DCO)

Instead of a Contributor License Agreement, this project uses the
lightweight **Developer Certificate of Origin** (the same approach used
by the Linux kernel, Docker, and many other large open-source
projects): https://developercertificate.org/

By adding a `Signed-off-by` line to your commits, you're certifying
that you wrote the contribution or otherwise have the right to submit
it under this project's license. Add the sign-off automatically with:

```bash
git commit -s -m "Your commit message"
```

A bot will check this on every PR. No separate form, account, or
e-signature is required.

## Licensing of contributions

This project is licensed under Apache License 2.0 (see `LICENSE`).
By submitting a contribution, you agree it's licensed to the project
and to downstream users under those same terms — this project does not
require a separate copyright assignment or CLA. You keep your
copyright and get attribution via normal Git history.

## Trademarks

"Hold'em Plus," "Dealer Assist Tech," "Billion Dollar Challenge," and
associated logos are trademarks, not covered by the code license — see
`TRADEMARKS.md`. You're free to fork and run this code under a
different name; using the above names for your own deployment requires
separate permission.

## Issue labels

- `good first issue` — small, self-contained, good entry point
- `bug` — confirmed incorrect behavior, ideally with a failing test
- `enhancement` — new feature or improvement to existing behavior
- `question` — needs discussion before any code should be written

## Code of conduct

Be respectful, assume good faith, and keep disagreements about code
focused on the code. Full details in `CODE_OF_CONDUCT.md` (adapted from
the Contributor Covenant).
