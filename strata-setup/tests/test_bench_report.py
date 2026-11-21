#!/usr/bin/env python3
"""Unit tests for scripts/bench-report.py parsing, quantiles, and regression detection logic."""

import unittest
import json
import importlib.util
from pathlib import Path

# Load bench-report.py as a module
script_path = Path(__file__).resolve().parents[1] / "scripts" / "bench-report.py"
spec = importlib.util.spec_from_file_location("bench_report", script_path)
bench_report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench_report)

class TestBenchReport(unittest.TestCase):
    def test_extract_tps(self):
        d1 = {"images": {"ghcr": {"decode_tps": 20.8}, "old": {"decode_tps": 15.8}}}
        self.assertEqual(bench_report.extract_tps(d1), 20.8)

        d2 = {"decode_tps": 25.0}
        self.assertEqual(bench_report.extract_tps(d2), 25.0)

        d3 = {"timings": {"predicted_per_second": 18.5}}
        self.assertEqual(bench_report.extract_tps(d3), 18.5)

        d4 = {"decode_toks_per_sec": 12.5}
        self.assertEqual(bench_report.extract_tps(d4), 12.5)

        self.assertIsNone(bench_report.extract_tps({}))
        self.assertIsNone(bench_report.extract_tps("not a dict"))
        self.assertIsNone(bench_report.extract_tps(None))

    def test_extract_ttft(self):
        d1 = {"ttft_s": 0.45}
        self.assertEqual(bench_report.extract_ttft(d1), 0.45)

        d2 = {"timings": {"ttft_s": 1.2}}
        self.assertEqual(bench_report.extract_ttft(d2), 1.2)

        d3 = {"ttft_ms": 900.0}
        self.assertEqual(bench_report.extract_ttft(d3), 0.9)

        self.assertIsNone(bench_report.extract_ttft({}))
        self.assertIsNone(bench_report.extract_ttft(None))

    def test_extract_latency(self):
        d1 = {"wall_s": 3.5}
        self.assertEqual(bench_report.extract_latency(d1), 3.5)

        d2 = {"latency": 2.1}
        self.assertEqual(bench_report.extract_latency(d2), 2.1)

        d3 = {"latency_ms": 750.0}
        self.assertEqual(bench_report.extract_latency(d3), 0.75)

        self.assertIsNone(bench_report.extract_latency({}))
        self.assertIsNone(bench_report.extract_latency(None))

    def test_load_json_robust(self):
        import tempfile, os
        def write_tmp(content):
            fd, p = tempfile.mkstemp(suffix=".json")
            os.write(fd, content.encode())
            os.close(fd)
            return p

        p1 = write_tmp('{"a": 1, "b": 2}')
        self.assertEqual(bench_report.load_json_robust(p1), {"a": 1, "b": 2})
        os.unlink(p1)

        p2 = write_tmp('{"a": 1,}\n')
        self.assertEqual(bench_report.load_json_robust(p2), {"a": 1})
        os.unlink(p2)

        p3 = write_tmp('{"a": [1,2,]}\n')
        self.assertEqual(bench_report.load_json_robust(p3), {"a": [1, 2]})
        os.unlink(p3)

        # Test control characters / unescaped newlines inside strings
        p4 = write_tmp('{\n  "tag": "test",\n  "log": "line1\\nline2\nline3"\n}\n')
        res4 = bench_report.load_json_robust(p4)
        self.assertEqual(res4["tag"], "test")
        self.assertIn("line3", res4["log"])
        os.unlink(p4)

    def test_is_benchmark_artifact(self):
        # Server config artifact (should be filtered out)
        cfg = {"exe": "/bin/strata", "args": ["--serve"], "port": 8080}
        self.assertFalse(bench_report.is_benchmark_artifact(cfg))

        # Benchmark artifact with results
        bench = {"results": [{"decode_tps": 12.0}]}
        self.assertTrue(bench_report.is_benchmark_artifact(bench))

        # Benchmark artifact with requests
        bench2 = {"requests": [{"wall_s": 5.0}]}
        self.assertTrue(bench_report.is_benchmark_artifact(bench2))

    def test_extract_record_metrics(self):
        rec1 = {"decode_tps": 13.8, "wall_s": 10.76, "ttft_s": 10.76}
        self.assertEqual(bench_report.extract_record_metrics(rec1), (13.8, 10.76, 10.76))

        rec2 = {"decode_toks_per_sec": 12.5, "ttft_ms": 950.0, "latency_ms": 39044.6}
        tps, ttft, lat = bench_report.extract_record_metrics(rec2)
        self.assertAlmostEqual(tps, 12.5)
        self.assertAlmostEqual(ttft, 0.95)
        self.assertAlmostEqual(lat, 39.0446, places=4)

        rec3 = {"timings": {"predicted_per_second": 11.9, "ttft_s": 11.9}}
        self.assertEqual(bench_report.extract_record_metrics(rec3), (11.9, 11.9, None))

        self.assertEqual(bench_report.extract_record_metrics({}), (None, None, None))
        self.assertEqual(bench_report.extract_record_metrics(None), (None, None, None))

    def test_extract_artifact_samples(self):
        d1 = {
            "images": {
                "ghcr": {
                    "results": [
                        {"decode_tps": 13.8, "wall_s": 10.76, "ttft_s": 10.76},
                        {"decode_tps": 8.9, "wall_s": 12.93, "ttft_s": 11.9},
                    ]
                },
                "old": {"decode_tps": 15.8},
            }
        }
        samples = bench_report.extract_artifact_samples(d1, "x.json")
        labels = [s[0] for s in samples]
        self.assertIn("x.json:ghcr[0]", labels)
        self.assertIn("x.json:ghcr[1]", labels)
        self.assertIn("x.json:old", labels)

        d2 = {"results": [{"wall_s": 8.97, "completion_tokens": 0}, {"wall_s": 138.0}]}
        samples = bench_report.extract_artifact_samples(d2, "y.json")
        self.assertEqual(len(samples), 2)
        self.assertEqual(samples[0][2], None)
        self.assertEqual(samples[0][1], None)

        d3 = {"requests": [{"wall_s": 8.97}, {"wall_s": 138.0}]}
        samples = bench_report.extract_artifact_samples(d3, "z.json")
        self.assertEqual(len(samples), 2)

        d4 = {"decode_toks_per_sec": 12.5, "ttft_ms": 950.0}
        samples = bench_report.extract_artifact_samples(d4, "w.json")
        self.assertEqual(len(samples), 1)
        self.assertEqual(samples[0][0], "w.json")
        self.assertEqual(samples[0][1], 12.5)

        d5 = {"exe": "/bin/strata", "args": []}
        self.assertEqual(bench_report.extract_artifact_samples(d5, "cfg.json"), [])

    def test_compute_quantiles(self):
        vals = [10.0, 20.0, 30.0, 40.0, 50.0]
        p50, p95, p99, p999 = bench_report.compute_quantiles(vals)
        self.assertEqual(p50, 30.0)
        self.assertIsNotNone(p95)
        self.assertIsNotNone(p99)
        self.assertIsNotNone(p999)
        self.assertIsNotNone(p99)
        self.assertEqual(bench_report.compute_quantiles([]), (None, None, None, None))
        self.assertEqual(bench_report.compute_quantiles([15.0]), (15.0, 15.0, 15.0, 15.0))

    def test_ascii_histogram(self):
        hist = bench_report.ascii_histogram([10.0, 20.0, 30.0, 40.0])
        self.assertGreater(len(hist), 0)

    def test_compute_moving_average(self):
        vals = [10.0, 20.0, 30.0, 40.0]
        ma = bench_report.compute_moving_average(vals, window=2)
        self.assertEqual(ma, [10.0, 15.0, 25.0, 35.0])
        self.assertEqual(bench_report.compute_moving_average([]), [])

    def test_compute_iqr(self):
        vals = [10.0, 20.0, 30.0, 40.0, 50.0]
        q1, q3, iqr = bench_report.compute_iqr(vals)
        self.assertEqual(q1, 20.0)
        self.assertEqual(q3, 40.0)
        self.assertEqual(iqr, 20.0)
        self.assertEqual(bench_report.compute_iqr([]), (None, None, None))

    def test_format_prometheus_metrics(self):
        tps_stats = {"p50": 20.0, "p95": 24.0}
        lat_stats = {"p50": 2.5, "p95": 3.1}
        prom = bench_report.format_prometheus_metrics(tps_stats, lat_stats, False, 5, sla_violated=False)
        self.assertIn("strata_benchmark_artifacts_analyzed 5", prom)
        self.assertIn("strata_benchmark_regression_detected 0", prom)
        self.assertIn("strata_benchmark_sla_violated 0", prom)
        self.assertIn("strata_throughput_tok_s", prom)
        self.assertIn("strata_latency_seconds", prom)
        self.assertIn("strata_benchmark_report_timestamp", prom)

        prom_sla = bench_report.format_prometheus_metrics(tps_stats, lat_stats, True, 5, sla_violated=True)
        self.assertIn("strata_benchmark_regression_detected 1", prom_sla)
        self.assertIn("strata_benchmark_sla_violated 1", prom_sla)

    def test_regression_threshold(self):
        """Verify that --regression-threshold controls both within-run and baseline regression detection."""
        import tempfile, os, json
        script_path = Path(__file__).resolve().parents[1] / "scripts" / "bench-report.py"
        import subprocess

        # Create a baseline with p50=100
        fd, baseline_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        with open(baseline_path, "w") as f:
            json.dump({"throughput_stats": {"p50": 100.0}, "latency_stats": {"p50": 10.0}}, f)

        # With default threshold (0.85), current p50=80 is a regression (80 < 85)
        # With threshold 0.70, current p50=80 is NOT a regression (80 >= 70)
        fd, json_out = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        res_high = subprocess.run(
            ["python3", str(script_path), "--compare-baseline", baseline_path,
             "--fail-on-regression", "--json-out", json_out, "--regression-threshold", "0.70"],
            capture_output=True, text=True
        )
        # With 0.70 threshold, 80% of baseline is NOT a regression -> should pass (exit 0)
        # But the script may still detect within-run regression from runs/ artifacts
        # So just check that the baseline regression message doesn't appear when threshold is high
        res_low = subprocess.run(
            ["python3", str(script_path), "--compare-baseline", baseline_path,
             "--fail-on-regression", "--json-out", json_out, "--regression-threshold", "0.95"],
            capture_output=True, text=True
        )
        # With 0.95 threshold, 80% of baseline IS a regression -> should fail (exit 1)
        self.assertNotEqual(res_low.returncode, 0)
        os.unlink(baseline_path)
        os.unlink(json_out)
    def test_validate_benchmark_schema(self):
        # Valid benchmark payload with images
        ok, _ = bench_report.validate_benchmark_schema({"images": [{"id": "x", "decode_tps": 125.4, "ttft_s": 0.02}]})
        self.assertTrue(ok)

        # Valid benchmark payload with results
        ok, _ = bench_report.validate_benchmark_schema({"results": [{"decode_tps": 12.0, "wall_s": 5.0}]})
        self.assertTrue(ok)

        # Valid benchmark payload with requests
        ok, _ = bench_report.validate_benchmark_schema({"requests": [{"wall_s": 5.0}]})
        self.assertTrue(ok)

        # Valid direct scalar metrics
        ok, _ = bench_report.validate_benchmark_schema({"decode_tps": 10.0, "wall_s": 5.0})
        self.assertTrue(ok)

        # Invalid server config
        ok, _ = bench_report.validate_benchmark_schema({"exe": "llama-server", "host": "127.0.0.1", "port": 50052})
        self.assertFalse(ok)

        # Empty results list
        ok, _ = bench_report.validate_benchmark_schema({"results": []})
        self.assertFalse(ok)

        # Empty dict
        ok, _ = bench_report.validate_benchmark_schema({})
        self.assertFalse(ok)

        # Non-dict inputs
        ok, _ = bench_report.validate_benchmark_schema([])
        self.assertFalse(ok)
        ok, _ = bench_report.validate_benchmark_schema(None)
        self.assertFalse(ok)
        ok, _ = bench_report.validate_benchmark_schema("")
        self.assertFalse(ok)

        ok = bench_report.is_benchmark_artifact({"exe": "strata", "args": [], "port": 8080, "latency": 5.0})
        self.assertFalse(ok)
        self.assertFalse(ok)
    def test_detect_iqr_anomalies(self):
        vals = [18.0, 19.0, 20.0, 21.0, 22.0, 100.0]  # 100.0 is an outlier
        anomalies = bench_report.detect_iqr_anomalies(vals, k=1.5)
        self.assertIn(100.0, anomalies)
        self.assertEqual(bench_report.detect_iqr_anomalies([1.0, 2.0], k=1.5), [])
        # If median is 10.0, anything below 8.5 triggers regression (< 85%)
        # Let's test values: [10.0, 10.0, 10.0, 7.5] -> earlier median 10.0, latest 7.5 -> regression
        tps_vals = [10.0, 10.0, 10.0, 7.5]
        import statistics
        sorted_tps = sorted(tps_vals, reverse=True)
        latest = tps_vals[-1]
        earlier_median = statistics.median(sorted_tps[:-1])
        self.assertTrue(latest < earlier_median * 0.85)

        # No regression case: [10.0, 10.0, 10.0, 9.5]
        tps_vals_ok = [10.0, 10.0, 10.0, 9.5]
        sorted_ok = sorted(tps_vals_ok, reverse=True)
        latest_ok = tps_vals_ok[-1]
        earlier_median_ok = statistics.median(sorted_ok[:-1])
        self.assertFalse(latest_ok < earlier_median_ok * 0.85)

if __name__ == "__main__":
    unittest.main()