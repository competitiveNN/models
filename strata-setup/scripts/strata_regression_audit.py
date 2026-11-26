#!/usr/bin/env python3
"""Strict SLA regression audit for Strata Dual-B580.

Measures decode and 64k-class prefill throughput, records a structured report,
and enforces explicit SLA gates.

Exit codes:
  0 - all gates passed
  1 - execution/error (server unreachable, malformed response, write failure)
  2 - measured but one or more SLA gates failed (hardware ceiling/regression)
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_URL = "http://127.0.0.1:1235/v1/chat/completions"
DEFAULT_OUTPUT = "runs/regression_audit_report.json"
DEFAULT_DECODE_TARGET = 50.0
DEFAULT_PREFILL_TARGET = 2000.0


def _git_sha() -> str | None:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            text=True,
            capture_output=True,
            check=False,
            timeout=5,
        )
        if proc.returncode == 0:
            return proc.stdout.strip()
    except Exception:  # noqa: BLE001
        return None
    return None


def post_json(url: str, payload: dict[str, Any], timeout: float) -> tuple[dict[str, Any], float]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST", headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as res:
        body = res.read().decode("utf-8", errors="replace")
    return json.loads(body), time.perf_counter() - t0


def _extract_metrics(resp: dict[str, Any], wall_s: float) -> dict[str, Any]:
    timings = resp.get("timings") or {}
    usage = resp.get("usage") or {}
    choices = resp.get("choices") or []
    msg = (choices[0].get("message") if choices else {}) or {}
    content = (msg.get("content") or "") + (msg.get("reasoning_content") or "")
    return {
        "success": True,
        "wall_s": wall_s,
        "prompt_tokens": timings.get("prompt_n", usage.get("prompt_tokens", 0)),
        "completion_tokens": timings.get("predicted_n", usage.get("completion_tokens", 0)),
        "prompt_tok_s": timings.get("prompt_per_second", 0),
        "decode_tok_s": timings.get("predicted_per_second", 0),
        "prompt_ms": timings.get("prompt_ms", 0),
        "coherence_pass": "!!!!!!" not in content,
        "content_preview": content[:120],
    }


def measure_decode(url: str, timeout: float) -> dict[str, Any]:
    prompt = "Explain the architectural implications of asymmetric PCIe links in multi-GPU inference."
    payload = {"model": "swift", "messages": [{"role": "user", "content": prompt}], "max_tokens": 64}
    try:
        resp, wall = post_json(url, payload, timeout)
        return _extract_metrics(resp, wall)
    except Exception as e:  # noqa: BLE001
        return {"success": False, "error": str(e), "error_type": type(e).__name__}


def measure_64k_prefill(url: str, timeout: float, prompt_chars: int) -> dict[str, Any]:
    base = "The quick brown fox jumps over the lazy dog. "
    prompt = (base * (prompt_chars // len(base) + 1))[:prompt_chars]
    payload = {"model": "swift", "messages": [{"role": "user", "content": prompt}], "max_tokens": 8}
    try:
        resp, wall = post_json(url, payload, timeout)
        m = _extract_metrics(resp, wall)
        m["prompt_chars"] = prompt_chars
        return m
    except Exception as e:  # noqa: BLE001
        return {"success": False, "error": str(e), "error_type": type(e).__name__, "prompt_chars": prompt_chars}


def build_report(args: argparse.Namespace, decode: dict[str, Any], prefill: dict[str, Any]) -> dict[str, Any]:
    decode_ok = bool(decode.get("success"))
    prefill_ok = bool(prefill.get("success"))
    decode_tok_s = float(decode.get("decode_tok_s") or 0) if decode_ok else 0.0
    prefill_tok_s = float(prefill.get("prompt_tok_s") or 0) if prefill_ok else 0.0
    decode_skipped = bool(decode.get("skipped"))
    prefill_skipped = bool(prefill.get("skipped"))
    gates = {
        "decode_passed": (decode_ok and decode_tok_s >= args.decode_target) if not decode_skipped else None,
        "prefill64k_passed": (prefill_ok and prefill_tok_s >= args.prefill_target) if not prefill_skipped else None,
        "coherence_passed": (
            (bool(decode.get("coherence_pass", False)) or decode_skipped)
            and (bool(prefill.get("coherence_pass", False)) or prefill_skipped)
        ),
    }
    active_gates = [v for v in gates.values() if v is not None]
    sla_passed = bool(active_gates) and all(active_gates) and decode_ok and prefill_ok
    return {
        "timestamp": time.time(),
        "timestamp_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "git_sha": _git_sha(),
        "host": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "cwd": os.getcwd(),
        },
        "config": {
            "url": args.url,
            "decode_target_tok_s": args.decode_target,
            "prefill_target_tok_s": args.prefill_target,
            "decode_timeout_s": args.decode_timeout,
            "prefill_timeout_s": args.prefill_timeout,
            "prefill_prompt_chars": args.prefill_prompt_chars,
        },
        "measured": {
            "decode": decode,
            "prefill64k": prefill,
        },
        "gates": gates,
        "sla_passed": sla_passed,
        "hardware_ceiling_note": (
            "2xB580 PP=2: no Level-Zero P2P, asymmetric PCIe x8/x4, 12GB/GPU, ~35.4% expert residency, "
            "TDR constraints; TP=2 not viable in current SYCL engine."
        ),
    }


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Strict SLA regression audit for Strata dual-B580")
    ap.add_argument("--url", default=os.environ.get("STRATA_URL", DEFAULT_URL))
    ap.add_argument("--output", default=os.environ.get("STRATA_AUDIT_OUT", DEFAULT_OUTPUT))
    ap.add_argument("--decode-target", type=float, default=float(os.environ.get("STRATA_DECODE_TARGET", DEFAULT_DECODE_TARGET)))
    ap.add_argument("--prefill-target", type=float, default=float(os.environ.get("STRATA_PREFILL_TARGET", DEFAULT_PREFILL_TARGET)))
    ap.add_argument("--decode-timeout", type=float, default=180.0)
    ap.add_argument("--prefill-timeout", type=float, default=900.0)
    ap.add_argument("--prefill-prompt-chars", type=int, default=65536)
    ap.add_argument("--skip-decode", action="store_true")
    ap.add_argument("--skip-prefill", action="store_true")
    args = ap.parse_args()

    print("Running strict SLA regression audit for Strata Dual-B580...")
    decode = {"success": True, "skipped": True} if args.skip_decode else measure_decode(args.url, args.decode_timeout)
    prefill = {"success": True, "skipped": True} if args.skip_prefill else measure_64k_prefill(args.url, args.prefill_timeout, args.prefill_prompt_chars)

    report = build_report(args, decode, prefill)
    try:
        write_report(Path(args.output), report)
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: failed to write report {args.output}: {e}")
        return 1

    if not decode.get("success"):
        print(f"ERROR: decode test failed: {decode.get('error')}")
        return 1
    if not prefill.get("success"):
        print(f"ERROR: prefill test failed: {prefill.get('error')}")
        return 1

    decode_tok_s = float(decode.get("decode_tok_s") or 0)
    prefill_tok_s = float(prefill.get("prompt_tok_s") or 0)
    print(f"Measured: decode_tok_s={decode_tok_s:.1f}, prefill64k_tok_s={prefill_tok_s:.1f}, prompt_tokens={prefill.get('prompt_tokens')}")
    print(f"Targets:  decode >= {args.decode_target}, prefill64k >= {args.prefill_target}")
    print(f"Report:   {args.output}")

    if report["sla_passed"]:
        print("PASS: strict SLA gates met.")
        return 0

    print("FAIL: strict SLA gates unmet. Keeping gap explicit (exit 2).")
    print(f"Note: {report['hardware_ceiling_note']}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
