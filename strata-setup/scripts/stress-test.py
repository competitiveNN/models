#!/usr/bin/env python3
"""Stress test a running Strata server with concurrent requests.

Sends N concurrent chat completion requests and reports success/failure rates,
latency percentiles, and throughput. Useful for catching race conditions,
deadlocks, and memory issues under load.

Usage:
    python3 scripts/stress-test.py --url http://127.0.0.1:1235 --clients 4 --requests 20
"""
from __future__ import annotations
import argparse, json, time, urllib.request, threading, statistics
from concurrent.futures import ThreadPoolExecutor, as_completed

PROMPT = "Write a short paragraph about a topic of your choice."

def send_request(url, max_tokens=64):
    body = json.dumps({"messages": [{"role": "user", "content": PROMPT}], "max_tokens": max_tokens, "stream": False}).encode()
    req = urllib.request.Request(url + "/v1/chat/completions", data=body, headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.loads(r.read())
            t1 = time.time()
            choice = (data.get("choices") or [{}])[0]
            msg = choice.get("message", {})
            content = msg.get("content", "") or msg.get("reasoning_content", "")
            from coherence import is_degenerate_response
            degenerate = is_degenerate_response(msg)
            return {
                "ok": True,
                "latency": round(t1 - t0, 2),
                "tokens": data.get("usage", {}).get("completion_tokens", 0),
                "degenerate": degenerate,
                "finish_reason": choice.get("finish_reason"),
            }
    except Exception as e:
        return {"ok": False, "latency": round(time.time() - t0, 2), "error": str(e)}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:1235")
    ap.add_argument("--clients", type=int, default=4)
    ap.add_argument("--requests", type=int, default=20)
    ap.add_argument("--max-tokens", type=int, default=64)
    args = ap.parse_args()

    print(f"Stress test: {args.requests} requests, {args.clients} concurrent, max_tokens={args.max_tokens}")
    print(f"Target: {args.url}")
    print()

    results = []
    t_start = time.time()
    with ThreadPoolExecutor(max_workers=args.clients) as pool:
        futures = [pool.submit(send_request, args.url, args.max_tokens) for _ in range(args.requests)]
        for i, f in enumerate(as_completed(futures), 1):
            r = f.result()
            results.append(r)
            status = "OK" if r["ok"] else "FAIL"
            extra = ""
            if r.get("degenerate"):
                extra = " [DEGENERATE]"
            if not r["ok"]:
                extra = f" [{r.get('error', '')[:60]}]"
            print(f"  [{i:3d}/{args.requests}] {status} latency={r['latency']:.2f}s tokens={r.get('tokens',0)}{extra}")

    total_time = time.time() - t_start
    ok = [r for r in results if r["ok"]]
    fail = [r for r in results if not r["ok"]]
    degenerate = [r for r in ok if r.get("degenerate")]

    print()
    print("=== Summary ===")
    print(f"Total time: {total_time:.1f}s")
    print(f"Requests: {len(results)} (ok={len(ok)}, fail={len(fail)}, degenerate={len(degenerate)})")
    if ok:
        latencies = [r["latency"] for r in ok]
        print(f"Latency: p50={statistics.median(latencies):.2f}s p95={sorted(latencies)[int(len(latencies)*0.95)]:.2f}s min={min(latencies):.2f}s max={max(latencies):.2f}s")
        total_tokens = sum(r.get("tokens", 0) for r in ok)
        print(f"Throughput: {total_tokens/total_time:.1f} tok/s aggregate, {len(ok)/total_time:.2f} req/s")
    if fail:
        print(f"Failures: {set(r.get('error','')[:80] for r in fail)}")
    if degenerate:
        print(f"WARNING: {len(degenerate)} responses were degenerate (repeated tokens)")

if __name__ == "__main__":
    main()
