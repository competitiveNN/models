"""Pure-Python regression guard for the strata-old 2x B580 image build.

Checks that the Containerfile / .dockerignore / run-strata-2gpu.sh guard the
regressions we already fixed:
  - No oneAPI 2026.2 level-zero lib64 in the image (glibc 2.41 incompatibility)
  - Engine component copy step present
  - strata-old-source in .dockerignore
  - run-strata-2gpu.sh uses the local image path and /opt/strata/terminal/bin/strata
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _file(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def _has_level_zero_copy(content: str) -> bool:
    return "level-zero/lib64" in content


class TestContainerfile(unittest.TestCase):
    def test_no_level_zero_20262_copy(self):
        cf = ROOT / "Containerfile.strata"
        self.assertTrue(cf.exists(), "Containerfile.strata must exist")
        c = _file(cf)
        self.assertFalse(_has_level_zero_copy(c),
                         "Containerfile copies level-zero lib64 from oneAPI 2026.2; "
                         "this requires glibc >= 2.41 and breaks Ubuntu 24.04")

    def test_engine_component_copy_step(self):
        cf = ROOT / "Containerfile.strata"
        self.assertTrue(cf.exists(), "Containerfile.strata must exist")
        c = _file(cf)
        self.assertIn("/root/.local", c,
                      "Containerfile must reference strata engine component path")

    def test_dockerignore_has_strata_old_source(self):
        doi = ROOT / ".dockerignore"
        if not doi.exists():
            return
        c = _file(doi)
        lines = [l.strip() for l in c.splitlines() if l.strip() and not l.startswith("#")]
        has_exclude = any("strata-old-source" in l and not l.startswith("!") for l in lines)
        if has_exclude:
            later = any(l.startswith("!") and "strata-old-source" in l for l in lines)
            self.assertTrue(later, ".dockerignore excludes strata-old-source without a later re-include")

    def test_run_strata_2gpu_uses_local_image(self):
        rs = ROOT / "run-strata-2gpu.sh"
        if not rs.exists():
            return
        c = _file(rs)
        self.assertIn("localhost/strata-old:latest", c,
                      "run-strata-2gpu.sh must target localhost/strata-old:latest image")
        self.assertTrue(
            "/opt/strata/terminal/bin/strata" in c or "/opt/strata/terminal/strata.py" in c,
            "run-strata-2gpu.sh should invoke strata via /opt/strata/terminal/ path")

    def test_run_strata_2gpu_has_b580_tuning(self):
        """run-strata-2gpu.sh must carry the documented B580 tuning."""
        rs = ROOT / "run-strata-2gpu.sh"
        if not rs.exists():
            return
        c = _file(rs)
        required = [
            "gpu",
            "pipeline-windows",
            "vram-reserve-mib",
            "expert-cache",
            "spec",
            "spec-min-p",
            "pool-workers",
            "expert-cache-per-layer",
            "stream-experts",
            "mmap-experts",
            "ONEAPI_DEVICE_SELECTOR",
        ]
        for key in required:
            self.assertIn(key, c, f"run-strata-2gpu.sh missing B580 tuning: {key}")

    def test_containerfile_healthcheck_port_matches_entrypoint(self):
        """Healthcheck should target the port the entrypoint serves (8080)."""
        cf = ROOT / "Containerfile.strata"
        if not cf.exists():
            return
        c = _file(cf)
        # The entrypoint defaults PORT=8080; healthcheck must not target 8081.
        self.assertNotIn("localhost:8081/health", c,
                         "healthcheck targets 8081 but entrypoint serves 8080")
        self.assertIn("localhost:8080/health", c,
                      "healthcheck must target localhost:8080/health")

    def test_contains_2gpu_config_keys(self):
        import importlib.util
        _vc = Path(__file__).resolve().parents[1] / 'scripts' / 'validate_configs.py'
        _spec = importlib.util.spec_from_file_location('validate_configs', _vc)
        _v = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_v)
        REQUIRED_ARGS = _v.REQUIRED_ARGS
        cfg = ROOT / "configs" / "strata-swift-iq3_xxs-2gpu-clean.json"
        if not cfg.exists():
            return
        d = json.loads(cfg.read_text())
        args = d.get("args") or []
        present = {args[i] for i in range(len(args) - 1) if args[i] in REQUIRED_ARGS}
        for a in REQUIRED_ARGS:
            self.assertIn(a, present,
                          f"required config arg {a} is missing from strata-swift-iq3_xxs-2gpu-clean.json")


if __name__ == "__main__":
    unittest.main()
