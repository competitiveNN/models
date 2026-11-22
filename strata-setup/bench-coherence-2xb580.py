#!/usr/bin/env python3
"""Coherence regression gate for the strata-old 2x B580 (TP2) inference server.

Posts a few prompts to the OpenAI-compatible endpoint and fails if any reply
shows a repetitive artifact loop (`!!!!!!`) or otherwise degenerates.
Stdlib only: it runs on the host without extra packages.
"""
import argparse
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))
from coherence import detect_degenerate

DEFAULT_URL = "http://127.0.0.1:1235/v1/chat/completions"

PROMPTS = [
    ("quantum", "Explain quantum computing in one short sentence."),
    ("capital", "What is the capital of France?"),
    ("code", "Write a python function to compute the factorial of a number."),
    ("prose", "Summarise the plot of Romeo and Juliet in two sentences."),
]


def ask(url, prompt, max_tokens, timeout):
    payload = {"model": "swift", "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json", "Connection": "close"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as res:
        body = json.loads(res.read().decode("utf-8"))
    return body["choices"][0]["message"].get("content", "") or ""


def main():
    ap = argparse.ArgumentParser(description="strata-old 2x B580 coherence gate")
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--max-tokens", type=int, default=150)
    ap.add_argument("--timeout", type=float, default=180.0, help="seconds per request (cold expert loads are slow)")
    args = ap.parse_args()

    failed = 0
    for name, prompt in PROMPTS:
        try:
            content = ask(args.url, prompt, args.max_tokens, args.timeout)
        except Exception as e:
            print(f"[FAIL] {name}: request error: {e}")
            failed += 1
            continue
        reason = detect_degenerate(content)
        print(f"[{'FAIL' if reason else 'PASS'}] {name}: {prompt}")
        print(f"       -> {content.strip()[:300]}")
        if reason:
            print(f"       degenerate output: {reason}")
            failed += 1

    print("-" * 60)
    if failed:
        print(f"Coherence gate FAILED ({failed}/{len(PROMPTS)}).")
        return 1
    print(f"Coherence gate PASSED ({len(PROMPTS)}/{len(PROMPTS)}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
