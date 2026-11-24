#!/usr/bin/env python3
"""Verify that run-strata-2gpu.sh defaults match the recorded sweep winner.

Winner-selection criterion (applied to all coherence-passing entries):
  1. coherence_pass == True
  2. decode_median > baseline decode  (strictly beats baseline on decode)
  3. prefill_median > baseline prefill (strictly beats baseline on prefill)
  Among qualifying entries, the winner maximises decode_median * prefill_median
  (combined throughput product).  Ties broken by higher prefill_median.

With --variance-aware, warm-repeat medians (from runs/warm-*.json) are used
when available, falling back to sweep medians.

Winner tag: r3-spec4-ec8192-pw2-ppr4-pool20-int8
Expected defaults: SPEC=4, EXPERT_CACHE=8192, PEER_PREFILL_ROWS=4, POOL_WORKERS=20
"""
import argparse
import json
import math
import re
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "run-strata-2gpu.sh"
SUMMARY = ROOT / "runs" / "sweep-summary.jsonl"
WINNER_TAG = "r3-spec4-ec8192-pw2-ppr4-pool20-int8"
BASELINE_TAG = "baseline-ctx64k-auto-spec4-par1"

SHELL_VARS = ["SPEC", "EXPERT_CACHE", "PEER_PREFILL_ROWS", "POOL_WORKERS"]
ENV_KEYS = {
    "SPEC": "SPEC",
    "EXPERT_CACHE": "EXPERT_CACHE",
    "PEER_PREFILL_ROWS": "PEER_PREFILL_ROWS",
    "POOL_WORKERS": "POOL_WORKERS",
}


def parse_shell_defaults(script_text):
    """Extract default values from VAR=\"${VAR:-default}\" patterns."""
    defaults = {}
    for var in SHELL_VARS:
        pattern = var + r'="\${' + var + r':-([^}]+)}"'
        m = re.search(pattern, script_text)
        if not m:
            pattern2 = var + r'=\$\{[^}]*:-([^}]+)\}'
            m = re.search(pattern2, script_text)
        if m:
            defaults[var] = m.group(1).strip().strip('"')
        else:
            defaults[var] = None
    return defaults


def load_entries():
    """Load all entries from sweep-summary.jsonl."""
    entries = []
    if not SUMMARY.exists():
        return entries
    for line in SUMMARY.read_text().splitlines():
        if not line.strip():
            continue
        entries.append(json.loads(line))
    return entries


def find_entry(tag):
    for e in load_entries():
        if e.get("tag") == tag:
            return e
    return None


def find_baseline():
    return find_entry(BASELINE_TAG)


def load_warm_repeats():
    """Load warm-repeat JSON files from runs/. Return dict tag->data.

    Also maps warm files to winner tag by env match (warm files may use different tags).
    """
    warm = {}
    runs_dir = ROOT / "runs"
    if not runs_dir.exists():
        return warm
    for p in runs_dir.glob("warm-*.json"):
        try:
            data = json.loads(p.read_text())
            tag = data.get("tag")
            if tag:
                warm[tag] = data
        except (json.JSONDecodeError, OSError):
            continue
    # Map warm files to winner tag by env match (warm files may use different tags).
    # Guard: if multiple warm files match, prefer the one with the most runs;
    # warn if ambiguous.
    winner_entry = find_entry(WINNER_TAG)
    if winner_entry:
        winner_env = winner_entry.get("env", {})
        match_keys = ["SPEC", "EXPERT_CACHE", "PEER_PREFILL_ROWS", "POOL_WORKERS"]
        matching = []
        for tag, data in warm.items():
            wenv = data.get("env", {})
            if all(str(wenv.get(k)) == str(winner_env.get(k)) for k in match_keys):
                matching.append((tag, data))
        if len(matching) > 1:
            # Prefer the warm file with the most runs; warn about ambiguity
            matching.sort(key=lambda x: len(x[1].get("per_run", [])), reverse=True)
            import sys as _sys
            print(f"WARNING: {len(matching)} warm files match winner env; "
                  f"using '{matching[0][0]}' (most runs).", file=_sys.stderr)
        if matching:
            warm[WINNER_TAG] = matching[0][1]
    return warm


def warm_median(tag, warm_data):
    """Return warm-repeat median decode/prefill for a tag, or None."""
    d = warm_data.get(tag)
    if d is None:
        return None
    decodes = [r["decode"] for r in d.get("per_run", []) if r.get("decode", 0) > 0]
    prefills = [r["prefill"] for r in d.get("per_run", []) if r.get("prefill", 0) > 0]
    if not decodes or not prefills:
        return None
    return {
        "decode_median": statistics.median(decodes),
        "prefill_median": statistics.median(prefills),
        "decode_stdev": statistics.stdev(decodes) if len(decodes) > 1 else 0.0,
        "prefill_stdev": statistics.stdev(prefills) if len(prefills) > 1 else 0.0,
        "n": len(decodes),
    }


