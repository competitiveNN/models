#!/usr/bin/env python3
"""Derive verified Strata throughput metrics from serve logs.

Every number this prints is parsed from an actual `strata serve:` line, so the
report can never drift from what the engine really did. Use this instead of
hand-copying tok/s figures into status docs.

Two things this deliberately does NOT do naively, because the raw log makes both
easy to get wrong:

1. A log file is often several engine sessions concatenated (the engine restarts
   mid-file, marked by `engine started:`). Requests and failures are attributed
   to the session they occurred in, and sessions that died with zero completed
   requests are reported separately -- they are the real signal of a hard crash.

2. Failures are counted as *events*, not lines. One `DEVICE_LOST` is emitted as
   two lines (backend error + exception site), so counting lines roughly doubles
   the failure count. Adjacent failure lines are merged into one event.

Failure classes are kept apart instead of collapsed into one number:
  - device_lost / oom / err_request are hard failures: the request did not finish.
  - verify_timeout is a *disturbance*: the engine reports the GPU exceeded 5s and
    releases its waits, but the request may still have completed. It is reported
    separately and NOT folded into the success denominator, because treating it
    as either success or failure would be an unverifiable claim.

Line format parsed (one per completed request):
  strata serve: prompt P tokens = R reused + K read in X ms (A tok/s),
                G generated in Z ms (B tok/s), drafts accepted N of M, ...

Usage:
  scripts/summarize-bench.py runs/*.log
  scripts/summarize-bench.py --json runs/*.log
"""
import argparse
import glob
import json
import os
import re
import sys

# Targets we are validating against (see docs/status.md).
TARGET_DECODE_TPS = 40.0
TARGET_PREFILL_TPS = 1400.0

REQ = re.compile(
    r"prompt (\d+) tokens = (\d+) reused \+ (\d+) read in (\d+) ms \(([\d.]+) tok/s\)"
    r".*?(\d+) generated in (\d+) ms \(([\d.]+) tok/s\)"
)
SESSION_START = re.compile(r"engine started:")
# A prefill is only a prefill measurement if new (non-reused) tokens were read.
# Below this the prompt was mostly cache hit and the tok/s reflects cache lookup.
PREFILL_MIN_NEW = 200

FAILURE_CLASSES = [
    ("device_lost", re.compile(r"UR_RESULT_ERROR_DEVICE_LOST")),
    ("oom", re.compile(r"UR_RESULT_ERROR_OUT_OF_DEVICE_MEMORY")),
    ("err_request", re.compile(r"ERR request failed")),
    ("other_ur_error", re.compile(r"UR_RESULT_ERROR_[A-Z_]+")),
]
# Disturbances: evidence something went wrong, but not evidence the request died.
DISTURBANCE_CLASSES = [
    ("verify_timeout", re.compile(r"verify: timed out|did not finish within \d+ s")),
]
HARD_FAILURES = ("device_lost", "oom", "err_request", "other_ur_error")


def median(xs):
    if not xs:
        return None
    xs = sorted(xs)
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2.0


def _events(line_idx, merge_gap=3):
    """Merge line indices closer than `merge_gap` into single events.

    One failure is typically logged on 2-3 consecutive lines (the backend error,
    then the exception site). Counting lines would double-count it.
    """
    if not line_idx:
        return []
    events = [[line_idx[0]]]
    for i in line_idx[1:]:
        if i - events[-1][-1] <= merge_gap:
            events[-1].append(i)
        else:
            events.append([i])
    return events


def parse(path):
    with open(path, "r", errors="replace") as f:
        lines = f.read().splitlines()

    sessions = [{"requests": [], "failures": {}, "disturbances": {}}]
    for i, line in enumerate(lines):
        if SESSION_START.search(line):
            sessions.append({"requests": [], "failures": {}, "disturbances": {}})
            continue
        cur = sessions[-1]
        m = REQ.search(line)
        if m:
            P, R, K, X, ptps, G, Z, gtps = m.groups()
            cur["requests"].append(
                {
                    "prompt_tokens": int(P),
                    "reused_prompt_tokens": int(R),
                    "new_prompt_tokens": int(K),
                    "prompt_ms": int(X),
                    "prompt_tps": float(ptps),
                    "generated": int(G),
                    "gen_ms": int(Z),
                    "gen_tps": float(gtps),
                    "_line": i,
                }
            )
            continue
        for name, pat in FAILURE_CLASSES + DISTURBANCE_CLASSES:
            if pat.search(line):
                bucket = "failures" if name in HARD_FAILURES else "disturbances"
                cur[bucket].setdefault(name, []).append(i)
                break

    # Collapse per-session line indices into event counts.
    for s in sessions:
        s["failure_events"] = {
            k: len(_events(v)) for k, v in s["failures"].items()
        }
        s["disturbance_events"] = {
            k: len(_events(v)) for k, v in s["disturbances"].items()
        }
        del s["failures"], s["disturbances"]
    return sessions


