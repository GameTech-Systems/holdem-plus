"""Exact odds for the Hold'em Plus third hole card, by full enumeration (standard library only).

The plus card is dealt AFTER the flop, so the chance that it is one of your "outs" depends on how many of
those outs the flop already used:

  * averaged over every possible flop it is exactly  outs / 50  (the third card is a uniformly random one of
    the 50 cards you cannot see before the flop);
  * once you have seen the flop it is  (outs still unseen) / 47.

The strategy guide quotes both. This script enumerates every flop and third card (C(50,3) x 47 = 921,200
combinations per starting hand) and asserts the values quoted there, so a wrong number fails CI.

Run: python sim/third_card_odds.py"""
from fractions import Fraction as F
from itertools import combinations

DECK = [(r, s) for r in range(13) for s in range(4)]          # (rank 0..12, suit 0..3)

def study(hole, is_out):
    """Return (average over all flops, {outs the flop used: P(third card is an out)})."""
    rest = [c for c in DECK if c not in hole]
    hits = total = 0
    by_used = {}
    for flop in combinations(rest, 3):
        left = [c for c in rest if c not in flop]
        n_out = sum(1 for c in left if is_out(c))
        used = sum(1 for c in flop if is_out(c))
        h, t = by_used.get(used, (0, 0))
        by_used[used] = (h + n_out, t + len(left))
        hits += n_out
        total += len(left)
    return F(hits, total), {u: F(h, t) for u, (h, t) in by_used.items()}

def pct(x):
    return f"{float(x):.2%}"

pair = [(5, 0), (5, 1)]                                      # 7c 7d
unpaired = [(12, 2), (11, 1)]                                # Ah Kd
suited = [(7, 2), (6, 2)]                                    # 9h 8h

print("Chance the plus card is one of your outs\n")
rows = {
    "Pocket pair -> third of a kind (2 outs)": study(pair, lambda c: c[0] == 5),
    "Two unpaired cards -> pairs one (6 outs)": study(unpaired, lambda c: c[0] in (12, 11)),
    "Suited -> third of the suit (11 outs)": study(suited, lambda c: c[1] == 2),
}
for name, (avg, by_used) in rows.items():
    print(f"{name}\n  averaged over all flops: {avg} = {pct(avg)}")
    for used in sorted(by_used):
        print(f"  flop already holds {used} of your outs -> {pct(by_used[used])}")

# Values quoted in static/strategy.html -- fail loudly if the guide and the maths ever disagree.
assert rows["Pocket pair -> third of a kind (2 outs)"][0] == F(2, 50)
assert rows["Two unpaired cards -> pairs one (6 outs)"][0] == F(6, 50)
assert rows["Suited -> third of the suit (11 outs)"][0] == F(11, 50)
assert rows["Pocket pair -> third of a kind (2 outs)"][1][0] == F(2, 47)
assert rows["Two unpaired cards -> pairs one (6 outs)"][1][0] == F(6, 47)
for used, outs_left in ((0, 11), (1, 10), (2, 9), (3, 8)):
    assert rows["Suited -> third of the suit (11 outs)"][1][used] == F(outs_left, 47)

# Set-mining: chance a pocket pair is a set or better by the time flop betting opens.
rest = [c for c in DECK if c not in pair]
hits = total = 0
for flop in combinations(rest, 3):
    left = [c for c in rest if c not in flop]
    flopped = any(c[0] == 5 for c in flop)
    total += len(left)
    hits += len(left) if flopped else sum(1 for c in left if c[0] == 5)
plus = F(hits, total)
holdem = 1 - F(48 * 47 * 46, 50 * 49 * 48)
print(f"\nPocket pair is a set or better by flop betting: Hold'em Plus {pct(plus)} (1 in {float(1/plus):.1f}), "
      f"Hold'em {pct(holdem)} (1 in {float(1/holdem):.1f})")
assert round(float(plus), 3) == 0.155 and round(float(holdem), 3) == 0.118