def compute_optimal_winner(variance_aware=False, warm_data=None):
    """Return the entry of the optimal winner under the defined criterion."""
    entries = load_entries()
    baseline = find_entry(BASELINE_TAG)
    if baseline is None:
        return None
    base_decode = baseline["decode_median"]
    base_prefill = baseline["prefill_median"]

    candidates = []
    for e in entries:
        if not e.get("coherence_pass", False):
            continue
        if variance_aware and warm_data:
            wm = warm_median(e.get("tag"), warm_data)
            if wm is not None:
                dec = wm["decode_median"]
                pre = wm["prefill_median"]
            else:
                dec = e["decode_median"]
                pre = e["prefill_median"]
        else:
            dec = e["decode_median"]
            pre = e["prefill_median"]

        if dec <= base_decode:
            continue
        if pre <= base_prefill:
            continue
        score = dec * pre
        candidates.append((score, pre, e.get("tag"), e, dec, pre))

    if not candidates:
        return None
    candidates.sort(key=lambda c: (c[0], c[1]), reverse=True)
    return candidates[0][3]


def verify_winner_optimal(variance_aware=False, warm_data=None):
    """Verify WINNER_TAG is the optimal winner. Return (ok, message)."""
    optimal = compute_optimal_winner(variance_aware=variance_aware, warm_data=warm_data)
    if optimal is None:
        return False, "No entry strictly beats baseline on both metrics."
    if optimal["tag"] != WINNER_TAG:
        return False, (
            f"Optimal winner is '{optimal['tag']}' "
            f"(decode={optimal['decode_median']}, prefill={optimal['prefill_median']}, "
            f"score={optimal['decode_median']*optimal['prefill_median']:.1f}), "
            f"not '{WINNER_TAG}'."
        )
    msg = (
        f"Winner '{WINNER_TAG}' is optimal: "
        f"decode={optimal['decode_median']}, prefill={optimal['prefill_median']}, "
        f"score={optimal['decode_median']*optimal['prefill_median']:.1f}."
    )
    if variance_aware and warm_data:
        wm = warm_median(WINNER_TAG, warm_data)
        if wm is not None:
            msg += (
                f" Warm-repeat median: decode={wm['decode_median']:.2f} "
                f"(stdev={wm['decode_stdev']:.2f}, n={wm['n']}), "
                f"prefill={wm['prefill_median']:.2f} (stdev={wm['prefill_stdev']:.2f})."
            )
    return True, msg


def main():
    ap = argparse.ArgumentParser(description="Verify deployed defaults match sweep winner")
    ap.add_argument("--variance-aware", action="store_true",
                    help="Use warm-repeat medians for winner selection")
    args = ap.parse_args()

    if not SCRIPT.exists():
        print(f"ERROR: {SCRIPT} not found")
        return 1
    if not SUMMARY.exists():
        print(f"ERROR: {SUMMARY} not found")
        return 1

    script_text = SCRIPT.read_text()
    defaults = parse_shell_defaults(script_text)
    winner = find_entry(WINNER_TAG)

    if winner is None:
        print(f"ERROR: Winner tag '{WINNER_TAG}' not found in {SUMMARY}")
        return 1

    env = winner.get("env", {})
    errors = []

    for var in SHELL_VARS:
        env_key = ENV_KEYS[var]
        shell_val = defaults.get(var)
        winner_val = env.get(env_key)
        if shell_val is None:
            errors.append(f"  {var}: could not parse from run-strata-2gpu.sh")
            continue
        if str(shell_val) != str(winner_val):
            errors.append(
                f"  {var}: shell default '{shell_val}' != winner env '{winner_val}'"
            )

    if errors:
        print("FAILED: Deployed defaults do not match verified winner:")
        for e in errors:
            print(e)
        print(f"\nWinner tag: {WINNER_TAG}")
        print(f"Winner env: {json.dumps(env)}")
        print(f"Shell defaults: {json.dumps(defaults)}")
        return 1

    warm_data = load_warm_repeats() if args.variance_aware else None
    ok, msg = verify_winner_optimal(variance_aware=args.variance_aware, warm_data=warm_data)
    if not ok:
        print(f"FAILED: {msg}")
        return 1

    print("PASSED: Deployed defaults match verified winner.")
    print(f"  Winner: {WINNER_TAG}")
    print(f"  decode={winner['decode_median']:.1f} prefill={winner['prefill_median']:.1f} tok/s")
    print(f"  coherence_pass={winner['coherence_pass']}")
    print(f"  {msg}")
    print(f"  Defaults: SPEC={defaults['SPEC']} EXPERT_CACHE={defaults['EXPERT_CACHE']} "
          f"PEER_PREFILL_ROWS={defaults['PEER_PREFILL_ROWS']} POOL_WORKERS={defaults['POOL_WORKERS']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
