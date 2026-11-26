#!/usr/bin/env python3
"""
Strata Layer Cache Manager — Advanced weight-resident activation residency
optimizer for 2x B580 asymmetric x8/x4 PCIe topology.

Minimizes redundant PCIe staging during recurrent token generation by:
- Pinning hot expert weights to VRAM across decode steps
- Caching activation outputs for repeat-routed experts
- Managing host-VRAM mirror with LRU eviction under VRAM pressure
- Coordinating with STRATA_ASYNC_RING_BUFFER and STRATA_MOE_DMA_OVERLAP
"""
import os
import json
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

class LayerCacheManager:
    """
    Manages layer-wise weight residency and activation caching for Strata
    on asymmetric dual-GPU (x8/x4 PCIe) B580 topology.
    """
    
    def __init__(self, 
                 n_layers: int = 32,
                 n_experts: int = 8,
                 vram_budget_mib: int = 10240,
                 pcie_mode: str = "asymmetric"):
        self.n_layers = n_layers
        self.n_experts = n_experts
        self.vram_budget_bytes = vram_budget_mib * 1024 * 1024
        self.pcie_mode = pcie_mode
        
        # Per-layer expert residency: layer -> {expert_id: slot}
        self.expert_residency: Dict[int, Dict[int, int]] = {}
        
        # Activation cache: (layer, expert, token_hash) -> activation_ptr
        self.activation_cache: OrderedDict = OrderedDict()
        self.max_activation_cache_size = 1024
        
        # Hot experts per layer (routing frequency)
        self.expert_hotness: Dict[int, Dict[int, int]] = {}
        
        # PCIe bandwidth tracker
        self.pcie_bytes_staged = 0
        self.pcie_staging_events = 0
        
        # Thread safety
        self._lock = threading.RLock()
        
        # Callbacks for engine integration
        self.on_evict_callback = None
        self.on_stage_callback = None
    
    def record_expert_access(self, layer: int, expert_id: int, token_count: int = 1):
        """Record expert routing to build hotness profile."""
        with self._lock:
            if layer not in self.expert_hotness:
                self.expert_hotness[layer] = {}
            self.expert_hotness[layer][expert_id] = \
                self.expert_hotness[layer].get(expert_id, 0) + token_count
    
    def get_hot_experts(self, layer: int, top_k: int = 4) -> List[int]:
        """Return top-K most frequently routed experts for a layer."""
        with self._lock:
            hotness = self.expert_hotness.get(layer, {})
            return sorted(hotness.keys(), key=lambda e: hotness[e], reverse=True)[:top_k]
    
    def pin_hot_experts(self, layer: int, hot_experts: List[int]) -> List[int]:
        """
        Pin hot experts to VRAM slots. Returns list of newly pinned expert IDs.
        """
        with self._lock:
            if layer not in self.expert_residency:
                self.expert_residency[layer] = {}
            
            pinned = []
            for expert_id in hot_experts:
                if expert_id not in self.expert_residency[layer]:
                    # Simulate VRAM slot allocation
                    slot = len(self.expert_residency[layer])
                    self.expert_residency[layer][expert_id] = slot
                    pinned.append(expert_id)
                    
                    if self.on_stage_callback:
                        self.on_stage_callback(layer, expert_id, slot, "pin")
            
            return pinned
    
    def evict_cold_experts(self, layer: int, keep_experts: List[int]) -> List[int]:
        """Evict experts not in keep list to free VRAM."""
        with self._lock:
            if layer not in self.expert_residency:
                return []
            
            evicted = []
            for expert_id in list(self.expert_residency[layer].keys()):
                if expert_id not in keep_experts:
                    slot = self.expert_residency[layer].pop(expert_id)
                    evicted.append(expert_id)
                    
                    if self.on_evict_callback:
                        self.on_evict_callback(layer, expert_id, slot)
            
            return evicted
    
    def cache_activation(self, layer: int, expert_id: int, 
                         token_hash: int, activation_ptr: int):
        """Cache activation output for recurrent routing."""
        with self._lock:
            key = (layer, expert_id, token_hash)
            self.activation_cache[key] = activation_ptr
            
            # LRU eviction
            if len(self.activation_cache) > self.max_activation_cache_size:
                self.activation_cache.popitem(last=False)
    
    def get_cached_activation(self, layer: int, expert_id: int, 
                               token_hash: int) -> Optional[int]:
        """Retrieve cached activation if available."""
        with self._lock:
            key = (layer, expert_id, token_hash)
            if key in self.activation_cache:
                # Move to end (MRU)
                val = self.activation_cache.pop(key)
                self.activation_cache[key] = val
                return val
            return None
    
    def record_pcie_staging(self, bytes_count: int):
        """Track PCIe bandwidth usage for monitoring."""
        with self._lock:
            self.pcie_bytes_staged += bytes_count
            self.pcie_staging_events += 1
    
    def get_stats(self) -> Dict:
        """Return cache manager statistics."""
        with self._lock:
            total_resident = sum(len(v) for v in self.expert_residency.values())
            return {
                "total_resident_experts": total_resident,
                "activation_cache_size": len(self.activation_cache),
                "pcie_bytes_staged": self.pcie_bytes_staged,
                "pcie_staging_events": self.pcie_staging_events,
                "vram_budget_mib": self.vram_budget_bytes // (1024*1024)
            }
    
    def configure_for_asymmetric_pcie(self, gpu0_bandwidth_gbs: float = 15.75,
                                       gpu1_bandwidth_gbs: float = 5.25):
        """Configure cache strategy for asymmetric x8/x4 PCIe links."""
        # GPU0 (x8) gets more resident experts, GPU1 (x4) gets fewer
        # This is a hint for the engine's layer split
        self.pcie_mode = "asymmetric"
        return {
            "gpu0_max_resident_experts": int((self.vram_budget_bytes * 0.6) / (256 * 1024)),
            "gpu1_max_resident_experts": int((self.vram_budget_bytes * 0.4) / (256 * 1024)),
            "preferred_layer_split": "27",  # earlier split for GPU0-heavy
            "staging_priority": "gpu1_first"  # stage GPU1 experts first (slower link)
        }


def main():
    """Demo / self-test."""
    mgr = LayerCacheManager(n_layers=32, n_experts=8, vram_budget_mib=10240)
    
    # Simulate routing hotness
    for _ in range(100):
        mgr.record_expert_access(0, 2, 1)
        mgr.record_expert_access(0, 5, 1)
        mgr.record_expert_access(1, 1, 1)
        mgr.record_expert_access(1, 3, 1)
    
    # Pin hot experts
    hot_l0 = mgr.get_hot_experts(0, top_k=4)
    mgr.pin_hot_experts(0, hot_l0)
    
    hot_l1 = mgr.get_hot_experts(1, top_k=4)
    mgr.pin_hot_experts(1, hot_l1)
    
    # Configure for asymmetric PCIe
    asymmetric_cfg = mgr.configure_for_asymmetric_pcie()
    
    print(json.dumps({
        "hot_experts_layer_0": hot_l0,
        "hot_experts_layer_1": hot_l1,
        "asymmetric_config": asymmetric_cfg,
        "stats": mgr.get_stats()
    }, indent=2))


if __name__ == "__main__":
    main()
