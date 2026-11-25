"""Deterministic edge-case showdowns for the evaluators.

Each case is a shared board plus two hole-card sets (3 cards = Hold'em Plus, 2 cards = Hold'em) and the
expected outcome, worked out by hand: +1 if hand A wins, -1 if hand B wins, 0 for a split pot. Every case is
checked against BOTH the C evaluator (`./equity --cmp`) and the Python evaluator (`hand_evaluator.py`), so a
disagreement between them or with the hand-derived answer fails the run.

These target the situations random sampling reaches only rarely (cross_check.py draws random showdowns;
quads, double trips and 3-pair hands are each a small fraction of them): competing kickers on four of a
kind, two sets, three pairs, six suited cards, wheels, board plays and ties.

Run from anywhere: python sim/edge_cases.py ./equity"""
import os, subprocess, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from hand_evaluator import evaluate_best_of
from poker_types import parse_cards

exe = sys.argv[1] if len(sys.argv) > 1 else "./equity"
RK, SU = "23456789TJQKA", "cdhs"
code = lambda c: RK.index(c[0]) * 4 + SU.index(c[1])

CASES = [
    # (description, board, hole A, hole B, expected)
    ("two sets: the higher set is the trips of the full house",
     "Qc Qd Qh 2s 3s", "Kc Kd Kh", "Ac Ad Ah", -1),
    ("full house: a second set supplies the pair part (QQQ+JJJ beats QQQ+99)",
     "Qc Qd Qh 2s 3s", "Jc Jd Jh", "9c 9d 4h", 1),
    ("full house: trips + second trips + a low pair: the second trips outranks the pair (QQQ+JJ beats QQQ+99)",
     "Qc Qd Qh 2s 2d", "Jc Jd Jh", "9c 9d 4h", 1),
    ("full house: a higher hole pair beats a lower second set (QQQ+KK beats QQQ+JJJ)",
     "Qc Qd Qh 2s 3s", "Jc Jd Jh", "Kc Kd 4h", -1),
    ("full house: the pair is the better of two board pairs, not the first",
     "Kc Kd 5h 5s 2c", "Kh 3c 3d", "Ks 9c 9d", -1),
    ("full house: the trips rank decides before the pair does",
     "Kc Kd 5h 5s 2c", "Kh 3c 3d", "Qc Qd Qh", 1),
    ("three pairs: the best two pairs play",
     "Kc Kd 9h 9s 4c", "Qc Qd 2h", "Jc Jd 3d", 1),
    ("three pairs: the third pair's rank is the kicker, so a hole ace beats it",
     "Kc Kd 9h 9s 4c", "Qc Qd 2h", "Qh Qs Ah", -1),
    ("quads on the board: the higher kicker wins",
     "Jc Jd Jh Js 3c", "Ac 2d 2h", "Kc Kd 4h", 1),
    ("quads on the board, 7 cards: higher kicker wins",
     "Jc Jd Jh Js 3c", "Ac 2d", "Kc Kd", 1),
    ("quads on the board: a second quad supplies only one kicker (3 vs 4)",
     "Jc Jd Jh Js 3c", "3d 3h 3s", "2c 2d 4h", -1),
    ("two quads in one hand: higher quads win",
     "9c 9d 9h Ks Kd", "9s 2c 3d", "Kc Kh 4d", -1),
    ("trips: second kicker decides when the first is equal",
     "Qc Qd 7h 3s 2c", "Qh Ac 9d", "Qs Kc 9h", 1),
    ("two pair: kicker decides",
     "Jc Jd 4h 4s 9c", "Kc 2d 3d", "Qh 2h 3h", 1),
    ("pair: second kicker decides when the first is equal",
     "8s 8d 6c 2h 9c", "Ah Qc 3d", "Ad Jc 3h", 1),
    ("pair: third kicker decides when the first two are equal",
     "8s 8d 6c 2h 4c", "Ah Qc 9d", "Ad Qd 7h", 1),
    ("high card: only the fifth card differs",
     "Ac Kd 9h 4s 2c", "Qh 8d 3s", "Qd 7c 3h", 1),
    ("flush: six suited cards, only the top five count",
     "Qs 9s 7s 2d 2h", "As Ks 3s", "Js Ts 4d", 1),
    ("flush on the board: both play it, split pot",
     "As Ks Qs Js 9s", "2c 3d 4h", "5c 6d 7h", 0),
    ("flush on the board: a hole card that completes a royal wins",
     "As Ks Qs Js 9s", "Ts 2c 3d", "5c 6d 7h", 1),
    ("wheel loses to a six-high straight",
     "3c 4d 5h Kc Kd", "Ah 2c 9s", "6d 2d 8s", -1),
    ("wheel straight flush beats four of a kind",
     "4s 5s Kh 9d 9c", "As 2s 3s", "9h 9s Kd", 1),
    ("ace-high straight beats a lower straight in the same 8 cards",
     "Qs Jd Tc 2h 2d", "Ac Kd 9h", "9c 8d 7h", 1),
    ("straight on the board: both play it, split pot",
     "As Kd Qh Jc Td", "2c 3d 4h", "5c 6d 7h", 0),
]

lines, expected, bad = [], [], 0
for desc, board, a, b, exp in CASES:
    A, B = a.split() + board.split(), b.split() + board.split()
    assert len(set(A + B)) == len(A) + len(B) - len(board.split()), f"duplicate card in case: {desc}"
    py_a, py_b = evaluate_best_of(parse_cards(" ".join(A))), evaluate_best_of(parse_cards(" ".join(B)))
    py = (py_a > py_b) - (py_a < py_b)
    lines.append(f"{len(A)} " + " ".join(str(code(c)) for c in A + B))
    expected.append((exp, py, desc))
out = subprocess.run([exe, "--cmp"], input="\n".join(lines) + "\n", capture_output=True, text=True, check=True).stdout.split()
for (exp, py, desc), c_out in zip(expected, map(int, out)):
    ok = exp == py == c_out
    bad += not ok
    if not ok:
        print(f"FAIL: {desc}\n      expected {exp:+d}, python {py:+d}, C {c_out:+d}")
print(f"{len(CASES)} edge cases checked, {bad} failures")
sys.exit(1 if bad else 0)
