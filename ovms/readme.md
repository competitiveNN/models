# OpenVINO Model Server Configuration Manager

A Python script to manage OpenVINO Model Server (OVMS) configuration files and reload configurations via the REST API. Supports both regular models and LLM graphs (MediaPipe pipelines).

## Features

- **Add models** by path with automatic name extraction or custom naming
- **Add LLM graphs** as MediaPipe pipelines with automatic `graph.pbtxt` generation and customization
- **Remove models/graphs** by name
- **Clear all models** with a single command
- **List all configured items** with details (path, device, type)
- **Reload configuration** via OVMS REST API
- **Check server status** and loaded models
- **Validation** of model paths and duplicate names
- **Optional device targeting** (GPU/CPU/etc.)
- **Advanced LLM Configuration**:
    - **KV Cache Precision**: Configurable (e.g., `u8`, `f16`)
    - **Smart Cache Sizing**: Heuristic calculation based on GPU memory and model size
    - **Performance Tuning**: Configurable `NUM_STREAMS` and `PERFORMANCE_HINT`

## Usage

### Basic Commands

```bash
# List all configured models and graphs
python ovms_manager.py list

# Add a regular model (name extracted from path)
python ovms_manager.py add /models/ov/mistral/llama-2-7b-chat

# Add an LLM as a graph (MediaPipe pipeline)
python ovms_manager.py add /models/ov/mistral/ministral --name ministral --llm

# Add a model with custom name and CPU device
python ovms_manager.py add /models/ov/mistral/phi-3-mini --name phi3-mini --device CPU

# Remove a model or graph by name
python ovms_manager.py remove llama-2-7b-chat

# Clear all models and graphs (with confirmation)
python ovms_manager.py clear

# Reload configuration on the server
python ovms_manager.py reload

# Check server status
python ovms_manager.py status
```

### LLM Optimization Flags

When adding an LLM (`--llm`), you can fine-tune its performance:

```bash
# Set KV cache precision (default: u8)
python ovms_manager.py add /models/ov/llama-2-7b --llm --kv-cache-precision f16

# Set specific cache size in GB (default: heuristic calculation based on available GPU memory)
python ovms_manager.py add /models/ov/llama-2-7b --llm --cache-size 10

# Set performance hint (default: THROUGHPUT)
python ovms_manager.py add /models/ov/llama-2-7b --llm --performance-hint LATENCY

# Set inference precision hint (e.g. f32, f16, bf16). Default: f16
python ovms_manager.py add /models/ov/llama-2-7b --llm --inference-precision-hint f16

# Add a DFlash draft model for speculative decoding
python ovms_manager.py add /models/ov/llama-2-7b --llm \
    --draft-model-path /models/ov/z-lab/Qwen3.5-27B-DFlash --draft-device GPU.1
```

### Global Options

| Option | Description | Default |
|--------|-------------|---------|
| `--config`, `-c` | Configuration file path | `ovms_config.json` |
| `--server`, `-s` | OVMS server URL | `http://localhost:8000` |
| `--models-path`, `-m` | Host path where `/models` is mapped | `$MODELS_PATH` or `~/data/models` |

### Command Reference

| Command | Description | Options |
|---------|-------------|---------|
| `add <path>` | Add model/graph to configuration | `--name`, `--device`, `--llm`, `--pipeline-type`, `--kv-cache-precision`, `--cache-size`, `--performance-hint`, `--inference-precision-hint`, `--model-distribution-policy`, `--execution-mode-hint`, `--scheduling-core-type`, `--enable-cpu-pinning`, `--draft-model-path`, `--draft-device`, `--num-assistant-tokens` (supports DFlash, EAGLE3, MTP draft models) |
| `remove <name>` | Remove model/graph by name | None |
| `clear` | Remove all models and graphs | `--force` |
| `list` | List all configured models and graphs | None |
| `reload` | Reload server configuration | None |
| `status` | Check server status | None |

## LLM Graph Support

When using the `--llm` flag, the script performs several automated steps:

1.  **Unique Graph Generation**: Creates a unique `graph.pbtxt` for the model in its managed directory.
2.  **Path Resolution**: Updates the `models_path` in the graph to point to the correct location (handling symlinks).
3.  **Plugin Configuration**: Injects optimization parameters (`KV_CACHE_PRECISION`, `PERFORMANCE_HINT`, `INFERENCE_PRECISION_HINT`, `MODEL_DISTRIBUTION_POLICY`, `EXECUTION_MODE_HINT`, `SCHEDULING_CORE_TYPE`, `ENABLE_CPU_PINNING`) into the graph's `plugin_config`.
4.  **Configuration Entry**: Adds an entry to `mediapipe_config_list` pointing to the new unique graph.

