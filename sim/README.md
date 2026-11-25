# Hold'em Plus equity simulation: technical replication

Every equity number on the [Strategy Guide](https://holdem-plus-demo.onrender.com/app/strategy.html) comes from `holdem_plus_equity.c`. This page explains exactly what it computes and how to reproduce it.

## Reproduce it

**On GitHub:** Actions, then "Equity simulation", then "Run workflow". The run builds the simulator, runs every validation layer listed under **Validation** below, runs the simulation, checks that the numbers on the Strategy Guide still match it, and uploads `results.json` as an artifact. The job summary shows a sanity table with standard errors.

**Locally:**
```bash
gcc -O2 -Wall -Wextra -o equity sim/holdem_plus_equity.c -lm
./equity --selftest                         # exact evaluator counts, about 20 seconds
python sim/exhaustive_check.py ./equity     # needs the repo's Python files, no packages
python sim/edge_cases.py ./equity
python sim/cross_check.py ./equity
python sim/third_card_odds.py               # exact third-card odds quoted on the page
./equity > results.json                     # about a minute
python sim/check_published.py results.json  # does static/strategy.html still match?
```
With the default seed and trial counts, `results.json` should match the numbers on the page exactly (same RNG sequence; floating-point summing is deterministic on x86-64), and `check_published.py` verifies that. Use `--hu-trials`, `--six-trials` and `--seed` to rerun with other settings. Arguments are validated: the seed must be a nonzero integer (xorshift never leaves state 0, so a zero seed used to make every deal identical and still print plausible-looking JSON), trial counts must be integers of at least 2, and anything unrecognized is an error. The seed and trial counts used are recorded in `results.json` under `meta`.

## What is computed

- **Equity** is your expected share of the pot if every player is all-in before the flop and the hand is dealt out: a win counts 1, a tie counts 1 divided by the number of tied players. All-in EV per chip staked is `players × equity − 1`.
- **Opponents** hold random hands and never fold. This measures raw hand strength, not profit against real opponents, who fold weak hands.
- **Heads-up** is 1 opponent (300,000 deals per starting hand); **6-handed** is 5 opponents (150,000 deals). Each estimate has a standard error (SE) that is reported per hand in `results.json`: at most 0.09 points heads-up and 0.13 six-handed (the worst case is a pot share near 50%; most hands are lower). A 95% margin is about twice the SE. Do not read "±0.1" as a universal accuracy figure.
- **Starting hands** use one fixed suit assignment per class (169 classes). Suits are symmetric, so this loses nothing.

### Texas Hold'em vs Hold'em Plus on the same deals

Each simulated deal draws, from the unseen cards: every opponent's two hole cards, five board cards, your third card, and each opponent's third card. Hold'em scores 2 hole cards + 5 board (best 5 of 7). Plus scores 3 hole cards + 5 board (best 5 of 8). Because both games use the same draw, the difference between them is a paired comparison. It still has sampling error (reported as `se.*.d`, about 0.09 points heads-up), but that is roughly 30% smaller than the error of two independent runs. Differences under about 0.2 points heads-up (0.3 six-handed) are within noise; 166 of 169 heads-up hands clear that bar by more than two SE.

In the real game the third card is dealt after the flop, from a deck with the flop and a burn removed. Drawing it uniformly from the unseen cards is statistically identical. Folded players receive no third card; this simulation assumes nobody folds.

### Third-card views

For heads-up Plus, each deal is bucketed by your third card: **pairs you** (its rank matches a hole card, so trips for a pair), **suits you** (suited hands only, same suit as your hole cards), or **misses** (neither). The page shows average equity within each bucket. These are conditional on the third card only, averaged over all flops. Because the third card is dealt after the flop, the chance that it is an out is outs/50 averaged over flops and (outs still unseen)/47 once the flop is known; `third_card_odds.py` enumerates both exactly and is the source of the odds quoted in the guide.

### Three-card shapes

14 fixed example holdings (for example `As9s4s`, `JsTh9d`). Each is simulated all-in before the flop against random opponents who also hold three cards, so it measures the raw strength of the shape, not a real decision point.

## Validation

There are three separate layers, because a correct evaluator says nothing about whether the simulator deals and scores correctly.

**1. Hand evaluation**
- `./equity --selftest` enumerates every 5-card and every 7-card hand and checks the category counts against the classical exact values (2,598,960 and 133,784,560 hands). It also checks that for 1,000,000 random hands each of 6, 7 and 8 cards, the evaluator returns exactly the best of all 5-card subsets.
- `exhaustive_check.py` ranks one representative of every one of the 7,462 distinct 5-card hands with `hand_evaluator.py` and requires the C evaluator's codes to be strictly increasing in that order: every kicker and tie-break agrees.
- `edge_cases.py` runs 24 hand-derived showdowns (competing kickers on quads, two sets, three pairs, six suited cards, wheels, board plays, ties) through both evaluators.
- `cross_check.py` compares the C evaluator with `hand_evaluator.evaluate_best_of` on 20,000 random showdown pairs each for 7 and 8 cards. Random sampling reaches rare hands slowly, so it is a backstop, not the main proof.
- Not covered exhaustively: all 752 million 8-card hands. The 8-card case rests on the 5-card exhaustive ordering plus the 1,000,000-hand subset-consistency test. Planting bugs in the evaluator (a wrong quads kicker, a missing second-trips pair, a wheel scored ace-high, a lost third pair kicker, ...) showed that no single layer catches everything: the self-test missed a quads-kicker bug that the exhaustive ordering check caught, and the reverse, which is why all four run.

**2. The simulator program**
- Invalid arguments (zero or non-numeric seed or trials, unknown options) exit with an error. CI asserts this.
- Cards are drawn with a partial Fisher-Yates shuffle of a deck that starts with 50 (or 49) distinct cards, so a duplicate card cannot occur by construction. The shuffle index uses `rnd() % n`; with a 64-bit generator and n at most 50 the modulo bias is about 1e-18, far below sampling error, so rejection sampling was deliberately not added (it would change nothing visible).
- The two shape equities in each `sh` entry are now computed in an explicit order. They used to be two calls inside one `printf`, whose argument evaluation order C does not define, so the published numbers depended on the compiler. The order that gcc used is kept, so published numbers did not change.

**3. The published numbers**
- The workflow asserts Texas Hold'em heads-up equities against well-known values (AA 85.2%, KK 82.4%, AKs 67.1%, AKo 65.2%, 72o 34.6%) within 0.5 points.
- `check_published.py` requires the data embedded in `static/strategy.html` to equal `results.json` for the default seed and trial counts.
- Still missing: an exact-enumeration benchmark of full preflop equity (an AA-versus-random enumeration is about 2 billion boards). The all-in equities are therefore validated by the known Hold'em values above, not by an exact Hold'em Plus reference.

## Limits

- Equity against random hands is not EV against real opponents, who fold weak hands. Use it to rank hands, not to size bets. All-in EV per chip staked, `players × equity − 1`, assumes equal stacks, no rake and nobody folding.
- Preflop all-in equity ignores position, stack depth, and postflop play, which is where most of the real strategy lives.
- The tiers and opening ranges on the Strategy Guide are judgment informed by these numbers, not solver output.

## Output format (`results.json`)

`hu.h`, `hu.p`: heads-up equity, Hold'em and Plus. `six.h`, `six.p`: 6-handed. `hu.pr`, `hu.su`, `hu.mi`: Plus heads-up by third-card bucket (`null` where impossible). Each array has 169 values in chart order: row = first rank, column = second rank (A to 2), pairs on the diagonal, suited above it, offsuit below. `sh`: `[name, cards, heads-up, 6-handed, heads-up SE, 6-handed SE]` for each three-card shape. `se.hu` and `se.six` each hold `h`, `p` and `d` (Plus minus Hold'em, paired): the standard error in percentage points of the matching equity, in the same chart order. The three-card-bucket arrays (`pr`, `su`, `mi`) have no SE. `meta`: the seed (as a string, since it exceeds 2^53) and trial counts used.
