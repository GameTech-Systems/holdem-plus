"""Exhaustive 5-card ordering check: the C evaluator against hand_evaluator.evaluate_5.

There are exactly 7,462 distinct 5-card poker hands once suits are ignored (apart from flushes). This builds
one representative of every one of them, ranks all 7,462 with the Python evaluator, and checks that the C
evaluator's rank codes are strictly increasing in that same order. That is a complete proof that the two
evaluators agree on every 5-card comparison, including every kicker and tie-break, which random sampling
(cross_check.py) reaches only slowly for rare hands such as quads and straight flushes.

The C evaluator's 6-, 7- and 8-card results are then tied to this 5-card ordering by `./equity --selftest`
(best of every 5-card subset), so together the two checks cover the 8-card showdown Hold'em Plus uses.

Run from anywhere: python sim/exhaustive_check.py ./equity"""
import itertools, os, subprocess, sys
from collections import Counter
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from hand_evaluator import evaluate_5
from poker_types import parse_cards

exe = sys.argv[1] if len(sys.argv) > 1 else "./equity"
RK, SU = "23456789TJQKA", "cdhs"

def representatives():
    """One 5-card hand (as rank/suit index pairs) for each of the 7,462 distinct poker hands."""
    for combo in itertools.combinations_with_replacement(range(13), 5):
        counts = Counter(combo)
        if max(counts.values()) > 4:
            continue
        if len(counts) == 5:                                   # five distinct ranks: flush and non-flush versions
            yield [(r, 0) for r in combo]
            yield [(r, i % 4) for i, r in enumerate(combo)]
        else:                                                  # paired hands can never be flushes
            seen = Counter()
            hand = []
            for r in combo:
                hand.append((r, seen[r]))
                seen[r] += 1
            yield hand

hands = list(representatives())
assert len(hands) == 7462, f"expected 7462 distinct hands, built {len(hands)}"
ranked = []
for h in hands:
    text = " ".join(RK[r] + SU[s] for r, s in h)
    ranked.append((evaluate_5(parse_cards(text)), h))
ranked.sort(key=lambda x: x[0])
assert all(a[0] < b[0] for a, b in zip(ranked, ranked[1:])), "Python evaluator ties between distinct classes"

lines = ["5 " + " ".join(str(r * 4 + s) for r, s in h) for _, h in ranked]
out = subprocess.run([exe, "--eval"], input="\n".join(lines) + "\n", capture_output=True, text=True, check=True).stdout.split()
codes = list(map(int, out))
assert len(codes) == 7462
bad = [i for i in range(1, len(codes)) if not codes[i - 1] < codes[i]]
print(f"{len(codes)} distinct 5-card hands checked, {len(bad)} ordering disagreements")
for i in bad[:5]:
    print("  python order puts", ranked[i - 1][1], "below", ranked[i][1], "but C codes are", codes[i - 1], codes[i])
sys.exit(1 if bad else 0)
