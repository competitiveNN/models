#!/usr/bin/env python3
"""Automated grid search script for Strata 2x B580 tuning.

Round 3: Local neighborhood search around the verified winner
(r3-spec4-ec8192-pw2-ppr4-pool20-int8). Varies one knob at a time
to confirm the winner is a local optimum and not a grid artifact.

Runs scripts/sweep-one.py for each valid combination with warm repeats.
Sequential execution (GPU contention risk on 2x B580 devices).
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SWEEP_SCRIPT = ROOT / "scripts" / "sweep-one.py"
SUMMARY_FILE = ROOT / "runs" / "sweep-summary.jsonl"

# Local neighborhood around winner: SPEC=4, EC=8192, PPR=4, POOL=20, PW=2, KV=int8
# Vary one knob at a time
GRID_COMBOS = [
    # (spec, ec, pw, ppr, pool_workers, kv)
    # Vary EXPERT_CACHE
    ("4", "4096", "2", "4", "16", "int8"),
    ("4", "16384", "2", "4", "16", "int8"),
    # Vary PEER_PREFILL_ROWS
    ("4", "8192", "2", "2", "16", "int8"),
    ("4", "8192", "2", "6", "16", "int8"),
    # Vary POOL_WORKERS
    ("4", "8192", "2", "4", "12", "int8"),
    ("4", "8192", "2", "4", "20", "int8"),
    # Vary PIPELINE_WINDOWS
    ("4", "8192", "1", "4", "16", "int8"),
    ("4", "8192", "4", "4", "16", "int8"),
    # Vary SPEC
    ("3", "8192", "2", "4", "16", "int8"),
    ("5", "8192", "2", "4", "16", "int8"),
]


def run_config(args):
    """Execute a single grid search configuration and return its results dict."""
    tag, spec, ec, pw, ppr, pool, kv, n_runs = args
    cmd = [
        sys.executable, str(SWEEP_SCRIPT),
        "--tag", tag,
        "--runs", str(n_runs),
        "--env", f"SPEC={spec}",
        "--env", f"EXPERT_CACHE={ec}",
        "--env", f"PIPELINE_WINDOWS={pw}",
        "--env", f"PEER_PREFILL_ROWS={ppr}",
        "--env", f"POOL_WORKERS={pool}",
        "--env", f"KV={kv}",
    ]

    print(f"  starting: {tag}", flush=True)
    res = subprocess.run(cmd)
    if res.returncode != 0:
        print(f"  FAILED ({tag}) exit code {res.returncode}", flush=True)
        return {"tag": tag, "failed": True}

    out_json = ROOT / "runs" / f"sweep-{tag}.json"
    if not out_json.exists():
        print(f"  missing output JSON for {tag}", flush=True)
        return {"tag": tag, "failed": True, "reason": "no output json"}

    try:
        result = json.loads(out_json.read_text())
    except json.JSONDecodeError as e:
        print(f"  JSON parse error for {tag}: {e}", flush=True)
        return {"tag": tag, "failed": True, "reason": f"json parse error: {e}"}

    if not result.get("coherence_pass", False):
        print(f"  COHERENCE FAIL for {tag}: skipping", flush=True)
        return {"tag": tag, "failed": True, "reason": "coherence_fail"}

    print(f"  complete: {tag} decode={result['decode_median']:.1f} prefill={result['prefill_median']:.1f}", flush=True)
    return {"tag": tag, "result": result}


def main():
    ap = argparse.ArgumentParser(description="Round 3 neighborhood search for Strata 2x B580 tuning")
    ap.add_argument("--runs", type=int, default=3, help="Warm repeats per config (default 3)")
    ap.add_argument("--limit", type=int, default=None, help="Limit number of configs to run")
    args = ap.parse_args()

    combos = GRID_COMBOS if args.limit is None else GRID_COMBOS[:args.limit]
    total = len(combos)
    print(f"Starting Round 3 neighborhood search over {total} configurations...", flush=True)

    results = []
    for spec, ec, pw, ppr, pool, kv in combos:
        tag = f"r3-spec{spec}-ec{ec}-pw{pw}-ppr{ppr}-pool{pool}-{kv}"
        print(f"\n==========================================\nRunning config: {tag}\n==========================================", flush=True)
        res = run_config((tag, spec, ec, pw, ppr, pool, kv, args.runs))
        results.append(res)

    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_sweep_regression.py"), "--validate-schema"],
        cwd=str(ROOT)
    )

    print("\nRound 3 neighborhood search complete. Summary:", flush=True)
    for r in results:
        if r.get("failed"):
            print(f"  SKIP: {r['tag']} ({r.get('reason', 'failed')})", flush=True)
        else:
            print(f"  OK:   {r['tag']} decode={r['result']['decode_median']:.1f} prefill={r['result']['prefill_median']:.1f}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
