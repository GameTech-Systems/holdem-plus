# Hold'em Plus equity simulation: technical replication

Every equity number on the [Strategy Guide](../static/strategy.html) comes from `holdem_plus_equity.c`. This page explains exactly what it computes and how to reproduce it.

## Reproduce it

**On GitHub:** Actions, then "Equity simulation", then "Run workflow". The run builds the simulator, cross-checks its evaluator against this repo's `hand_evaluator.py`, runs the simulation, and uploads `results.json` as an artifact. The job summary shows a sanity table.

**Locally:**
```bash
gcc -O2 -Wall -o equity sim/holdem_plus_equity.c
python sim/cross_check.py ./equity          # needs the repo's Python files, no packages
./equity > results.json                     # about a minute
```
With the default seed and trial counts, `results.json` should match the numbers on the page (same RNG sequence; floating-point summing is deterministic on x86-64). Use `--hu-trials`, `--six-trials` and `--seed` to rerun with other settings.

## What is computed

- **Equity** is your expected share of the pot if every player is all-in before the flop and the hand is dealt out: a win counts 1, a tie counts 1 divided by the number of tied players. All-in EV per chip staked is `players × equity − 1`.
- **Opponents** hold random hands and never fold. This measures raw hand strength, not profit against real opponents, who fold weak hands.
- **Heads-up** is 1 opponent (300,000 deals per starting hand); **6-handed** is 5 opponents (150,000 deals). Standard error is about ±0.1 points.
- **Starting hands** use one fixed suit assignment per class (169 classes). Suits are symmetric, so this loses nothing.

### Texas Hold'em vs Hold'em Plus on the same deals

Each simulated deal draws, from the unseen cards: every opponent's two hole cards, five board cards, your third card, and each opponent's third card. Hold'em scores 2 hole cards + 5 board (best 5 of 7). Plus scores 3 hole cards + 5 board (best 5 of 8). Because both games use the same draw, the difference between them is an exact paired comparison with much less noise than two independent runs.

In the real game the third card is dealt after the flop, from a deck with the flop and a burn removed. Drawing it uniformly from the unseen cards is statistically identical. Folded players receive no third card; this simulation assumes nobody folds.

### Third-card views

For heads-up Plus, each deal is bucketed by your third card: **pairs you** (its rank matches a hole card, so trips for a pair), **suits you** (suited hands only, same suit as your hole cards), or **misses** (neither). The page shows average equity within each bucket. These are conditional on the third card only, averaged over all flops.

### Three-card shapes

14 fixed example holdings (for example `As9s4s`, `JsTh9d`). Each is simulated all-in before the flop against random opponents who also hold three cards, so it measures the raw strength of the shape, not a real decision point.

## Validation

1. `cross_check.py` compares the C evaluator with `hand_evaluator.evaluate_best_of` on 20,000 random showdown pairs each for 7 and 8 cards, using the repo's own comparison. Expect 0 disagreements.
2. The workflow asserts Texas Hold'em heads-up equities against well-known values (AA 85.2%, KK 82.4%, AKs 67.1%, AKo 65.2%, 72o 34.6%) within 1 point.

## Limits

- Equity against random hands is not EV against real opponents. Use it to rank hands.
- Preflop all-in equity ignores position, stack depth, and postflop play, which is where most of the real strategy lives.
- The tiers and opening ranges on the Strategy Guide are judgment informed by these numbers, not solver output.

## Output format (`results.json`)

`hu.h`, `hu.p`: heads-up equity, Hold'em and Plus. `six.h`, `six.p`: 6-handed. `hu.pr`, `hu.su`, `hu.mi`: Plus heads-up by third-card bucket (`null` where impossible). Each array has 169 values in chart order: row = first rank, column = second rank (A to 2), pairs on the diagonal, suited above it, offsuit below. `sh`: `[name, cards, heads-up, 6-handed]` for each three-card shape.