def summarize(path):
    sessions = parse(path)
    reqs = [r for s in sessions for r in s["requests"]]
    gens = [r for r in reqs if r["generated"] > 0]

    hard = {}
    dist = {}
    for s in sessions:
        for k, v in s["failure_events"].items():
            hard[k] = hard.get(k, 0) + v
        for k, v in s["disturbance_events"].items():
            dist[k] = dist.get(k, 0) + v
    hard_total = sum(hard.values())
    dist_total = sum(dist.values())

    # Prefill sample accounting: report what was excluded, not just the median.
    prefills = [r for r in gens if r["new_prompt_tokens"] >= PREFILL_MIN_NEW]
    excluded_low_reuse = [r for r in gens if 0 < r["new_prompt_tokens"] < PREFILL_MIN_NEW]
    full_reuse = [r for r in gens if r["new_prompt_tokens"] == 0]

    g = [r["gen_tps"] for r in gens]
    p = [r["prompt_tps"] for r in prefills]
    longest = max(gens, key=lambda r: r["generated"]) if gens else None
    dead_sessions = [
        s for s in sessions if not s["requests"] and (s["failure_events"] or s["disturbance_events"])
    ]

    attempts = len(gens) + hard_total
    return {
        "log": os.path.basename(path),
        "sessions": len(sessions),
        "sessions_died_without_completing_a_request": len(dead_sessions),
        "requests_generating": len(gens),
        "hard_failures_total": hard_total,
        "hard_failures_by_class": hard,
        "disturbances_by_class": dist,
        "disturbance_note": "engine reported trouble but the request may still have "
                            "completed; excluded from the success rate on purpose",
        "success_rate_pct": round(100.0 * len(gens) / attempts, 1) if attempts else None,
        "decode_tps_median": round(median(g), 1) if g else None,
        "decode_tps_min": round(min(g), 1) if g else None,
        "decode_tps_max": round(max(g), 1) if g else None,
        "prefill_samples": len(prefills),
        "prefill_excluded_low_new_tokens": len(excluded_low_reuse),
        "prefill_excluded_full_reuse": len(full_reuse),
        "prefill_min_new_tokens_threshold": PREFILL_MIN_NEW,
        "prefill_tps_median": round(median(p), 1) if p else None,
        "prefill_tps_max": round(max(p), 1) if p else None,
        "longest_gen": (
            {"tokens": longest["generated"], "ms": longest["gen_ms"], "tps": longest["gen_tps"]}
            if longest else None
        ),
        "meets_decode_target": bool(g) and median(g) >= TARGET_DECODE_TPS,
        "meets_prefill_target": bool(p) and median(p) >= TARGET_PREFILL_TPS,
    }


def expand(patterns):
    out = []
    for pat in patterns:
        hits = glob.glob(pat)
        out.extend(hits if hits else ([pat] if os.path.exists(pat) else []))
    return out


def _fmt(v, width=8, nd=1):
    return f"{'-':>{width}}" if v is None else f"{v:{width}.{nd}f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("logs", nargs="+", help="log globs or paths")
    ap.add_argument("--json", action="store_true", help="emit JSON")
    ap.add_argument("--sort-by", default="decode_tps_median")
    ap.add_argument("--verbose", action="store_true", help="print per-log failure detail")
    args = ap.parse_args()

    paths = [p for p in expand(args.logs) if os.path.isfile(p)]
    if not paths:
        print("no logs matched", file=sys.stderr)
        return 1

    rows = [summarize(p) for p in paths]
    rows = [r for r in rows if r["requests_generating"] or r["hard_failures_total"]]
    # Deterministic order: sort key descending, then log name ascending.
    rows.sort(key=lambda r: (-(r[args.sort_by] or 0), r["log"]))

    if args.json:
        print(json.dumps(rows, indent=2))
        return 0

    hdr = (
        f"{'log':44} {'sess':>4} {'died':>4} {'gen':>5} {'hard':>4} {'ok%':>6} "
        f"{'dec med':>8} {'dec max':>8} {'pf med':>8} {'pf max':>8} {'pf n':>5}"
    )
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        name = r["log"]
        if len(name) > 44:
            name = name[:41] + "..."
        print(
            f"{name:44} {r['sessions']:4} "
            f"{r['sessions_died_without_completing_a_request']:4} "
            f"{r['requests_generating']:5} {r['hard_failures_total']:4} "
            f"{_fmt(r['success_rate_pct'], 6)} {_fmt(r['decode_tps_median'])} "
            f"{_fmt(r['decode_tps_max'])} {_fmt(r['prefill_tps_median'])} "
            f"{_fmt(r['prefill_tps_max'])} {r['prefill_samples']:5}"
        )
    print()
    print(f"targets: decode >= {TARGET_DECODE_TPS} tok/s, prefill >= {TARGET_PREFILL_TPS} tok/s")
    print("sess = engine sessions in file (restarts); died = sessions with 0 completed requests")
    if args.verbose:
        print()
        for r in rows:
            print(f"{r['log']}")
            print(f"   hard failures: {r['hard_failures_by_class'] or '{}'}")
            print(f"   disturbances:  {r['disturbances_by_class'] or '{}'}")
            print(f"   prefill: kept {r['prefill_samples']}, "
                  f"excluded {r['prefill_excluded_low_new_tokens']} low-reuse "
                  f"(<{r['prefill_min_new_tokens_threshold']} new tokens), "
                  f"{r['prefill_excluded_full_reuse']} fully-cached")
    return 0


if __name__ == "__main__":
    sys.exit(main())
