# Models Export Tool

A Python tool for exporting AI/ML models to OpenVINO format with optimized quantization and calibration options.

## Overview

This project provides a streamlined interface for converting Hugging Face models to OpenVINO format using Intel's Optimum library. It exports models with optimized static shapes for maximum performance and memory efficiency.

## Features

- **Static Shape Export**: Optimized exports with fixed shapes for maximum performance
- **Dual Export Modes**: Fast baseline vs. calibrated export with scale estimation
- **Automatic Task Detection**: Intelligently detects model tasks from model names
- **Multiple Weight Formats**: Support for int4, int8, fp16, and fp32 quantization
- **Memory Optimization**: Low CPU memory usage and half-precision loading
- **OpenVINO Export**: Optimized for Intel's OpenVINO inference engine

## Requirements

- Python 3.11+
- Linux/macOS/Windows
- Sufficient RAM for model conversion (configurable target)

## Installation

1. **Clone the repository and navigate to the project directory:**
   ```bash
   cd /path/to/models
   ```

2. **Install dependencies (optional for basic functionality):**
   ```bash
   uv sync  # Recommended
   ```
   Or:
   ```bash
   pip install -e .
   ```

   **Note**: Basic export functionality works without installing dependencies (falls back to CLI mode).

## Files

- `export.py`: Main export script
- `pyproject.toml`: Python project configuration
- `README.md`: This documentation

## Usage

### Basic Usage

```bash
# Fast export with default settings (static shapes, int4 quantization)
./export.py --fast meta-llama/Llama-3.2-1B-Instruct

# Calibrated export with custom output directory
./export.py --slow --out ./my-model-export meta-llama/Llama-3.2-1B-Instruct
```

### Advanced Usage

```bash
# Export with specific weight format
./export.py --slow --param-size int8 meta-llama/Llama-3.2-1B-Instruct

# Export with custom task specification
./export.py --fast --task text2text-generation-with-past t5-small

# Export large models with minimal memory usage
./export.py --fast --low-memory meta-llama/Llama-2-70b-chat-hf

# Disable low CPU memory usage
./export.py --fast --no-low-cpu-mem-usage meta-llama/Llama-3.2-1B-Instruct

# Model loading options
./export.py --fast --cache-dir /tmp/models --revision main meta-llama/Llama-3.2-1B-Instruct

# Conservative memory settings for large models
./export.py --slow --low-memory meta-llama/Llama-2-70b-chat-hf
```

## Command Line Options

### Required Arguments
- `<model>`: Hugging Face model name or local path

### Export Modes (choose one)
- `--fast`: Baseline export (faster)
- `--slow`: Calibrated export with scale estimation using WikiText-2 dataset (slower but potentially better quality)

### Optional Arguments
- `--task <task>`: Override auto-detected task (e.g., `text-generation-with-past`, `text2text-generation-with-past`, `automatic-speech-recognition-with-past`, `text-to-image`)
- `--param-size <size>`: Weight format (`int4`, `int8`, `fp16`, `fp32`) - default: `int4`
- `--out <directory>`: Output directory - default: `<model-name>-<param-size>[-awq]-ov`
- `--low-memory`: Use most conservative memory settings for large models (forces static shapes, small batch/sequence)
- `--no-low-cpu-mem-usage`: Disable low CPU memory usage mode (enabled by default for static shapes)
- `--cache-dir <dir>`: Directory to cache downloaded models
- `--revision <rev>`: Specific model revision to load
- `--token <token>`: Authentication token for remote models

## Examples

### Text Generation Models
```bash
# Llama model with int4 quantization
./export.py --fast meta-llama/Llama-3.2-1B-Instruct

# GPT model with calibrated export
./export.py --slow microsoft/DialoGPT-medium
```

### Text-to-Text Models
```bash
# T5 model
./export.py --fast t5-small

# BART model with custom output
./export.py --slow --out ./bart-cnn-ov facebook/bart-large-cnn
```

### Speech Recognition Models
```bash
# Whisper model (auto-detected as speech recognition)
./export.py --slow openai/whisper-tiny
```

### Diffusion Models
```bash
# Stable Diffusion (auto-detected as text-to-image)
./export.py --fast runwayml/stable-diffusion-v1-5
```

## Memory Management

The tool uses optimized memory management for static shape exports:

- **Low CPU Memory Usage**: Reduces memory consumption during model loading (enabled by default)
- **Half-Precision Loading**: Uses FP16 when PyTorch is available for memory efficiency
- **Conservative Shapes**: `--low-memory` flag uses smaller fixed shapes for large models
- **Quantization Support**: All weight formats (int4, int8, fp16, fp32) supported

## Static vs Dynamic Shapes

By default, exported models use **dynamic shapes** which allow flexible batch sizes and sequence lengths at inference time.

- **Dynamic Shapes** (default): Flexible inference with any batch size/sequence length, but slightly slower first inference
- **Static Shapes** (`--static-shapes`): Fixed shapes (batch_size=1, sequence_length=512) for optimized performance with low CPU memory usage, faster inference but fixed dimensions

**Note**: Static shapes work with both `--fast` and `--slow` modes and support all weight formats (int4, int8, fp16, fp32). For `--slow` mode, scale estimation (calibration) with static shapes is not yet supported in the Python API, so it falls back to static shapes without calibration. Static shapes automatically enable multiple memory optimizations including low CPU memory usage and half-precision loading when available.

## Supported Model Types

The tool automatically detects model types from names and applies appropriate configurations:

- **Text Generation**: Llama, GPT, OPT, etc.
- **Text-to-Text**: T5, BART, mBART
- **Speech Recognition**: Whisper models
- **Text-to-Image**: Stable Diffusion, SDXL

## Dependencies

**Core Requirements:**
- Python 3.11+
- `optimum[openvino]` (for static shapes export, with fallback to CLI)

**Optional Dependencies:**
- PyTorch (for memory optimizations)
- Intel Extension for PyTorch (for additional optimizations)

**Note**: The script includes graceful fallbacks and can run basic export functionality without optional dependencies installed.

## Output

Exports create OpenVINO Intermediate Representation (IR) files in the specified output directory:
- `openvino_model.xml`: Model structure
- `openvino_model.bin`: Model weights
- Additional metadata files

## Troubleshooting

### Common Issues

1. **Out of Memory**: Use `--low-memory` flag for large models
2. **Model Not Found**: Ensure model name is correct and accessible
3. **Task Detection Issues**: Specify `--task` manually if auto-detection fails
4. **Missing Optimum**: Install `optimum[openvino]` for export functionality

### Performance Tips

- Use `--fast` mode for quick exports
- Use `--slow` mode for production deployments where quality matters
- Use `--low-memory` for large models to reduce memory usage
- All exports use optimized static shapes for maximum performance

## License

This project is part of the broader AI model optimization toolkit.