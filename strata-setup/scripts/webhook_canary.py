#!/usr/bin/env python3
"""Canary traffic shifting for webhook failover with automatic rollback.

Routes a configurable fraction of alerts to a canary endpoint, tracks
success rates, and promotes or rolls back based on thresholds.
"""
import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from regression_alert import send_webhook  # noqa: E402


class CanaryRouter:
    def __init__(self, primary, canary, fallback=None, canary_ratio=0.0,
                 min_samples=5, success_threshold=0.9, failure_threshold=0.5,
                 rng=None):
        self.primary = primary
        self.canary = canary
        self.fallback = fallback
        self.canary_ratio = canary_ratio
        self.min_samples = min_samples
        self.success_threshold = success_threshold
        self.failure_threshold = failure_threshold
        self.rng = rng or random.Random()
        self.stats = {
            "primary": {"success": 0, "failure": 0},
            "canary": {"success": 0, "failure": 0},
            "fallback": {"success": 0, "failure": 0},
        }
        self.decisions = []

    def _choose_endpoint(self):
        if self.canary_ratio > 0 and self.rng.random() < self.canary_ratio:
            return "canary", self.canary
        return "primary", self.primary

    def _record(self, name, ok):
        if ok:
            self.stats[name]["success"] += 1
        else:
            self.stats[name]["failure"] += 1

    def _success_rate(self, name):
        s = self.stats[name]["success"]
        f = self.stats[name]["failure"]
        total = s + f
        if total == 0:
            return None
        return s / total

    def _evaluate(self):
        rate = self._success_rate("canary")
        if rate is None or (self.stats["canary"]["success"] + self.stats["canary"]["failure"]) < self.min_samples:
            return
        if rate >= self.success_threshold:
            decision = "promote"
            self.canary_ratio = 1.0
        elif rate <= self.failure_threshold:
            decision = "rollback"
            self.canary_ratio = 0.0
        else:
            return
        self.decisions.append({"decision": decision, "success_rate": round(rate, 4)})

    def dispatch(self, payload, send_func=None, dry_run=False, timeout=15, retries=1):
        """Dispatch one alert through the canary decision process."""
        name, url = self._choose_endpoint()
        sender = send_func or send_webhook
        ok, msg = sender(url, payload, dry_run=dry_run, timeout=timeout, retries=retries)
        self._record(name, ok)

        used = name
        if not ok and self.fallback:
            ok2, msg2 = sender(self.fallback, payload, dry_run=dry_run,
                               timeout=timeout, retries=retries)
            self._record("fallback", ok2)
            if ok2:
                return {"status": "ok", "used": "fallback", "role": "fallback",
                        "message": msg2, "canary_ratio": self.canary_ratio}
            return {"status": "failed", "used": None, "role": None,
                    "message": f"{msg}; {msg2}", "canary_ratio": self.canary_ratio}

        self._evaluate()
        return {"status": "ok" if ok else "failed", "used": used,
                "role": used, "message": msg, "canary_ratio": self.canary_ratio}

    def summary(self):
        return {
            "canary_ratio": self.canary_ratio,
            "stats": self.stats,
            "decisions": self.decisions,
        }


def main():
    ap = argparse.ArgumentParser(description="Canary webhook dispatcher")
    ap.add_argument("--primary", required=True)
    ap.add_argument("--canary", required=True)
    ap.add_argument("--fallback", default=None)
    ap.add_argument("--payload", default='{"text":"alert"}')
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    try:
        payload = json.loads(args.payload)
    except json.JSONDecodeError:
        print("ERROR: invalid JSON payload", file=sys.stderr)
        return 1

    router = CanaryRouter(args.primary, args.canary, fallback=args.fallback,
                          canary_ratio=0.5)
    result = router.dispatch(payload, dry_run=args.dry_run)
    print(json.dumps(result, indent=2))
    print(json.dumps(router.summary(), indent=2))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
