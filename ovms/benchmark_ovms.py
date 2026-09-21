#!/usr/bin/env python3
"""
Streaming benchmark for OpenVINO Model Server (OVMS) / OpenAI-compatible endpoints.
Measures TTFT (time-to-first-token), total latency, throughput, and token count.
Supports multi-run aggregation, CSV output, and JSONL logging.
"""

import time
import json
import csv
import argparse
import sys
import os
import statistics
import io
from typing import Optional, Dict, Any, List

try:
    import requests
except ImportError:
    print("Error: 'requests' is required. Install with: pip install requests", file=sys.stderr)
    sys.exit(1)


DEFAULT_PROMPT = "Explain the theory of relativity in simple terms."
DEFAULT_MAX_TOKENS = 256
DEFAULT_PORT = 9000
DEFAULT_MODEL_NAME = "Muse-Glimmer-30B-int4"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="OVMS streaming benchmark")
    parser.add_argument("--url", default=f"http://localhost:{DEFAULT_PORT}/v2/chat/completions",
                        help="Chat completions endpoint URL")
    parser.add_argument("--model", default=DEFAULT_MODEL_NAME, help="Model name")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT, help="Prompt text")
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS, help="Max tokens to generate")
    parser.add_argument("--device", default="CPU", help="Device label for reporting")
    parser.add_argument("--timeout", type=int, default=300, help="Request timeout in seconds")
    parser.add_argument("--warmup", action="store_true", help="Run a warm-up request before measuring")
    parser.add_argument("--retries", type=int, default=1, help="Number of repeated runs (reports median/aggregate)")
    parser.add_argument("--csv", action="store_true", help="Output CSV instead of markdown table row")
    parser.add_argument("--output", help="Append results to a JSONL file")
    return parser.parse_args()


def build_payload(model: str, prompt: str, max_tokens: int) -> Dict[str, Any]:
    return {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
        "max_tokens": max_tokens,
    }


def stream_request(url: str, payload: Dict[str, Any], timeout: int) -> Optional[Dict[str, Any]]:
    """Send a streaming request and measure TTFT, total latency, throughput, token count."""
    start = time.perf_counter()
    first_token_time: Optional[float] = None
    token_count = 0

    try:
        with requests.post(url, json=payload, stream=True, timeout=timeout) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines(decode_unicode=True):
                if not line:
                    continue
                if not line.startswith("data: "):
                    continue
                data_str = line[6:].strip()
                if data_str == "[DONE]":
                    break
                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError:
                    continue
                if first_token_time is None:
                    first_token_time = time.perf_counter()
                delta = (
                    data.get("choices", [{}])[0]
                    .get("delta", {})
                    .get("content", "")
                )
                if delta:
                    token_count += 1
    except requests.RequestException as e:
        print(f"Request failed: {e}", file=sys.stderr)
        return None

    end = time.perf_counter()

    if first_token_time is None or token_count == 0:
        return None

    ttft_ms = (first_token_time - start) * 1000
    total_ms = (end - start) * 1000
    throughput = token_count / ((end - first_token_time) or 1e-9)

    return {
        "ttft_ms": round(ttft_ms, 2),
        "total_ms": round(total_ms, 2),
        "throughput_tok_s": round(throughput, 2),
        "tokens": token_count,
    }


def aggregate_results(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute aggregate statistics across multiple runs."""
    if not results:
        return {}

    def agg(key):
        vals = [r[key] for r in results]
        return {
            "mean": round(statistics.mean(vals), 2),
            "median": round(statistics.median(vals), 2),
            "stdev": round(statistics.stdev(vals), 2) if len(vals) > 1 else 0.0,
            "min": round(min(vals), 2),
            "max": round(max(vals), 2),
        }

    return {
        "runs": len(results),
        "ttft_ms": agg("ttft_ms"),
        "total_ms": agg("total_ms"),
        "throughput_tok_s": agg("throughput_tok_s"),
        "tokens": agg("tokens"),
    }


def format_markdown(device: str, agg: Dict[str, Any]) -> str:
    t = agg["ttft_ms"]
    tot = agg["total_ms"]
    thr = agg["throughput_tok_s"]
    tok = agg["tokens"]
    return (
        f"| {device} | {t['median']:.2f} | {tot['median']:.2f} | "
        f"{thr['median']:.2f} | {tok['median']:.0f} | "
        f"(n={agg['runs']}, mean ttft={t['mean']:.2f}ms, mean total={tot['mean']:.2f}ms) |"
    )


def format_csv(device: str, agg: Dict[str, Any]) -> str:
    t = agg["ttft_ms"]
    tot = agg["total_ms"]
    thr = agg["throughput_tok_s"]
    tok = agg["tokens"]
    fields = [
        device,
        t["median"], t["mean"], t["stdev"], t["min"], t["max"],
        tot["median"], tot["mean"], tot["stdev"], tot["min"], tot["max"],
        thr["median"], thr["mean"], thr["stdev"], thr["min"], thr["max"],
        tok["median"], tok["mean"], tok["stdev"], tok["min"], tok["max"],
        agg["runs"],
    ]
    return ",".join(str(v) for v in fields)


def write_jsonl(path: str, payload: Dict[str, Any], result: Dict[str, Any], agg: Dict[str, Any]) -> None:
    record = {
        "model": payload.get("model"),
        "prompt": payload.get("messages", [{}])[0].get("content", ""),
        "max_tokens": payload.get("max_tokens"),
        "run": result,
        "aggregate": agg,
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def main() -> int:
    args = parse_args()
    payload = build_payload(args.model, args.prompt, args.max_tokens)
    results: List[Dict[str, Any]] = []

    if args.warmup:
        print("Running warm-up request...", file=sys.stderr)
        stream_request(args.url, payload, args.timeout)

    for i in range(1, args.retries + 1):
        print(f"Run {i}/{args.retries}...", file=sys.stderr)
        result = stream_request(args.url, payload, args.timeout)
        if result is None:
            print(f"Benchmark failed on run {i}: no tokens received or request errored.", file=sys.stderr)
            return 1
        results.append(result)

    agg = aggregate_results(results)

    if args.output:
        write_jsonl(args.output, payload, results[-1], agg)

    if args.csv:
        header = (
            "device,"
            "ttft_ms_median,ttft_ms_mean,ttft_ms_stdev,ttft_ms_min,ttft_ms_max,"
            "total_ms_median,total_ms_mean,total_ms_stdev,total_ms_min,total_ms_max,"
            "throughput_median,throughput_mean,throughput_stdev,throughput_min,throughput_max,"
            "tokens_median,tokens_mean,tokens_stdev,tokens_min,tokens_max,"
            "runs"
        )
        if not hasattr(main, "_csv_header_written") or main._csv_header_written is False:
            print(header)
            main._csv_header_written = True
        print(format_csv(args.device, agg))
    else:
        print(format_markdown(args.device, agg))

    return 0


if __name__ == "__main__":
    sys.exit(main())
