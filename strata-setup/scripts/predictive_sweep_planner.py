#!/usr/bin/env python3
"""Generate a predictive self-healing sweep plan around the verified winner.

Uses anomaly forecasts to decide between stabilizing (conservative) and
expanding configurations, ranks candidates using historical sweep results,
and emits an actionable plan.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from sweep_plan import DEFAULT_BASE, generate_combinations, make_tag  # noqa: E402
from anomaly_prediction import detect_predicted_regression  # noqa: E402

SUMMARY_DEFAULT = ROOT / "runs" / "sweep-summary.jsonl"
HISTORY_DEFAULT = ROOT / "runs" / "regression-alert-history.jsonl"

STABILIZE_KNOBS = {
    "SPEC": ["4"],
    "EXPERT_CACHE": ["8192"],
    "PIPELINE_WINDOWS": ["2"],
    "PEER_PREFILL_ROWS": ["4"],
    "POOL_WORKERS": ["12", "16"],
    "KV": ["int8"],
}

EXPAND_KNOBS = {
    "SPEC": ["3", "4", "5"],
    "EXPERT_CACHE": ["4096", "8192", "16384"],
    "PIPELINE_WINDOWS": ["1", "2", "4"],
    "PEER_PREFILL_ROWS": ["2", "4", "6"],
    "POOL_WORKERS": ["12", "16", "20"],
    "KV": ["int8"],
}


def load_history(path):
    records = []
    p = Path(path)
    if not p.exists():
        return records
    for line in p.read_text().splitlines():
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return records


def load_summary_scores(path):
    scores = {}
    p = Path(path)
    if not p.exists():
        return scores
    for line in p.read_text().splitlines():
        if not line.strip():
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        tag = e.get("tag")
        if not tag:
            continue
        if not e.get("coherence_pass", False):
            scores[tag] = -1.0
            continue
        dec = float(e.get("decode_median", 0) or 0)
        pre = float(e.get("prefill_median", 0) or 0)
        scores[tag] = dec * pre
    return scores


def distance_from_winner(env, winner):
    dist = 0
    for k in ("SPEC", "EXPERT_CACHE", "PIPELINE_WINDOWS", "PEER_PREFILL_ROWS", "POOL_WORKERS"):
        try:
            dist += abs(float(env.get(k, 0)) - float(winner.get(k, 0)))
        except (TypeError, ValueError):
            pass
    return dist


def build_plan(winner_env, history_path=None, summary_path=None,
               baseline_decode=11.9, baseline_prefill=22.9, max_candidates=10):
    history = load_history(history_path or HISTORY_DEFAULT)
    prediction = detect_predicted_regression(history, baseline_decode, baseline_prefill)
    knobs = STABILIZE_KNOBS if prediction["predicted_regression"] else EXPAND_KNOBS
    mode = "stabilize" if prediction["predicted_regression"] else "expand"

    candidates = generate_combinations(winner_env, knobs)
    summary_scores = load_summary_scores(summary_path or SUMMARY_DEFAULT)

    ranked = []
    for c in candidates:
        tag = c["tag"]
        env = c["env"]
        score = summary_scores.get(tag, None)
        dist = distance_from_winner(env, winner_env)
        if score is not None:
            rank = score
            source = "historical"
        else:
            rank = -dist
            source = "distance"
        ranked.append({**c, "score": rank, "source": source, "distance": dist})

    # Always include a winner revalidation candidate first.
    winner_tag = make_tag(winner_env)
    ranked.sort(key=lambda x: (x["tag"] != winner_tag, -x["score"], x["distance"]))

    return {
        "mode": mode,
        "prediction": prediction,
        "winner_tag": winner_tag,
        "candidates": ranked[:max_candidates],
        "total_candidates": len(ranked),
    }


def main():
    ap = argparse.ArgumentParser(description="Generate a predictive self-healing sweep plan")
    ap.add_argument("--history", default=str(HISTORY_DEFAULT))
    ap.add_argument("--summary", default=str(SUMMARY_DEFAULT))
    ap.add_argument("--output", default=None)
    ap.add_argument("--max", type=int, default=10)
    args = ap.parse_args()

    plan = build_plan(DEFAULT_BASE, history_path=args.history,
                      summary_path=args.summary, max_candidates=args.max)
    text = json.dumps(plan, indent=2)
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
