#!/usr/bin/env python3
"""
Automated benchmark runner for strata-old 2x B580 TP2.

Runs a standardized benchmark suite, compares against stored baselines,
and fails on significant regression. Designed for CI integration.

Usage:
  python3 scripts/bench-automation.py --run              # Run benchmarks
  python3 scripts/bench-automation.py --baseline         # Set current as baseline
  python3 scripts/bench-automation.py --compare          # Compare against baseline
  python3 scripts/bench-automation.py --report           # Generate report
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = ROOT / "runs"
BASELINE_FILE = RUNS_DIR / "baseline-2xb580.json"
RESULTS_FILE = RUNS_DIR / "bench-results.json"

# Benchmark configuration - use shorter, more realistic prompts
BENCHMARKS = [
    {
        "name": "short_chat",
        "prompt": "What is the capital of France?",
        "max_tokens": 50,
        "description": "Short chat latency",
    },
    {
        "name": "code_gen",
        "prompt": "Write a Python function to compute fibonacci numbers.",
        "max_tokens": 200,
        "description": "Code generation throughput",
    },
    {
        "name": "explanation",
        "prompt": "Explain how a hash map works in 3 sentences.",
        "max_tokens": 150,
        "description": "Medium explanation throughput",
    },
    {
        "name": "creative",
        "prompt": "Write a short poem about computers.",
        "max_tokens": 100,
        "description": "Creative writing throughput",
    },
]


import subprocess


import tempfile, os


def ask_with_retry(url: str, prompt: str, max_tokens: int, timeout: float = 120, retries: int = 3) -> dict[str, Any] | None:
    """Make a request with retry logic via curl (Python socket handling is unreliable here)."""
    url = url.replace("://localhost:", "://127.0.0.1:").replace("://localhost/", "://127.0.0.1/")
    payload = {"model": "swift", "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens}
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w") as f:
        json.dump(payload, f)
        f.flush()
        os.fsync(f.fileno())
    time.sleep(0.5)

    result_data = None
    for attempt in range(retries):
        try:
            result = subprocess.run(
                ["curl", "-sS", "-X", "POST", url,
                 "-H", "Content-Type: application/json",
                 "-d", f"@{path}"],
                capture_output=True, text=True, timeout=timeout,
            )
            if result.returncode == 0:
                result_data = json.loads(result.stdout)
                break
            if attempt == retries - 1:
                result_data = {"error": result.stderr.strip() or "curl failed"}
        except Exception as e:
            if attempt == retries - 1:
                result_data = {"error": str(e)}
        time.sleep(2 ** attempt)

    try:
        os.unlink(path)
    except OSError:
        pass
    return result_data


def run_benchmark(url: str, prompt: str, max_tokens: int, runs: int = 3) -> dict[str, Any]:
    """Run a single benchmark multiple times and return statistics."""
    latencies = []
    token_counts = []
    throughputs = []

    for i in range(runs):
        start = time.perf_counter()
        body = ask_with_retry(url, prompt, max_tokens)
        elapsed = time.perf_counter() - start

        if not body or "error" in body:
            return {"error": body.get("error", "unknown error") if body else "no response"}

        content = body["choices"][0]["message"].get("content", "") or ""
        usage = body.get("usage") or {}
        tokens = int(usage.get("completion_tokens") or len(content.split()))
        latencies.append(elapsed)
        token_counts.append(tokens)
        throughputs.append(tokens / elapsed if elapsed > 0 else 0)

        # Small delay between runs to avoid overwhelming the server
        if i < runs - 1:
            time.sleep(1)

    return {
        "latency_mean": statistics.mean(latencies),
        "latency_median": statistics.median(latencies),
        "latency_stdev": statistics.stdev(latencies) if len(latencies) > 1 else 0,
        "tokens_mean": statistics.mean(token_counts),
        "throughput_mean": statistics.mean(throughputs),
        "throughput_median": statistics.median(throughputs),
        "runs": runs,
    }


def run_all_benchmarks(url: str = "http://127.0.0.1:1235/v1/chat/completions") -> dict[str, Any]:
    """Run all benchmarks and return combined results."""
    results = {"timestamp": time.time(), "url": url, "benchmarks": {}}
    for bm in BENCHMARKS:
        print(f"Running {bm['name']} ({bm['description']})...", flush=True)
        results["benchmarks"][bm["name"]] = {
            "description": bm["description"],
            "results": run_benchmark(url, bm["prompt"], bm["max_tokens"]),
        }
    return results


def save_results(results: dict[str, Any], path: Path) -> None:
    RUNS_DIR.mkdir(exist_ok=True)
    path.write_text(json.dumps(results, indent=2))


def load_results(path: Path) -> dict[str, Any] | None:
    if path.exists():
        return json.loads(path.read_text())
    return None


def compare_with_baseline(current: dict, baseline: dict, threshold: float = 0.15) -> tuple[bool, list[str]]:
    """Compare current results with baseline. Returns (passed, messages)."""
    messages = []
    passed = True
    for name, bm_data in current.get("benchmarks", {}).items():
        if name not in baseline.get("benchmarks", {}):
            messages.append(f"  {name}: no baseline")
            continue
        cur_tput = bm_data["results"].get("throughput_median", 0)
        base_tput = baseline["benchmarks"][name]["results"].get("throughput_median", 0)
        if base_tput == 0:
            messages.append(f"  {name}: baseline throughput zero")
            continue
        ratio = cur_tput / base_tput
        status = "PASS" if ratio >= (1 - threshold) else "REGRESSION"
        if ratio < (1 - threshold):
            passed = False
        messages.append(f"  {name}: {status} (current={cur_tput:.1f} tok/s, baseline={base_tput:.1f} tok/s, ratio={ratio:.2f})")
    return passed, messages


def main():
    ap = argparse.ArgumentParser(description="Strata-old 2x B580 benchmark automation")
    ap.add_argument("--run", action="store_true", help="Run benchmarks and save results")
    ap.add_argument("--baseline", action="store_true", help="Set current results as baseline")
    ap.add_argument("--compare", action="store_true", help="Compare latest results with baseline")
    ap.add_argument("--report", action="store_true", help="Generate human-readable report")
    ap.add_argument("--url", default="http://127.0.0.1:1235/v1/chat/completions")
    ap.add_argument("--threshold", type=float, default=0.15, help="Regression threshold (fraction)")
    args = ap.parse_args()

    if args.run:
        results = run_all_benchmarks(args.url)
        save_results(results, RESULTS_FILE)
        print(f"Results saved to {RESULTS_FILE}")

    if args.baseline:
        results = load_results(RESULTS_FILE)
        if results:
            save_results(results, BASELINE_FILE)
            print(f"Baseline saved to {BASELINE_FILE}")
        else:
            print("No results to set as baseline. Run --run first.")
            sys.exit(1)

    if args.compare:
        current = load_results(RESULTS_FILE)
        baseline = load_results(BASELINE_FILE)
        if not current:
            print("No current results. Run --run first.")
            sys.exit(1)
        if not baseline:
            print("No baseline. Run --baseline first.")
            sys.exit(1)
        passed, messages = compare_with_baseline(current, baseline, args.threshold)
        for m in messages:
            print(m)
        if not passed:
            print(f"\nREGRESSION DETECTED (threshold={args.threshold*100:.0f}%)")
            sys.exit(1)
        print("\nAll benchmarks within threshold.")

    if args.report:
        current = load_results(RESULTS_FILE)
        baseline = load_results(BASELINE_FILE)
        if not current:
            print("No results to report.")
            sys.exit(1)
        print("=" * 60)
        print("STRATA-OLD 2x B580 BENCHMARK REPORT")
        print("=" * 60)
        for name, bm_data in current.get("benchmarks", {}).items():
            r = bm_data["results"]
            print(f"\n{bm_data['description']} ({name})")
            if "error" in r:
                print(f"  ERROR: {r['error']}")
                continue
            print(f"  Throughput: {r['throughput_median']:.1f} tok/s (median of {r['runs']} runs)")
            print(f"  Latency:    {r['latency_median']*1000:.0f} ms (median)")
            if baseline and name in baseline.get("benchmarks", {}):
                base_tput = baseline["benchmarks"][name]["results"].get("throughput_median", 0)
                if base_tput > 0:
                    ratio = r['throughput_median'] / base_tput
                    print(f"  vs Baseline: {ratio:.2f}x ({'OK' if ratio >= 0.85 else 'REGRESSION'})")

    if not any([args.run, args.baseline, args.compare, args.report]):
        ap.print_help()


if __name__ == "__main__":
    main()
