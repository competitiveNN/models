#!/usr/bin/env python3
"""Benchmark battery for a running Strata server, with regression gating.

Superset of battery_cfg.py, which only fired one prompt shape at the server and
printed a median. Three gaps this closes:

  1. One prompt shape measures neither prefill nor long-context decode, and
     those are exactly the two regimes where this rig has hit limits. We fire a
     matrix: short decode, long-prefill (prefill-dominated), long decode.
  2. Results went to stdout only, so nothing could be compared later. We write
     a JSON record with provenance next to the other bench artefacts.
  3. A run could not fail. `--compare <baseline.json>` turns the battery into a
     gate: exit 2 if decode or prefill regresses past --tolerance.

Usage:
  scripts/bench-battery.py --base-url http://127.0.0.1:8081 \
      --model swift-1.5-iq3_xxs --out bench/runs/battery-1gpu.json
  scripts/bench-battery.py ... --compare bench/runs/battery-1gpu.json

Exit codes: 0 ok, 1 server/benchmark error, 2 regression vs baseline.
"""
import argparse
import json
import os
import platform
import statistics
import sys
import time
import urllib.error
import urllib.request

# Prompt shapes chosen so each regime dominates the measurement:
#   decode  -> tiny prompt, many tokens: wall time is ~all decode
#   prefill -> huge prompt, few tokens: wall time is ~all prefill
#   mixed   -> moderate both, the everyday case
DEFAULT_SUITE = [
    {"name": "decode_short", "max_tokens": 128,
     "prompt": "Write one paragraph about the ocean."},
    {"name": "decode_long", "max_tokens": 512,
     "prompt": "Write a detailed technical explanation of transformer attention."},
    {"name": "prefill_long", "max_tokens": 32,
     "prompt": "Summarize the following notes in one sentence.\n\n" +
               ("The maintenance robot logged a fault on the coolant loop. " * 220)},
]


def post_json(url, payload, timeout):
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.load(r)
    return time.time() - t0, data


def get_json(url, timeout=5):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.load(r)


def wait_ready(base, timeout_s):
    """The engine is only ready when health reports loaded, not when it accepts
    TCP: the first start reads tens of GB of experts."""
    t0 = time.time()
    last_err = None
    while time.time() - t0 < timeout_s:
        try:
            h = get_json(f"{base}/health")
            if h.get("loaded"):
                return time.time() - t0
        except Exception as e:  # server still coming up
            last_err = e
        time.sleep(2)
    raise RuntimeError(f"server not loaded within {timeout_s}s (last error: {last_err})")


def run_case(base, model, case, timeout):
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": case["prompt"]}],
        "max_tokens": case["max_tokens"],
        "stream": False,
        "temperature": 0,
    }
    wall, resp = post_json(f"{base}/v1/chat/completions", payload, timeout)
    usage = resp.get("usage", {})
    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)
    if completion_tokens <= 0:
        raise RuntimeError(f"{case['name']}: no tokens generated ({resp.get('choices')})")
    return {
        "name": case["name"],
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "wall_s": round(wall, 3),
        # Wall-clock end-to-end throughput. This is the honest number: it
        # includes prefill, so it is lower than engine-reported decode tok/s.
        "e2e_tok_s": round(completion_tokens / wall, 2),
        "max_tokens": case["max_tokens"],
    }


def summarize(cases):
    """Separate the regimes: prefill-dominated cases bound prefill, the rest
    bound decode."""
    pf = [c for c in cases if c["name"].startswith("prefill")]
    dec = [c for c in cases if not c["name"].startswith("prefill")]
    out = {}
    if dec:
        out["decode_e2e_tok_s_median"] = round(
            statistics.median(c["e2e_tok_s"] for c in dec), 2)
    if pf:
        # prefill tok/s = prompt tokens processed per second of wall time
        out["prefill_tok_s_median"] = round(statistics.median(
            c["prompt_tokens"] / c["wall_s"] for c in pf), 1)
    return out


def compare(current, baseline, tolerance_pct):
    """Return list of regression strings. A lower median than baseline by more
    than tolerance is a regression."""
    problems = []
    for key, label in (("decode_e2e_tok_s_median", "decode"),
                       ("prefill_tok_s_median", "prefill")):
        cur = current.get(key)
        old = (baseline.get("summary") or {}).get(key)
        if cur is None or old is None:
            continue
        floor = old * (1.0 - tolerance_pct / 100.0)
        if cur < floor:
            problems.append(
                f"{label} regressed: {cur} < {floor:.2f} "
                f"(baseline {old}, tolerance {tolerance_pct}%)")
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8081")
    ap.add_argument("--model", required=True)
    ap.add_argument("--out", required=True, help="where to write the JSON record")
    ap.add_argument("--compare", help="baseline JSON to gate against")
    ap.add_argument("--tolerance", type=float, default=10.0,
                    help="allowed percent drop before it counts as a regression")
    ap.add_argument("--ready-timeout", type=int, default=600)
    ap.add_argument("--request-timeout", type=int, default=1800)
    ap.add_argument("--tag", default="", help="free-form label for this run")
    args = ap.parse_args()

    base = args.base_url.rstrip("/")
    try:
        ready_s = wait_ready(base, args.ready_timeout)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    cases = []
    for case in DEFAULT_SUITE:
        try:
            c = run_case(base, args.model, case, args.request_timeout)
        except Exception as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1
        cases.append(c)
        print(f"  {c['name']:14} prompt={c['prompt_tokens']:5} "
              f"gen={c['completion_tokens']:4} wall={c['wall_s']:7.2f}s "
              f"e2e={c['e2e_tok_s']:7.2f} tok/s")

    summary = summarize(cases)
    record = {
        "tag": args.tag,
        "base_url": base,
        "model": args.model,
        "started_ready_after_s": round(ready_s, 1),
        "host": platform.node(),
        "cpu": platform.machine(),
        "cases": cases,
        "summary": summary,
    }

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(record, f, indent=2)
        f.write("\n")

    print("  summary:", json.dumps(summary))
    print(f"  wrote {args.out}")

    if args.compare:
        try:
            baseline = json.load(open(args.compare))
        except Exception as e:
            print(f"ERROR: cannot read baseline {args.compare}: {e}", file=sys.stderr)
            return 1
        problems = compare(summary, baseline, args.tolerance)
        if problems:
            for p in problems:
                print(f"  REGRESSION: {p}", file=sys.stderr)
            return 2
        print(f"  vs baseline {args.compare}: no regression "
              f"(tolerance {args.tolerance}%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
