#!/usr/bin/env python3
"""
Benchmark script for OpenVINO models

Tests latency and throughput for FP16 vs INT4 models
"""

import os
import sys
import time
import argparse
from pathlib import Path

import numpy as np
import openvino as ov
from openvino import Core

def benchmark_model(model_path, name, warmup_runs=3, test_runs=20, seq_len=5, batch_size=1):
    """Benchmark OpenVINO model"""
    print(f"\nBenchmarking {name}...")
    
    core = Core()
    model = core.read_model(str(model_path))
    compiled = core.compile_model(model, 'CPU')
    infer = compiled.create_infer_request()
    
    # Setup inputs
    input_ids = np.random.randint(200000, 202048, size=(batch_size, seq_len)).astype(np.int64)
    attention_mask = np.ones((batch_size, seq_len), dtype=np.int64)
    position_ids = np.arange(seq_len).reshape(1, seq_len).repeat(batch_size, axis=0).astype(np.int64)
    
    inputs = {
        'input_ids': input_ids,
        'attention_mask': attention_mask,
        'position_ids': position_ids
    }
    
    # Warmup
    print(f"  Warmup ({warmup_runs} runs)...")
    for _ in range(warmup_runs):
        infer.infer(inputs)
    
    # Benchmark
    print(f"  Testing ({test_runs} runs)...")
    times = []
    for _ in range(test_runs):
        start = time.perf_counter()
        infer.infer(inputs)
        end = time.perf_counter()
        times.append((end - start) * 1000)
    
    avg_time = sum(times) / len(times)
    min_time = min(times)
    max_time = max(times)
    throughput = 1000 / avg_time
    
    print(f"  Results:")
    print(f"    Avg latency: {avg_time:.2f} ms")
    print(f"    Min latency: {min_time:.2f} ms")
    print(f"    Max latency: {max_time:.2f} ms")
    print(f"    Std dev: {np.std(times):.2f} ms")
    print(f"    Throughput: {throughput:.2f} samples/sec")
    
    return {
        'name': name,
        'avg_latency_ms': avg_time,
        'min_latency_ms': min_time,
        'max_latency_ms': max_time,
        'std_ms': float(np.std(times)),
        'throughput': throughput
    }

def main():
    parser = argparse.ArgumentParser(description="Benchmark OpenVINO models")
    parser.add_argument("--fp16", required=True, help="FP16 model path")
    parser.add_argument("--int4", required=True, help="INT4 model path")
    parser.add_argument("--runs", type=int, default=20, help="Number of test runs")
    parser.add_argument("--seq-len", type=int, default=5, help="Sequence length")
    
    args = parser.parse_args()
    
    print("="*70)
    print("OpenVINO Model Benchmark")
    print("="*70)
    
    fp16_results = benchmark_model(args.fp16, "FP16", test_runs=args.runs, seq_len=args.seq_len)
    int4_results = benchmark_model(args.int4, "INT4", test_runs=args.runs, seq_len=args.seq_len)
    
    print("\n" + "="*70)
    print("Comparison:")
    print("="*70)
    
    latency_reduction = (fp16_results['avg_latency_ms'] - int4_results['avg_latency_ms']) / fp16_results['avg_latency_ms'] * 100
    throughput_increase = (int4_results['throughput'] - fp16_results['throughput']) / fp16_results['throughput'] * 100
    
    print(f"FP16: {fp16_results['avg_latency_ms']:.2f} ms avg, {fp16_results['throughput']:.2f} samples/sec")
    print(f"INT4: {int4_results['avg_latency_ms']:.2f} ms avg, {int4_results['throughput']:.2f} samples/sec")
    print(f"\nLatency reduction: {latency_reduction:.1f}%")
    print(f"Throughput increase: {throughput_increase:.1f}%")
    print("="*70)

if __name__ == "__main__":
    main()
