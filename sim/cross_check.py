"""Cross-checks the C simulator's hand evaluator against the project's own
hand_evaluator.evaluate_best_of on random 7- and 8-card showdowns.
Run from anywhere: python sim/cross_check.py ./equity [pairs-per-size]"""
import os, random, subprocess, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from hand_evaluator import evaluate_best_of
from poker_types import parse_cards

exe = sys.argv[1] if len(sys.argv) > 1 else "./equity"
pairs = int(sys.argv[2]) if len(sys.argv) > 2 else 20000
RK, SU = "23456789TJQKA", "cdhs"
txt = lambda c: RK[c >> 2] + SU[c & 3]
rng = random.Random(2024)
lines, expected = [], []
for n in (7, 8):
    for _ in range(pairs):
        d = rng.sample(range(52), 5 + 2 * (n - 5))
        board, a, b = d[:5], d[5:5 + n - 5], d[5 + n - 5:]
        A, B = a + board, b + board
        ra = evaluate_best_of(parse_cards(" ".join(map(txt, A))))
        rb = evaluate_best_of(parse_cards(" ".join(map(txt, B))))
        expected.append((ra > rb) - (ra < rb))
        lines.append(f"{n} " + " ".join(map(str, A + B)))
out = subprocess.run([exe, "--cmp"], input="\n".join(lines) + "\n", capture_output=True, text=True, check=True).stdout.split()
bad = [i for i, (o, e) in enumerate(zip(map(int, out), expected)) if o != e]
print(f"{len(expected)} showdowns compared, {len(bad)} disagreements")
sys.exit(1 if bad else 0)
