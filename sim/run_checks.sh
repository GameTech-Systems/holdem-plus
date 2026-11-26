#!/usr/bin/env bash
# One command that runs every validation layer. The unpack-zip workflow runs this before committing anything,
# and you can run it yourself:   bash sim/run_checks.sh [all|py|sim]
#
#   py   the pytest suite (engine, API, orchestrator, ...)                                   ~10 seconds
#   sim  build the C simulator, run every evaluator/simulator check, rerun the default-seed
#        simulation and require static/strategy.html to match it exactly                      ~2 minutes
#   all  both (default)
#
# Build products go to a temp directory, so the working tree stays clean. Exits non-zero on the first failure.
set -euo pipefail
cd "$(dirname "$0")/.."
mode="${1:-all}"
case "$mode" in all|py|sim) ;; *) echo "usage: bash sim/run_checks.sh [all|py|sim]" >&2; exit 2 ;; esac

step() { printf '\n=== %s ===\n' "$*"; }

run_py() {
  step "pytest"
  python3 -m pip install -q -r requirements.txt
  python3 -m pytest -q
}

run_sim() {
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT
  step "build simulator"
  gcc -O2 -Wall -Wextra -o "$tmp/equity" sim/holdem_plus_equity.c -lm
  step "evaluator self-test (exact 5- and 7-card counts, 6/7/8-card subset consistency)"
  "$tmp/equity" --selftest
  step "evaluator ordering over all 7,462 distinct 5-card hands"
  python3 sim/exhaustive_check.py "$tmp/equity"
  step "evaluator edge cases"
  python3 sim/edge_cases.py "$tmp/equity"
  step "evaluator random cross-check against hand_evaluator.py"
  python3 sim/cross_check.py "$tmp/equity" 20000
  step "invalid arguments are rejected"
  for args in "--seed 0" "--seed abc" "--seed -1" "--hu-trials 0" "--six-trials x" "--bogus"; do
    # shellcheck disable=SC2086
    if "$tmp/equity" $args >/dev/null 2>&1; then echo "accepted invalid arguments: $args"; exit 1; fi
  done
  echo "all six invalid invocations rejected"
  step "exact third-card odds"
  python3 sim/third_card_odds.py >/dev/null && echo "assertions passed"
  step "default-seed simulation, then compare with static/strategy.html"
  "$tmp/equity" > "$tmp/results.json"
  python3 sim/check_published.py "$tmp/results.json" static/strategy.html
}

[ "$mode" = sim ] || run_py
[ "$mode" = py ]  || run_sim
printf '\nALL CHECKS PASSED (%s)\n' "$mode"
