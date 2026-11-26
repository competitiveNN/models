#!/usr/bin/env python3
"""Measure prefill (prompt) and decode (generation) throughput from the
strata 2x B580 server's own `timings` field (prompt_per_second / predicted_per_second).

Usage: python scripts/measure-prefill-decode.py [--url URL] [--runs N] [--json OUT]
"""
import argparse
import json
import sys
import urllib.request

DEFAULT_URL = "http://127.0.0.1:1235/v1/chat/completions"

# (name, prompt, max_tokens) - prompt length grows across rows to exercise prefill.
PROMPTS = [
    ("short", "What is 2+2?", 64),
    ("short2", "Explain gravity in two sentences.", 96),
    ("medium", "Summarise the main ideas of Newton's Principia in a short paragraph.", 160),
    ("code", "Write a Python function that returns the n-th prime number, efficient for large n, with a short explanation.", 220),
    ("long", "Explain how a transformer neural network works, covering self-attention, multi-head attention, positional encoding, and the feed-forward layers, in about six sentences.", 320),
]


def ask(url, prompt, max_tokens, timeout=300):
    payload = {"model": "swift", "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens}
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return json.loads(res.read().decode())


def stats(vals):
    if not vals:
        return {}
    s = sorted(vals)
    return {"min": s[0], "max": s[-1], "mean": sum(vals) / len(vals), "median": s[len(s) // 2]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--runs", type=int, default=2)
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    rows = []
    for name, prompt, mt in PROMPTS:
        samples = []
        for i in range(args.runs):
            try:
                d = ask(args.url, prompt, mt)
            except Exception as e:
                print(f"[{name}] run {i+1} ERROR: {e}", flush=True)
                continue
            t = d.get("timings") or {}
            u = d.get("usage") or {}
            fr = d["choices"][0].get("finish_reason")
            rows.append({
                "case": name, "run": i + 1,
                "prompt_tokens": t.get("prompt_n", u.get("prompt_tokens", 0)),
                "prompt_ms": t.get("prompt_ms"),
                "prompt_per_second": t.get("prompt_per_second"),
                "predicted_n": t.get("predicted_n", u.get("completion_tokens", 0)),
                "predicted_ms": t.get("predicted_ms"),
                "predicted_per_second": t.get("predicted_per_second"),
                "draft_n": t.get("draft_n"),
                "draft_accepted": t.get("draft_n_accepted"),
                "finish_reason": fr,
            })
            print(f"[{name}] pt={t.get('prompt_n')} prefill={t.get('prompt_per_second')}tok/s "
                  f"pred={t.get('predicted_n')} decode={t.get('predicted_per_second')}tok/s "
                  f"draft={t.get('draft_n')}/{t.get('draft_n_accepted')} fin={fr}", flush=True)

    prefill = [r["prompt_per_second"] for r in rows if r.get("prompt_per_second")]
    decode = [r["predicted_per_second"] for r in rows if r.get("predicted_per_second")]
    print("\n=== SUMMARY ===")
    print("prefill tok/s:", stats(prefill))
    print("decode  tok/s:", stats(decode))
    if args.json:
        with open(args.json, "w") as f:
            json.dump({"rows": rows, "prefill": stats(prefill), "decode": stats(decode)}, f, indent=2)
        print("saved ->", args.json)


if __name__ == "__main__":
    main()