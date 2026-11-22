#!/usr/bin/env python3
"""Pin and verify the built strata-old container image digest.

Records the image digest to a file and verifies the current image matches.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DIGEST_FILE = ROOT / "configs" / "strata-old-image-digest.json"
IMAGE = "localhost/strata-old:latest"


def get_image_digest() -> str:
    """Get the digest of the currently built image."""
    try:
        res = subprocess.run(
            ["podman", "inspect", "--format", "{{.Digest}}", IMAGE],
            capture_output=True, text=True, timeout=30,
        )
        if res.returncode == 0:
            return res.stdout.strip()
    except Exception:
        pass
    # Fallback: try docker
    try:
        res = subprocess.run(
            ["docker", "inspect", "--format", "{{.Id}}", IMAGE],
            capture_output=True, text=True, timeout=30,
        )
        if res.returncode == 0:
            return res.stdout.strip()
    except Exception:
        pass
    return ""


def pin_digest() -> dict[str, Any]:
    """Record the current image digest to file."""
    digest = get_image_digest()
    if not digest:
        return {"status": "error", "message": "Could not retrieve image digest"}
    data = {
        "image": IMAGE,
        "digest": digest,
        "pinned_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
    }
    DIGEST_FILE.parent.mkdir(parents=True, exist_ok=True)
    DIGEST_FILE.write_text(json.dumps(data, indent=2))
    return {"status": "ok", "digest": digest, "file": str(DIGEST_FILE)}


def verify_digest() -> dict[str, Any]:
    """Verify the current image matches the pinned digest."""
    if not DIGEST_FILE.exists():
        return {"status": "error", "message": "No pinned digest found. Run --pin first."}
    data = json.loads(DIGEST_FILE.read_text())
    current = get_image_digest()
    if not current:
        return {"status": "error", "message": "Could not retrieve current image digest"}
    if current == data["digest"]:
        return {"status": "ok", "digest": current, "match": True}
    return {"status": "mismatch", "pinned": data["digest"], "current": current, "match": False}


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Pin or verify strata-old image digest")
    ap.add_argument("--pin", action="store_true", help="Pin current image digest")
    ap.add_argument("--verify", action="store_true", help="Verify current image matches pinned digest")
    args = ap.parse_args()

    if args.pin:
        result = pin_digest()
    elif args.verify:
        result = verify_digest()
    else:
        result = verify_digest() if DIGEST_FILE.exists() else pin_digest()

    print(json.dumps(result, indent=2))
    return 0 if result.get("status") == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())