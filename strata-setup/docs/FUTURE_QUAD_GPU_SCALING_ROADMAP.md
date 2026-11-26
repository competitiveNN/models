# Future Quad-GPU & Advanced Pipeline Scaling Roadmap (Strata SYCL Engine)

**Date:** 2026-11-26  
**Scope:** Scaling beyond dual-B580 hardware ceilings via 4× B580 Pipeline Parallelism (PP=4), symmetric PCIe topologies, and distributed host staging.

---

## 1. Executive Vision
As established by our empirical hardware ceiling audits (`docs/B580_CEILING_AUDIT.md`), dual Intel Arc B580 GPUs operating under asymmetric PCIe x8/x4 topology with no Level-Zero P2P fabric are strictly bounded at ~15.5 tok/s decode and ~1000 tok/s 64k prefill. 

To break past these hardware limits and achieve the stretch targets (~50 tok/s decode, ≥2000 tok/s prefill), we must transition from 2-card Pipeline Parallelism (`PP=2`) to a **Quad-GPU distributed architecture (`PP=4` or `PP=2/DP=2`)**.

---

## 2. Quad-GPU (`4× B580`) Architectural Blueprint

### 2.1 Layer & VRAM Redistribution
- **Current (2× B580, PP=2):**
  - GPU 0 (PCIe x8): Layers 0–25 (~11.33 GB VRAM)
  - GPU 1 (PCIe x4): Layers 26–47 (~11.33 GB VRAM)
  - *Bottleneck:* GPU 1's x4 bus (~7 GB/s) restricts all stage handoffs.
- **Proposed (4× B580, PP=4):**
  - GPU 0 (x16/x8 slot 1): Layers 0–11
  - GPU 1 (x8 slot 2): Layers 12–23
  - GPU 2 (x8 slot 3): Layers 24–35
  - GPU 3 (x8 slot 4): Layers 36–47
  - *Benefit:* Reduces per-card layer quota by 50%, cuts inter-stage payload size per hop, and increases total VRAM to **45.3 GB**, elevating MoE expert residency from ~35.4% to **>75%**.

### 2.2 Host-Assisted Multi-Cast Staging (`STRATA_HOST_CAST=1`)
- Since Level-Zero does not currently support direct peer-to-peer memory transfers between disparate consumer Battlemage boards, a distributed host-side casting daemon (`PinnedRing` expanded to 4 ring queues with dedicated PCIe DMA threads) can overlap broadcast distribution of prompt tokens across all four cards simultaneously.

---

## 3. Implementation Plan & Milestones

1. **Multi-Card Launch Scripting (`run-strata-4gpu.sh`):**
   - Extend `run-strata-2gpu.sh` to accept `--gpu 0,1,2,3`, binding four render nodes (`renderD128` through `renderD131`) and setting `ONEAPI_DEVICE_SELECTOR=level_zero:0;level_zero:1;level_zero:2;level_zero:3`.
2. **Dynamic Residency Profiling (`scripts/vram_balancer.py`):**
   - Automate the calculation of optimal layer split quotas based on dynamic VRAM footprint and PCIe bus width detection.
3. **Automated SLA Gate Adjustment:**
   - Update `scripts/strata_regression_audit.py` to support multi-card threshold profiles (`PP=4` target scaling: decode ≥35 tok/s, 64k prefill ≥1800 tok/s).

---

## 4. Conclusion
While 2× B580 hardware limits are unbridgeable by software tuning alone, planning and structuring the `PP=4` Quad-GPU roadmap provides an immediate, engineering-sound upgrade path for achieving high-throughput local MoE inference on Intel Battlemage hardware.
