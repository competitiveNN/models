# Qwen3.8 Flash-Next Q3_XXS Best Configurations & Setup Guide

This document outlines the optimal configurations for running **Qwen3.8 Flash-Next Q3_XXS** on Intel Arc B580 (Battlemage) dual-GPU setups with Tensor Parallelism (`TP=2`) and single-GPU setups.

## Overview of Model & Hardware
- **Model**: Swift-Qwen3.8-Flash-Next-GSQ-RCO-IQ3_XXS (split across two shards)
- **Hardware**: Dual Intel Arc B580 GPUs (`level_zero:0`, `level_zero:1`)
- **Backend**: SYCL / Level Zero direct engine (`strata-sycl-direct.sh`)

---

## Recommended Configuration Files

### 1. Dual-GPU TP=2 Clean Standard (`configs/strata-swift-iq3_xxs-2gpu-clean.json`)
The primary production configuration for dual Intel Arc B580 GPUs.
- **Port**: `8081`
- **Context Size**: `262144`
- **KV Cache**: `int8`
- **Expert Cache**: `1024`
- **Pipeline Windows**: `2`
- **Device Selector**: `level_zero:0;level_zero:1`

### 2. Single-GPU TDR-Safe (`configs/tdr-safe-1gpu-fixed.json`)
The fallback configuration for single Intel Arc B580 operation with timeout-safe settings.
- **Port**: `8082`
- **Device Selector**: `level_zero:0`

---

## Launcher Usage (`strata-launch.sh`)
To launch the optimized dual-GPU server:
```bash
./strata-launch.sh --2gpu --image edge
```

To launch the single-GPU server:
```bash
./strata-launch.sh --1gpu --image dev
```
