#!/usr/bin/env python3
"""Multi-region webhook failover dispatcher.

Tries primary endpoints first; on total primary failure, fails over to
backup endpoints. Tracks endpoint health and cooldown windows.
"""
import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys_path = ROOT / "scripts"
import sys
sys.path.insert(0, str(sys_path))
from regression_alert import send_webhook  # noqa: E402


class Endpoint:
    def __init__(self, url, region="default", role="primary", cooldown=300):
        self.url = url
        self.region = region
        self.role = role
        self.cooldown = cooldown
        self.healthy = True
        self.last_failure = 0.0

    def is_available(self, now=None):
        now = now if now is not None else time.time()
        if self.healthy:
            return True
        return (now - self.last_failure) >= self.cooldown

    def mark_failure(self, now=None):
        self.healthy = False
        self.last_failure = now if now is not None else time.time()

    def mark_success(self):
        self.healthy = True
        self.last_failure = 0.0


class FailoverRouter:
    def __init__(self, primary_urls, backup_urls=None, cooldown=300, max_workers=4):
        self.primary = [Endpoint(u, role="primary", cooldown=cooldown) for u in primary_urls]
        self.backup = [Endpoint(u, role="backup", cooldown=cooldown) for u in (backup_urls or [])]
        self.cooldown = cooldown
        self.max_workers = max_workers
        self.failover_events = []

    def _dispatch_group(self, endpoints, payload, dry_run=False, timeout=15, retries=1):
        available = [e for e in endpoints if e.is_available()]
        if not available:
            return None, [(e, False, "unavailable: cooldown") for e in endpoints]
        results = {}

        def _send(ep):
            ok, msg = send_webhook(ep.url, payload, dry_run=dry_run,
                                   timeout=timeout, retries=retries)
            return ep, ok, msg

        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(available) or 1)) as ex:
            futures = [ex.submit(_send, ep) for ep in available]
            for fut in as_completed(futures):
                ep, ok, msg = fut.result()
                results[ep] = (ok, msg)
                if ok:
                    ep.mark_success()
                else:
                    ep.mark_failure()

        # Preserve endpoint order for reporting.
        ordered = [(ep, results.get(ep, (False, "not attempted"))) for ep in available]
        for ep in available:
            ok, _ = results.get(ep, (False, ""))
            if ok:
                return ep, ordered
        return None, ordered

    def dispatch(self, payload, dry_run=False, timeout=15, retries=1):
        """Dispatch payload; fail over to backups if all primaries fail."""
        primary_ep, primary_results = self._dispatch_group(
            self.primary, payload, dry_run=dry_run, timeout=timeout, retries=retries)
        if primary_ep is not None:
            return {
                "status": "ok",
                "used": primary_ep.url,
                "role": "primary",
                "results": [(ep.url, ok, msg) for ep, (ok, msg) in primary_results],
                "failover": False,
            }

        # Fail over to backups.
        self.failover_events.append({"timestamp": time.time(), "reason": "primary_failure"})
        backup_ep, backup_results = self._dispatch_group(
            self.backup, payload, dry_run=dry_run, timeout=timeout, retries=retries)
        if backup_ep is not None:
            return {
                "status": "ok",
                "used": backup_ep.url,
                "role": "backup",
                "results": [(ep.url, ok, msg) for ep, (ok, msg) in backup_results],
                "failover": True,
            }

        return {
            "status": "failed",
            "used": None,
            "role": None,
            "results": [(ep.url, ok, msg) for ep, (ok, msg) in (primary_results + backup_results)],
            "failover": True,
        }

    def health_summary(self):
        return {
            "primary": [{"url": e.url, "healthy": e.healthy} for e in self.primary],
            "backup": [{"url": e.url, "healthy": e.healthy} for e in self.backup],
            "failover_events": len(self.failover_events),
        }


def main():
    ap = argparse.ArgumentParser(description="Dispatch a webhook with multi-region failover")
    ap.add_argument("--primary", nargs="+", required=True, help="Primary webhook URLs")
    ap.add_argument("--backup", nargs="*", default=[], help="Backup webhook URLs")
    ap.add_argument("--payload", default='{"text":"strata alert"}', help="JSON payload")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--timeout", type=int, default=15)
    ap.add_argument("--retries", type=int, default=2)
    args = ap.parse_args()

    try:
        payload = json.loads(args.payload)
    except json.JSONDecodeError:
        print("ERROR: invalid JSON payload", file=sys.stderr)
        return 1

    router = FailoverRouter(args.primary, args.backup)
    result = router.dispatch(payload, dry_run=args.dry_run,
                            timeout=args.timeout, retries=args.retries)
    print(json.dumps(result, indent=2))
    print(json.dumps(router.health_summary(), indent=2))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
