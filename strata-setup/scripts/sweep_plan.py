#!/usr/bin/env python3
"""Generate a deduplicated combinatorial sweep plan for Strata 2x B580 tuning.

Produces a JSON plan of candidate configurations derived from a base config
and per-knob value lists. Useful for expanding sweeps without hand-editing
grid scripts.
"""
import argparse
import itertools
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DEFAULT_BASE = {
    "SPEC": "4",
    "EXPERT_CACHE": "8192",
    "PIPELINE_WINDOWS": "2",
    "PEER_PREFILL_ROWS": "4",
    "POOL_WORKERS": "20",
    "KV": "int8",
}

DEFAULT_KNOBS = {
    "SPEC": ["3", "4", "5"],
    "EXPERT_CACHE": ["4096", "8192", "16384"],
    "PIPELINE_WINDOWS": ["1", "2", "4"],
    "PEER_PREFILL_ROWS": ["2", "4", "6"],
    "POOL_WORKERS": ["12", "16", "20"],
    "KV": ["int8"],
}


def make_tag(env):
    spec = env.get("SPEC", "x")
    ec = env.get("EXPERT_CACHE", "x")
    pw = env.get("PIPELINE_WINDOWS", "x")
    ppr = env.get("PEER_PREFILL_ROWS", "x")
    pool = env.get("POOL_WORKERS", "x")
    kv = env.get("KV", "x")
    return f"r3-spec{spec}-ec{ec}-pw{pw}-ppr{ppr}-pool{pool}-{kv}"


def generate_combinations(base, knobs):
    """Return a list of unique env dicts (with tags) for the cartesian product."""
    keys = list(knobs.keys())
    combos = []
    seen = set()
    for values in itertools.product(*[knobs[k] for k in keys]):
        env = dict(base)
        env.update(dict(zip(keys, values)))
        tag = make_tag(env)
        if tag in seen:
            continue
        seen.add(tag)
        combos.append({"tag": tag, "env": env})
    return combos


def main():
    ap = argparse.ArgumentParser(description="Generate a Strata sweep plan")
    ap.add_argument("--base", default=None, help="Path to JSON base env (optional)")
    ap.add_argument("--knobs", default=None, help="Path to JSON knob value lists (optional)")
    ap.add_argument("--output", default=None, help="Write plan JSON to this path")
    ap.add_argument("--max", type=int, default=None, help="Limit number of candidates")
    args = ap.parse_args()

    base = DEFAULT_BASE
    knobs = DEFAULT_KNOBS
    if args.base:
        base = {**base, **json.loads(Path(args.base).read_text())}
    if args.knobs:
        knobs = json.loads(Path(args.knobs).read_text())

    plan = generate_combinations(base, knobs)
    if args.max is not None:
        plan = plan[:args.max]

    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(plan, indent=2))
    print(json.dumps({"candidates": len(plan)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
