# Intel Arc B580 — Specifications

> Distilled from the TechPowerUp GPU Database page for the [Intel Arc B580](https://www.techpowerup.com/gpu-specs/arc-b580.c4244).
> Source file `docs/b580_specs.html` was removed after distillation; this markdown is the reference copy.

## Overview

The Arc B580 is a performance-segment graphics card by Intel, launched on December 13th, 2024. It is built on the 5 nm process and based on the BMG-G21 graphics processor in its SRPMF variant, supporting DirectX 12 Ultimate (hardware ray tracing, variable-rate shading and more). The BMG-G21 is an average-sized die of 272 mm² with 19.6 billion transistors: 2560 shading units, 160 TMUs, 80 ROPs, 160 XMX cores (INT2/INT4/INT8 machine-learning acceleration) and 20 ray-tracing cores. It ships with 12 GB GDDR6 on a 192-bit bus, is a dual-slot card drawing power through a single 8-pin connector at 190 W, and connects via PCIe 4.0 x8.

**Launch price:** 249 USD

**Recommended gaming resolutions:** 1920x1080 (Good), 2560x1440 (Playable), 3840x2160 (Low FPS)

## Key Specifications

| Specification | Value |
|---|---|
| Graphics Processor | BMG-G21 |
| Architecture | Xe2-HPG |
| Process | 5 nm (TSMC) |
| Transistors | 19.6 billion |
| Die Size | 272 mm² |
| Cores | 2560 |
| TMUs | 160 |
| ROPs | 80 |
| XMX Cores | 160 |
| RT Cores | 20 |
| L2 Cache | 18 MB |
| Memory Size | 12 GB |
| Memory Type | GDDR6 |
| Memory Bus | 192 bit |
| Bandwidth | 456.0 GB/s |
| Base Clock | 2670 MHz |
| Boost Clock | 2670 MHz |
| Memory Clock | 2375 MHz / 19 Gbps effective |
| TDP | 190 W |
| Suggested PSU | 450 W |
| Bus Interface | PCIe 4.0 x8 |
| Outputs | 1x HDMI 2.1a / 3x DisplayPort 2.1 |
| Form Factor | Dual-slot, 272 mm / 10.7 inches |
| Launch Price | 249 USD |

## Specifications by Section

### Graphics Processor

| Item | Value |
|---|---|
| GPU Name | BMG-G21 |
| GPU Variant | SRPMF |
| Architecture | Xe2-HPG |
| Generation | 20.1 |
| Foundry | TSMC |
| Process Size | 5 nm |
| Transistors | 19.6 billion |
| Density | 72.1M / mm² |
| Die Size | 272 mm² |
| Chip Package | FCBGA-2362 |
| Package Size | 41.5 mm × 34 mm |

### Graphics Card

| Item | Value |
|---|---|
| Release Date | Dec 13th, 2024 |
| Announced | Dec 3rd, 2024 |
| Generation | Battlemage (Arc 5) |
| Predecessor | Alchemist |
| Production | Active |
| Driver Support | Active |
| Launch Price | 249 USD |
| Bus Interface | PCIe 4.0 x8 |
| Reviews | 20 in our database |

### Clock Speeds

| Item | Value |
|---|---|
| Base Clock | 2670 MHz |
| Boost Clock | 2670 MHz |
| Memory Clock | 2375 MHz / 19 Gbps effective |

### Memory

| Item | Value |
|---|---|
| Memory Size | 12 GB |
| Memory Type | GDDR6 |
| Memory Bus | 192 bit |
| Bandwidth | 456.0 GB/s |

### Render Config

| Item | Value |
|---|---|
| Shading Units | 2560 |
| TMUs | 160 |
| ROPs | 80 |
| Execution Units | 20 |
| XMX Cores | 160 |
| RT Cores | 20 |
| L1 Cache | 256 KB (per EU) |
| L2 Cache | 18 MB |

### Theoretical Performance

| Item | Value |
|---|---|
| Pixel Rate | 213.6 GPixel/s |
| Texture Rate | 427.2 GTexel/s |
| FP16 | 27.34 TFLOPS (2:1) |
| FP32 | 13.67 TFLOPS |
| FP64 | 854.4 GFLOPS (1:16) |

### Matrix Performance

| Item | Value |
|---|---|
| INT2 | 437.5 TOPS |
| INT4 | 437.5 TOPS |
| INT8 | 218.7 TOPS |
| FP16 | 109.4 TFLOPS |
| BF16 | 109.4 TFLOPS |
| TF32 | 54.68 TFLOPS |

### Numeric Format Support

| Item | Value |
|---|---|
| Vector | INT4 INT8 INT16 INT32 FP16 BF16 FP32 FP64 |
| Matrix | INT1 INT2 INT4 INT8 MXFP4 NVFP4 MXFP6 FP8 MXFP8 FP16 BF16 FP32 TF32 FP64 |

### Board Design

| Item | Value |
|---|---|
| Slot Width | Dual-slot |
| Length | 272 mm / 10.7 inches |
| Height | 115 mm / 4.5 inches |
| Width | 45 mm / 1.8 inches |
| TDP | 190 W |
| Suggested PSU | 450 W |
| Outputs | 1x HDMI 2.1a / 3x DisplayPort 2.1 |
| Power Connectors | 1x 8-pin |

### Graphics Features

| Item | Value |
|---|---|
| DirectX | 12 Ultimate (12_2) |
| OpenGL | 4.6 |
| OpenCL | 3.0 |
| Vulkan | 1.4 |
| Shader Model | 6.9 |

### BMG-G21 GPU Notes

- Super Resolution: XeSS 3, FSR 3.1.5
- Frame Generation: XeSS 3 (4×), FSR 3.1.6
- Ray Regeneration: No Support
- Xe-Cores: 2nd Gen
- Ray Tracing Units: 2nd Gen
- XMX Engines: 2nd Gen

## Retail Boards Based on This Design

13 boards share the BMG-G21 design. All run the stock 2670 MHz GPU clock and 2375 MHz memory clock; differences are boost clock, length, and (for SPARKLE) power limit.

| Name | GPU Clock | Boost Clock | Memory Clock | Other Changes |
|---|---|---|---|---|
| Acer Nitro Arc B580 | 2670 MHz | 2740 MHz | 2375 MHz | 268 mm/10.6 inches |
| ASRock Arc B580 Challenger OC | 2670 MHz | 2740 MHz | 2375 MHz | 249 mm/9.8 inches |
| ASRock Arc B580 Steel Legend OC | 2670 MHz | 2800 MHz | 2375 MHz | 298 mm/11.7 inches |
| GUNNIR Arc B580 Index | 2670 MHz | 2670 MHz | 2375 MHz | 244 mm/9.6 inches |
| GUNNIR Arc B580 Photon OC | 2670 MHz | 2850 MHz | 2375 MHz | 300 mm/11.8 inches |
| GUNNIR Arc B580 Photon OC W | 2670 MHz | 2850 MHz | 2375 MHz | 300 mm/11.8 inches |
| MAXSUN Arc B580 iCraft | 2670 MHz | 2850 MHz | 2375 MHz | 315 mm/12.4 inches |
| MAXSUN Arc B580 Milestone | 2670 MHz | 2850 MHz | 2375 MHz | 241 mm/9.5 inches |
| ONIX Lumi Arc B580 OC | 2670 MHz | 2740 MHz | 2375 MHz |  |
| ONIX Odyssey Arc B580 OC | 2670 MHz | 2740 MHz | 2375 MHz |  |
| SPARKLE Arc B580 GUARDIAN | 2670 MHz | 2670 MHz | 2375 MHz | 242 mm/9.5 inches, 200 W |
| SPARKLE Arc B580 TITAN Luna OC | 2670 MHz | 2740 MHz | 2375 MHz | 315 mm/12.4 inches, 200 W |
| SPARKLE Arc B580 TITAN OC | 2670 MHz | 2740 MHz | 2375 MHz | 315 mm/12.4 inches, 200 W |

## Relative Performance

Performance index for 176 GPUs, relative to the Arc B580 (the highlighted 100% entry). Derived from TPU review data ("Performance Summary" at 1920x1080; 4K for RTX 3080 and faster). "Bar Width" is the graph scaling used on the source page.

| GPU | Relative Performance | Bar Width |
|---|---|---|
| GeForce RTX 5090 | 410% | 100.00% |
| GeForce RTX 4090 | 313% | 76.27% |
| GeForce RTX 5080 | 270% | 65.90% |
| GeForce RTX 4080 SUPER | 241% | 58.84% |
| GeForce RTX 4080 | 239% | 58.34% |
| Radeon RX 7900 XTX | 239% | 58.30% |
| GeForce RTX 5070 Ti | 236% | 57.46% |
| Radeon RX 9070 XT | 225% | 54.91% |
| Radeon RX 7900 XT | 206% | 50.20% |
| GeForce RTX 3090 Ti | 202% | 49.29% |
| GeForce RTX 4070 Ti SUPER | 202% | 49.24% |
| Radeon RX 9070 | 202% | 49.19% |
| GeForce RTX 4070 Ti | 185% | 45.07% |
| GeForce RTX 5070 | 183% | 44.62% |
| GeForce RTX 3090 | 180% | 43.96% |
| GeForce RTX 3080 Ti | 178% | 43.38% |
| GeForce RTX 4070 SUPER | 172% | 41.99% |
| Radeon RX 7900 GRE | 170% | 41.35% |
| Radeon RX 9070 GRE | 168% | 40.94% |
| Radeon RX 6950 XT | 167% | 40.67% |
| GeForce RTX 4070 | 165% | 40.11% |
| Radeon RX 6900 XT | 163% | 39.71% |
| GeForce RTX 3080 | 160% | 39.08% |
| Radeon RX 7800 XT | 160% | 38.96% |
| Radeon RX 6800 XT | 154% | 37.59% |
| GeForce RTX 5060 Ti 16 GB | 143% | 34.89% |
| GeForce RTX 5060 Ti 8 GB | 142% | 34.68% |
| Radeon RX 7700 XT | 140% | 34.16% |
| Radeon RX 9060 XT 16 GB | 136% | 33.12% |
| GeForce RTX 3070 Ti | 136% | 33.06% |
| Radeon RX 6800 | 131% | 31.95% |
| Radeon RX 9060 XT 8 GB | 128% | 31.26% |
| GeForce RTX 3070 | 127% | 30.93% |
| GeForce RTX 2080 Ti | 126% | 30.67% |
| GeForce RTX 4060 Ti 8 GB | 125% | 30.53% |
| GeForce RTX 5060 | 123% | 30.06% |
| Radeon RX 6750 XT | 120% | 29.32% |
| GeForce RTX 3060 Ti | 111% | 27.07% |
| Radeon RX 6700 XT | 109% | 26.59% |
| GeForce RTX 2080 SUPER | 101% | 24.71% |
| Radeon RX 7600 XT | 100% | 24.49% |
| GeForce RTX 4060 | 100% | 24.42% |
| **Arc B580** | 100% | 24.38% |
| GeForce RTX 5050 | 97% | 23.75% |
| GeForce RTX 2080 | 97% | 23.57% |
| Radeon RX 6650 XT | 95% | 23.05% |
| Radeon RX 7600 | 94% | 23.02% |
| GeForce RTX 2070 SUPER | 90% | 21.91% |
| GeForce GTX 1080 Ti | 89% | 21.68% |
| Arc A770 | 89% | 21.65% |
| GeForce RTX 3060 12 GB | 86% | 20.87% |
| Radeon RX 6600 XT | 84% | 20.57% |
| Radeon VII | 84% | 20.51% |
| Arc A750 | 82% | 20.10% |
| Steam Machine GPU | 81% | 19.68% |
| Radeon RX 5700 XT | 81% | 19.65% |
| GeForce RTX 2070 | 79% | 19.36% |
| Radeon RX 6600 | 76% | 18.49% |
| Arc A580 | 74% | 17.96% |
| GeForce RTX 2060 SUPER | 74% | 17.94% |
| Radeon RX Vega 64 | 70% | 17.17% |
| GeForce RTX 2060 | 68% | 16.62% |
| Radeon RX 5700 | 68% | 16.54% |
| GeForce GTX 1080 | 67% | 16.23% |
| GeForce GTX 1070 Ti | 65% | 15.92% |
| Radeon RX 5600 XT | 65% | 15.78% |
| Radeon RX Vega 56 | 62% | 14.99% |
| GeForce GTX 1070 | 59% | 14.45% |
| GeForce GTX 1660 SUPER | 56% | 13.68% |
| GeForce GTX 1660 Ti | 56% | 13.67% |
| GeForce GTX 980 Ti | 53% | 12.95% |
| GeForce RTX 3050 8 GB | 53% | 12.88% |
| Radeon R9 FURY X | 52% | 12.73% |
| GeForce GTX 1660 | 52% | 12.59% |
| Radeon RX 590 | 49% | 11.89% |
| Radeon R9 FURY | 48% | 11.59% |
| GeForce GTX 980 | 47% | 11.44% |
| GeForce GTX 1650 SUPER | 46% | 11.33% |
| Radeon RX 6500 XT | 46% | 11.19% |
| Radeon RX 5500 XT | 46% | 11.09% |
| Radeon RX 580 | 45% | 11.01% |
| GeForce GTX 1060 6 GB | 44% | 10.73% |
| Radeon R9 390X | 43% | 10.57% |
| GeForce GTX 690 | 43% | 10.45% |
| Radeon RX 480 | 42% | 10.36% |
| Radeon HD 7990 | 42% | 10.31% |
| GeForce GTX 780 Ti | 42% | 10.12% |
| GeForce GTX 970 | 40% | 9.86% |
| Radeon R9 290X | 40% | 9.83% |
| Radeon R9 390 | 40% | 9.67% |
| Radeon RX 570 | 39% | 9.55% |
| Radeon R9 290 | 37% | 9.07% |
| Radeon RX 470 | 37% | 8.94% |
| GeForce GTX 1650 | 35% | 8.42% |
| Radeon RX 6400 | 34% | 8.25% |
| Arc A380 | 33% | 8.14% |
| GeForce GTX 780 | 33% | 8.13% |
| Radeon HD 7970 GHz Edition | 30% | 7.34% |
| GeForce GTX 590 | 30% | 7.33% |
| Radeon R9 280X | 30% | 7.23% |
| Radeon HD 6990 | 29% | 7.06% |
| GeForce GTX 1050 Ti | 28% | 6.72% |
| GeForce GTX 680 | 27% | 6.57% |
| Radeon R9 380 | 27% | 6.50% |
| Radeon HD 7970 | 27% | 6.50% |
| GeForce GTX 770 | 27% | 6.49% |
| Radeon R9 285 | 26% | 6.44% |
| GeForce GTX 960 | 26% | 6.24% |
| GeForce GTX 670 | 25% | 6.08% |
| Radeon HD 5970 | 23% | 5.50% |
| GeForce GTX 1630 | 23% | 5.49% |
| Radeon HD 7950 | 22% | 5.39% |
| GeForce GTX 1050 | 22% | 5.38% |
| GeForce GTX 760 | 22% | 5.34% |
| GeForce GTX 580 | 22% | 5.34% |
| GeForce GTX 660 Ti | 22% | 5.31% |
| Radeon R9 270X | 22% | 5.25% |
| Radeon HD 7870 GHz Edition | 21% | 5.12% |
| GeForce GTX 950 | 21% | 5.08% |
| Radeon RX 560 | 20% | 4.78% |
| GeForce GTX 570 | 19% | 4.70% |
| GeForce GTX 660 | 19% | 4.69% |
| Radeon RX 460 | 19% | 4.67% |
| Radeon R7 370 | 19% | 4.67% |
| Radeon HD 6970 | 19% | 4.51% |
| GeForce GTX 480 | 18% | 4.31% |
| Radeon HD 7850 | 17% | 4.24% |
| GeForce GTX 295 | 17% | 4.16% |
| Radeon HD 6950 | 16% | 4.02% |
| GeForce GTX 750 Ti | 16% | 4.00% |
| Radeon HD 4870 X2 | 16% | 3.93% |
| GeForce GTX 560 Ti | 16% | 3.91% |
| Radeon HD 5870 | 16% | 3.79% |
| Radeon HD 6870 | 15% | 3.55% |
| GeForce GTX 470 | 14% | 3.42% |
| GeForce GTX 650 Ti | 13% | 3.28% |
| Radeon HD 5850 | 13% | 3.22% |
| GeForce GTX 285 | 12% | 3.00% |
| Radeon HD 6850 | 12% | 2.94% |
| GeForce GTX 280 | 11% | 2.76% |
| Radeon HD 7770 GHz Edition | 11% | 2.75% |
| GeForce GTX 275 | 11% | 2.74% |
| GeForce GT 1030 | 11% | 2.72% |
| GeForce GTX 460 | 11% | 2.67% |
| Radeon HD 4890 | 11% | 2.57% |
| Radeon HD 6790 | 10% | 2.53% |
| Radeon HD 5830 | 10% | 2.41% |
| GeForce GTX 650 | 9% | 2.28% |
| GeForce GTX 550 Ti | 9% | 2.26% |
| Radeon HD 4870 | 9% | 2.23% |
| GeForce GTX 260 | 9% | 2.20% |
| Radeon HD 5770 | 9% | 2.16% |
| Radeon HD 7750 | 9% | 2.15% |
| Radeon HD 5750 | 8% | 1.88% |
| GeForce GTS 450 | 7% | 1.82% |
| GeForce GTS 250 | 7% | 1.76% |
| Radeon HD 4850 | 7% | 1.72% |
| Radeon HD 4770 | 7% | 1.63% |
| Radeon HD 4830 | 6% | 1.53% |
| Radeon HD 6670 | 6% | 1.48% |
| GeForce 9800 GT | 6% | 1.43% |
| GeForce GT 640 | 6% | 1.38% |
| Radeon HD 5670 | 5% | 1.29% |
| GeForce 9600 GT | 5% | 1.21% |
| GeForce GT 240 | 4% | 1.06% |
| GeForce GT 440 | 4% | 1.03% |
| Radeon HD 4670 | 4% | 0.98% |
| Radeon HD 5570 | 4% | 0.90% |
| GeForce GT 430 | 4% | 0.89% |
| GeForce GT 220 | 3% | 0.68% |
| GeForce GT 520 | 2% | 0.55% |
| Radeon HD 6450 | 2% | 0.52% |
| Radeon HD 5450 | 2% | 0.44% |
| Radeon HD 4550 | 1% | 0.35% |
| GeForce 9400 GT | 1% | 0.28% |
| GeForce 210 | 1% | 0.22% |

## Images

- **Front**: https://tpucdn.com/gpu-specs/images-new/c/4244-front-large.jpg
- **GPU Chip**: https://tpucdn.com/gpu-specs/images-new/g/1085-default-large.jpg
- **Top**: https://tpucdn.com/gpu-specs/images-new/c/4244-top-large.jpg
- **Bottom**: https://tpucdn.com/gpu-specs/images-new/c/4244-bottom-large.jpg
- **Back**: https://tpucdn.com/gpu-specs/images-new/c/4244-back-large.jpg
- **PCB Front**: https://tpucdn.com/gpu-specs/images-new/c/4244-pcb-front-large.jpg
- **PCB Back**: https://tpucdn.com/gpu-specs/images-new/c/4244-pcb-back-large.jpg

