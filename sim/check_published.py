"""Checks that the numbers embedded in static/strategy.html are exactly what the simulator produces.

The strategy guide ships its data as a JavaScript object (`const D=...`). This extracts it and compares every
equity, standard error and three-card shape against a fresh results.json, so the page can never silently drift
from the code that is supposed to be its source. If results.json was produced with a non-default seed or trial
count it cannot match the page by design, so that case is reported and skipped rather than failed.

Run from anywhere: python sim/check_published.py results.json [path/to/strategy.html]"""
import json, os, re, sys

here = os.path.dirname(os.path.abspath(__file__))
results = json.load(open(sys.argv[1]))
page = sys.argv[2] if len(sys.argv) > 2 else os.path.join(here, "..", "static", "strategy.html")
html = open(page, encoding="utf-8").read()
m = re.search(r"const D=(\{.*?\});\s*const R=", html, re.S)
if not m:
    sys.exit("could not find `const D=...;` in the strategy page")
D = json.loads(re.sub(r"([{,])([A-Za-z_]+):", r'\1"\2":', m.group(1)))

if (D["meta"]["seed"], D["meta"]["hu_trials"], D["meta"]["six_trials"]) != \
        (results["meta"]["seed"], results["meta"]["hu_trials"], results["meta"]["six_trials"]):
    print("results.json uses a different seed/trial count than the published page; skipping the comparison")
    sys.exit(0)

diffs = [key for key in results if D.get(key) != results[key]]
for key in diffs:
    print(f"MISMATCH in '{key}': the strategy page does not match this simulation run")
print("strategy page data matches the simulation output exactly" if not diffs else f"{len(diffs)} section(s) differ")
sys.exit(1 if diffs else 0)
