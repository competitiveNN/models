#!/usr/bin/env python3
"""OVMS benchmark for Muse-Glimmer-30B-int4"""

import requests
import time
import json
import sys
import os

BASE_URL = os.environ.get("OVMS_URL", "http://localhost:8000")
MODEL = "muse-glimmer-30b-int4-ov_model"
PROMPT = "Write a 4-sentence summary of the causes of the French Revolution."
MAX_TOKENS = 128
STREAM = True
API_KEY = os.environ.get("API_KEY", "abc")

def bench(device: str) -> dict:
    url = f"{BASE_URL}/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": PROMPT}],
        "max_tokens": MAX_TOKENS,
        "stream": STREAM,
        "device": device
    }
    start = time.perf_counter()
    first_chunk_time = None
    tokens_generated = 0
    try:
        with requests.post(url, headers=headers, json=payload, stream=True, timeout=120) as r:
            r.raise_for_status()
            for line in r.iter_lines(decode_unicode=True):
                if not line:
                    continue
                if line.strip() == "data: [DONE]":
                    break
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                if first_chunk_time is None:
                    first_chunk_time = time.perf_counter()
                if chunk.get("choices"):
                    delta = chunk["choices"][0].get("delta", {})
                    if "content" in delta and delta["content"]:
                        tokens_generated += 1
    except Exception as e:
        print(f"ERROR {device}: {e}")
        return {"device": device, "error": str(e)}

    end = time.perf_counter()
    if first_chunk_time is None:
        return {"device": device, "error": "no_chunks"}
    ttft = (first_chunk_time - start) * 1000
    total_ms = (end - start) * 1000
    throughput = (tokens_generated / ((end - first_chunk_time) * 1000)) * 1000 if end > first_chunk_time else 0
    return {
        "device": device,
        "ttft_ms": round(ttft, 1),
        "total_ms": round(total_ms, 1),
        "throughput_tok_s": round(throughput, 2),
        "tokens": tokens_generated,
    }

def main():
    devices = ["CPU"]
    if os.path.exists("/dev/nvidiactl"):
        devices += ["GPU.0", "GPU.1"]
    else:
        devices += ["GPU.0"]
    results = []
    for d in devices:
        print(f"Benchmarking {d}...", flush=True)
        results.append(bench(d))
    print("\n| Device | TTFT (ms) | Total Latency (ms) | Throughput (tokens/sec) | Tokens Generated |")
    print("|---|---|---|---|---|")
    for r in results:
        if "error" in r:
            print(f"| {r['device']} | ERROR | ERROR | ERROR | {r['error']} |")
        else:
            print(f"| {r['device']} | {r['ttft_ms']} | {r['total_ms']} | {r['throughput_tok_s']} | {r['tokens']} |")

if __name__ == "__main__":
    main()
