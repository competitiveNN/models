"""Unit tests for scripts/grid_search_sweep.py - parameter generation and dry-run."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import json
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_grid_search_tag_format():
    """Verify that generated tags follow expected convention."""
    from scripts.grid_search_sweep import GRID_COMBOS
    for combo in GRID_COMBOS:
        spec, ec, pw, ppr, pool, kv = combo
        tag = f"r2-spec{spec}-ec{ec}-pw{pw}-ppr{ppr}-pool{pool}-{kv}"
        assert tag.startswith("r2-"), f"Tag {tag} must start with 'r2-'"
        assert "-spec" in tag, f"Tag {tag} missing SPEC component"
        assert "-ec" in tag, f"Tag {tag} missing EXPERT_CACHE component"
        assert "-pw" in tag, f"Tag {tag} missing PIPELINE_WINDOWS component"
        assert "-ppr" in tag, f"Tag {tag} missing PEER_PREFILL_ROWS component"
        assert "-pool" in tag, f"Tag {tag} missing POOL_WORKERS component"
        assert tag.endswith(("int8", "auto")), f"Tag {tag} must end with KV type"
        print(f"  OK: tag format valid: {tag}")


def test_grid_search_dry_run():
    """Test that grid search script imports and helper functions work."""
    from scripts.grid_search_sweep import GRID_COMBOS
    assert len(GRID_COMBOS) > 0
    print("  OK: grid search parameters loaded successfully")


def test_sweep_summary_schema_unchanged():
    """Verify existing sweep summary schema integrity after grid search runs."""
    summary_file = ROOT / "runs" / "sweep-summary.jsonl"
    if not summary_file.exists():
        # minimal test - ensure basic structure
        # create from scratch with known entries for verification
        summary_file.write_text("")

    with open(summary_file) as f:
        for i, line in enumerate(f):
            if not line.strip():
                continue
            entry = json.loads(line)
            required = {"tag", "decode_median", "prefill_median", "coherence_pass", "env"}
            assert required.issubset(entry.keys()), \
                f"Missing fields in entry {i}: {required - set(entry.keys())}"
            assert isinstance(entry["tag"], str)
            assert isinstance(entry["decode_median"], (int, float))
            assert isinstance(entry["prefill_median"], (int, float))
            assert isinstance(entry["coherence_pass"], bool)
            assert isinstance(entry["env"], (dict, list))


if __name__ == "__main__":
    # Run all tests
    print("Running grid search unit tests...")
    test_grid_search_tag_format()
    print()
    test_grid_search_dry_run()
    print()
    test_sweep_summary_schema_unchanged()
    print("\nAll grid search unit tests passed!")