**Heuristic Cache Sizing**:
If `--cache-size` is not provided and the target device is a GPU, the script uses `openvino` to detect the GPU's total memory. It then subtracts the estimated model size and a system overhead buffer (~1.5GB) to automatically set the optimal `cache_size`.

## Speculative Decoding (Draft Models)

The script supports adding **draft models** for speculative decoding (DFlash, EAGLE3, or MTP). When `--draft-model-path` is provided with `--llm`, the script:

1. Creates a managed symlink for the draft model under `./draft/1` inside the model's managed directory.
2. Writes `draft_models_path: "./draft"` and `draft_device` into the generated `graph.pbtxt`'s `LLMCalculatorOptions`, which is where OVMS reads draft configuration.
3. The main model config (`model_config_list`) remains clean — draft settings are **not** stored in the JSON config.

**Auto-detection:** The C++ server auto-detects the draft strategy from model artifacts:
- **DFlash**: `<dflash_mode value="1">` in `openvino_model.xml` `<rt_info>`
- **EAGLE3**: `<eagle3_mode value="1">` in `openvino_model.xml` `<rt_info>`
- **MTP**: presence of `openvino_mtp_model.xml` in the draft directory (takes priority)
- **Fast Draft**: no markers detected (classic two-model speculative decoding)

**Requirements:**
- DFlash/EAGLE3: OpenVINO-exported model with `--all-layers` (to output hidden states for KV injection). DFlash draft models from `z-lab` are available on HuggingFace (e.g. `z-lab/Qwen3.5-27B-DFlash`).
- MTP: Model must include the MTP prediction head exported as `openvino_mtp_model.xml` alongside the main model.

**Note:** `num_assistant_tokens` is a **request-time generation parameter** — set it via `generation_config.json` in the model directory or pass it per-request in the API body, not via `ovms_manager.py`.

```bash
# Add a model with a DFlash draft model
python ovms_manager.py add /models/ov/mistral/qwen3.5-27b --name qwen3.5-27b --llm \
    --pipeline-type LM_CB \
    --device GPU.1 \
    --draft-model-path /models/ov/z-lab/Qwen3.5-27B-DFlash \
    --draft-device GPU.1

# Add a model with an MTP draft head (auto-detected from openvino_mtp_model.xml)
python ovms_manager.py add /models/ov/llama-3.1-8b-mtp --name llama-mtp --llm \
    --draft-model-path /models/ov/llama-3.1-8b-mtp \
    --draft-device CPU
```

This generates a `graph.pbtxt` containing:
```
node_options: {
    [type.googleapis.com / mediapipe.LLMCalculatorOptions]: {
        models_path: "/models/ov/server/qwen3.5-27b/1",
        plugin_config: '{"KV_CACHE_PRECISION": "u8", ...}',
        cache_size: 0,
        device: "GPU.1",
        draft_models_path: "./draft",
        draft_device: "GPU.1",
    }
}
```

## Configuration Format

### Regular Model
```json
{
  "model_config_list": [
    {
      "config": {
        "name": "model-name",
        "base_path": "/models/ov/server/model-name",
        "target_device": "GPU"
      }
    }
  ]
}
```

### LLM Graph (MediaPipe Pipeline)
```json
{
  "model_config_list": [
    {
      "config": {
        "name": "llm-name_model",
        "base_path": "/models/ov/server/llm-name",
        "target_device": "GPU"
      }
    }
  ],
  "mediapipe_config_list": [
    {
      "name": "llm-name",
      "graph_path": "/models/ov/server/llm-name/graph.pbtxt"
    }
  ]
}
```

## MuseGlimmer-30B INT4 Model Directory Layout

The OpenVINO IR export for MuseGlimmer-30B INT4 should follow this structure:

```
Muse-Glimmer-30B-assistant-ov-int4/
├── model.xml
├── model.bin
└── (optional) generation_config.json
```

**Expected paths:**
- Verified INT4 model: `/var/home/fra/data/models/openvino/Muse-Glimmer-30B-assistant-ov-int4`
- FP32 model reference: `/var/home/fra/data/models/openvino/Muse-Glimmer-30B-assistant-ov`
- FP16 optimum model: `/var/home/fra/data/models/openvino/Muse-Glimmer-30B-assistant-ov-fp16-final`

**Configuration example:**
```json
{
  "model_config_list": [
    {
      "config": {
        "name": "muse-glimmer-30b-int4-ov_model",
        "base_path": "/var/home/fra/data/models/openvino/Muse-Glimmer-30B-assistant-ov-int4",
        "target_device": "CPU"
      }
    }
  ]
}
```

**Notes:**
- MuseGlimmer is a Vision-Language Model (VLM) with multimodal inputs. Ensure your serving client handles image/video tokens according to the model's expected prompt format.
- INT4 quantization reduces memory footprint but may require calibration data for optimal accuracy. The exported model at the path above is post-training quantized INT4.
