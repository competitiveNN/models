# Models Export Tool

A Python tool for exporting AI/ML models to OpenVINO format with optimized quantization and calibration options.

## Overview

This project provides a streamlined interface for converting Hugging Face models to OpenVINO format using Intel's Optimum library. It supports both fast baseline exports and slower calibrated exports with scale estimation for potentially better performance and accuracy.

## Features

- **Dual Export Modes**: Fast baseline export vs. calibrated export with scale estimation
- **Automatic Task Detection**: Intelligently detects model tasks from model names
- **Memory-Aware Batch Calculation**: Auto-calculates optimal batch sizes and sequence lengths based on target RAM
- **Multiple Weight Formats**: Support for int4, int8, fp16, and fp32 quantization
- **Intel Optimizations**: Built with Intel Extension for PyTorch and OpenVINO optimizations

## Requirements

- Python 3.11+
- Linux/macOS/Windows
- Sufficient RAM for model conversion (configurable target)

## Installation

1. **Clone the repository and navigate to the project directory:**
   ```bash
   cd /path/to/models
   ```

2. **Install dependencies using uv (recommended):**
   ```bash
   uv sync
   ```

   Or using pip:
   ```bash
   pip install -e .
   ```

## Usage

### Basic Usage

```bash
# Fast export with default settings
./export.sh --fast meta-llama/Llama-3.2-1B-Instruct

# Calibrated export with custom output directory
./export.sh --slow --out ./my-model-export meta-llama/Llama-3.2-1B-Instruct
```

### Advanced Usage

```bash
# Export with specific weight format and memory constraints
./export.sh --slow --param-size int8 --target-ram 32 meta-llama/Llama-3.2-1B-Instruct

# Export with custom task specification
./export.sh --fast --task text2text-generation-with-past t5-small

# Memory-safe batch processing for large models
./export.sh --slow --batch --target-ram 64 meta-llama/Llama-2-70b-chat-hf
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
- `--batch`: Enable OOM-safe batch processing with conservative defaults
- `--target-ram <GB>`: Target RAM limit for automatic batch calculation - default: 48GB
- `--batch-size <n>`: Manual batch size override (for memory estimation)
- `--sequence_length <n>`: Manual sequence length override (for memory estimation)

## Examples

### Text Generation Models
```bash
# Llama model with int4 quantization
./export.sh --fast meta-llama/Llama-3.2-1B-Instruct

# GPT model with calibrated export
./export.sh --slow microsoft/DialoGPT-medium
```

### Text-to-Text Models
```bash
# T5 model
./export.sh --fast t5-small

# BART model with custom output
./export.sh --slow --out ./bart-cnn-ov facebook/bart-large-cnn
```

### Speech Recognition Models
```bash
# Whisper model (auto-detected as speech recognition)
./export.sh --slow openai/whisper-tiny
```

### Diffusion Models
```bash
# Stable Diffusion (auto-detected as text-to-image)
./export.sh --fast runwayml/stable-diffusion-v1-5
```

## Memory Management

The tool includes intelligent memory management features:

- **Automatic RAM Detection**: Calculates optimal batch sizes and sequence lengths based on available RAM
- **Conservative Defaults**: Uses safe defaults when `--batch` flag is specified
- **Memory Estimation**: Provides RAM usage estimates before export
- **OOM Prevention**: Helps prevent out-of-memory errors during calibration

## Supported Model Types

The tool automatically detects model types from names and applies appropriate configurations:

- **Text Generation**: Llama, GPT, OPT, etc.
- **Text-to-Text**: T5, BART, mBART
- **Speech Recognition**: Whisper models
- **Text-to-Image**: Stable Diffusion, SDXL

## Dependencies

- `auto-round >= 0.9.7`: Model quantization and rounding
- `intel-extension-for-pytorch >= 2.5`: Intel PyTorch optimizations
- `optimum[openvino] >= 2.1.0`: Hugging Face Optimum with OpenVINO support
- `torch < 2.9`: PyTorch framework

## Output

Exports create OpenVINO Intermediate Representation (IR) files in the specified output directory:
- `openvino_model.xml`: Model structure
- `openvino_model.bin`: Model weights
- Additional metadata files

## Troubleshooting

### Common Issues

1. **Out of Memory**: Use `--batch` flag or reduce `--target-ram`
2. **Model Not Found**: Ensure model name is correct and accessible
3. **Task Detection Issues**: Specify `--task` manually if auto-detection fails

### Performance Tips

- Use `--fast` mode for quick exports
- Use `--slow` mode for production deployments where quality matters
- Adjust `--target-ram` based on your system's available memory
- For large models, consider using `--batch` mode

## License

This project is part of the broader AI model optimization toolkit.