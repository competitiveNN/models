#!/usr/bin/env python3
"""
Strata Async Overlap Scheduler — Pipelined PCIe ring staging overlap with
GPU GEMM execution for asymmetric 2× B580 (x8/x4) topology.

Overlaps cross-card DMA staging with compute kernels to hide PCIe latency
and maximize bus saturation during recurrent token generation.
"""
import os
import json
import threading
import time
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Callable

class AsyncOverlapScheduler:
    """
    Async pipelined overlap scheduler for Strata 2x B580.
    Schedules PCIe ring staging in flight with GPU GEMM kernels.
    """
    
    def __init__(self,
                 n_gpus: int = 2,
                 pcie_links: Dict[int, float] = None,
                 ring_buffer_mib: int = 256,
                 max_queued_rings: int = 8):
        self.n_gpus = n_gpus
        self.pcie_links = pcie_links or {0: 15.75, 1: 5.25}  # x8, x4 GB/s
        self.ring_buffer_mib = ring_buffer_mib
        self.max_queued_rings = max_queued_rings
        
        # Pipeline stages per GPU
        self.pipeline_stages: Dict[int, List[Dict]] = {g: [] for g in range(n_gpus)}
        
        # Currently running rings: gpu_id -> ring info
        self.running_rings: Dict[int, Optional[Dict]] = {g: None for g in range(n_gpus)}
        
        # Queued rings: FIFO per GPU
        self.queued_rings: Dict[int, List[Dict]] = {g: [] for g in range(n_gpus)}
        
        # Bandwidth tracking
        self.pcie_bandwidth_used: Dict[int, float] = {g: 0.0 for g in range(n_gpus)}
        self.ring_submit_latency_us: float = 0.0
        
        # Thread safety
        self._scheduler_lock = threading.Lock()
        self._running = False
        
        # Callbacks
        self.on_ring_scheduled: Optional[Callable] = None
        self.on_ring_complete: Optional[Callable] = None
    
    def schedule_ring_staging(self,
                              gpu_id: int,
                              ring_data_size_mib: float,
                              gemm_kernel_fn: Callable,
                              gemm_args: Tuple,
                              priority: str = "normal") -> Optional[Dict]:
        """
        Schedule a ring staging operation that overlaps with GEMM execution.
        Returns the scheduled ring token, or None if queue full.
        """
        with self._scheduler_lock:
            # Calculate staging time based on PCIe bandwidth
            bandwidth_gbs = self.pcie_links.get(gpu_id, 10.0)
            staging_time_us = (ring_data_size_mib * 1024 * 1024) / (bandwidth_gbs * 1e6) * 1e6
            
            # Calculate GEMM execution time (estimated)
            # In production, this would use actual kernel timing
            gemm_estimated_us = max(1000, staging_time_us * 0.8)  # GEMM typically longer
            
            ring_token = {
                "id": f"ring_{gpu_id}_{int(time.time()*1e6)}",
                "gpu_id": gpu_id,
                "data_size_mib": ring_data_size_mib,
                "bandwidth_gbs": bandwidth_gbs,
                "staging_time_us": staging_time_us,
                "gemm_estimated_us": gemm_estimated_us,
                "priority": priority,
                "submit_time": time.time(),
                "status": "queued"
            }
            
            # Add to GPU queue
            self.queued_rings[gpu_id].append(ring_token)
            
            # Keep queue bounded
            if len(self.queued_rings[gpu_id]) > self.max_queued_rings:
                self.queued_rings[gpu_id].pop(0)
            
            # If not running, start the pipeline
            if self.running and self.running_rings[gpu_id] is None:
                self._start_ring_pipeline(gpu_id, ring_token)
            
            if self.on_ring_scheduled:
                self.on_ring_scheduled(ring_token)
            
            return ring_token
    
    def _start_ring_pipeline(self, gpu_id: int, first_ring: Dict):
        """Start the overlap pipeline for a GPU."""
        self.running_rings[gpu_id] = first_ring
        first_ring["status"] = "staging_in_flight"
        
        # Simulate async staging + GEMM overlap
        def pipeline_task():
            try:
                # Phase 1: Start PCIe staging (non-blocking conceptual)
                staging_duration = first_ring["staging_time_us"]
                time.sleep(staging_duration / 1e6)  # conceptual wait
                
                # Phase 2: GEMM execution overlaps with remaining staging
                gemm_duration = first_ring["gemm_estimated_us"]
                overlap_remaining = max(0, staging_time_us - gemm_duration)
                
                # Phase 3: Ring complete notification
                first_ring["status"] = "complete"
                first_ring["completed_time"] = time.time()
                
                if self.on_ring_complete:
                    self.on_ring_complete(first_ring)
                
                self.running_rings[gpu_id] = None
                
                # Process next queued ring
                with self._scheduler_lock:
                    if self.queued_rings[gpu_id]:
                        next_ring = self.queued_rings[gpu_id].pop(0)
                        self._start_ring_pipeline(gpu_id, next_ring)
            except Exception as e:
                print(f"Pipeline error on GPU {gpu_id}: {e}")
                self.running_rings[gpu_id] = None
        
        # Fire-and-forget pipeline thread (conceptual - in production uses CUDA streams)
        threading.Thread(target=pipeline_task, daemon=True).start()
    
    def process_ring_complete(self, gpu_id: int, ring_token: Dict):
        """Called when a ring staging completes."""
        with self._scheduler_lock:
            ring_token["status"] = "completed"
            ring_token["complete_time"] = time.time()
            
            # Update bandwidth tracking
            self.pcie_bandwidth_used[gpu_id] += ring_token["data_size_mib"]
            
            if self.on_ring_complete:
                self.on_ring_complete(ring_token)
            
            # Release running slot
            self.running_rings[gpu_id] = None
            
            # Try to start next queued ring
            if self.queued_rings[gpu_id]:
                next_ring = self.queued_rings[gpu_id].pop(0)
                self._start_ring_pipeline(gpu_id, next_ring)
    
    def get_scheduler_stats(self) -> Dict:
        """Return scheduler optimization statistics."""
        with self._scheduler_lock:
            total_rings = sum(len(v) for v in self.queued_rings.values()) + sum(
                1 for v in self.running_rings.values() if v is not None)
            
            total_bandwidth = sum(self.pcie_bandwidth_used.values())
            
            return {
                "n_gpus": self.n_gpus,
                "queued_rings": total_rings,
                "running_rings": sum(1 for v in self.running_rings.values() if v is not None),
                "pcie_bandwidth_used_mib": total_bandwidth,
                "pcie_links_gbs": self.pcie_links,
                "max_queued_rings": self.max_queued_rings,
                "ring_buffer_mib": self.ring_buffer_mib,
                "bandwidth_util_pct": min(100.0, (total_bandwidth / (sum(self.pcie_links.values()) * 1e3)) * 100)
            }
    
    def configure_for_asymmetric_b580(self):
        """Configure scheduler specifically for 2x B580 asymmetric PCIe."""
        # GPU0 (x8) gets priority for latency-sensitive rings
        # GPU1 (x4) gets throughput-oriented rings with longer staging
        self.pcie_links = {0: 15.75, 1: 5.25}
        return {
            "gpu0_ring_buffer": self.ring_buffer_mib,
            "gpu1_ring_buffer": self.ring_buffer_mib // 2,  # x4 link: half ring size
            "gpu0_priority_weight": 1.3,  # favor GPU0 staging first
            "gpu1_priority_weight": 0.7,
            "pipeline_fill_mode": "alternating",  # overlap GPU0 then GPU1
            "staging_overlap_goal": "hide_pcie_latency_under_gemm"
        }

def demo():
    """Demonstrate overlap scheduler on asymmetric B580."""
    scheduler = AsyncOverlapScheduler(n_gpus=2)
    
    # Configure for B580 asymmetric PCIe
    b580_cfg = scheduler.configure_for_asymmetric_b580()
    print("B580 Asymmetric PCIe Config:")
    for k, v in b580_cfg.items():
        print(f"  {k}: {v}")
    
    # Schedule sample rings for both GPUs
    for i in range(4):
        ring0 = scheduler.schedule_ring_staging(
            gpu_id=0,
            ring_data_size_mib=128,
            gemm_kernel_fn=lambda: None,  # placeholder
            gemm_args=(),
            priority="high" if i % 2 == 0 else "normal"
        )
        
        ring1 = scheduler.schedule_ring_staging(
            gpu_id=1,
            ring_data_size_mib=64,
            gemm_kernel_fn=lambda: None,
            gemm_args=(),
            priority="normal"
        )
    
    # Print stats
    stats = scheduler.get_scheduler_stats()
    print("\nScheduler Stats:")
    for k, v in stats.items():
        print(f"  {k}: {v}")

if __name__ == "__main__":
    demo()
