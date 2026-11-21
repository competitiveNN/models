# Intel Arc B580 Dual-GPU Optimization Guide

## Hardware Profile (2× Intel Arc B580)
| Property | Per GPU | Aggregate (2×) |
|----------|---------|----------------|
| Architecture | Xe2-HPG (Battlemage) | — |
| VRAM | 12 GB GDDR6 | 24 GB |
| Bandwidth | 456 GB/s | 912 GB/s |
| XMX INT4 TOPS | 437.5 | 875 |
| PCIe | 4.0 x8 | Asymmetric (x16 + x4) |
| TDP | 190 W | 380 W |

## Key Optimization Decisions

### 1. Asymmetric PCIe Topology
- One B580 on PCIe x16, one on x4
- `STRATA_COPY_ENGINE=0` — disables copy engine to avoid PCIe bottleneck on x4 link
- Layer placement favors the x16 GPU for communication-heavy operations

### 2. IGC GEP Simplification Workaround
- `IGC_EnableGEPSimplification=0` — prevents miscompilation on Xe2 targets
- Must be set before SYCL runtime lists devices (done in Containerfile.edge ENV)

### 3. Expert Cache Scaling
- Default: 1024 → Optimized: 2048 (24 GB total VRAM allows larger cache)
- Reduces expert loading latency for MoE models

### 4. Speculative Decoding
- Default spec=4 → Optimized spec=6 (deeper speculation for better throughput)
- spec-min-p=0.5 maintained for quality

### 5. Pool Workers
- Default: 8 → Optimized: 12 (more parallelism for dual-GPU)
- pool-affinity: p-cores (pin to performance cores)

### 6. VRAM Reserve
- Default: 700 MiB → Optimized: 512 MiB (24 GB total allows tighter reserve)

### 7. Pipeline Windows
- pipeline-windows=2 (optimal for 2-GPU layer split)

## Configuration Files
- `configs/strata-swift-iq3_xxs-2gpu-clean.json` — Baseline stable config
- `configs/strata-swift-iq3_xxs-2gpu-optimized.json` — Optimized for B580 dual-GPU

## Container Image
- Base: Intel Deep Learning Essentials 2025.3.3
- AOT target: bmg-g21 (Xe2)
- XMX SG16 enabled for matrix operations
- Runtime: minimal with Level Zero + IGC

## Fork Integration (XeStrata)
- IGC GEP simplification workaround (IGC_EnableGEPSimplification=0)
- Level Zero driver version checks
- Fedora 44 container approach for IGC compatibility
