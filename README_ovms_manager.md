# OpenVINO Model Server Configuration Manager

A Python script to manage OpenVINO Model Server (OVMS) configuration files and reload configurations via the REST API. Supports both regular models and LLM graphs (MediaPipe pipelines).

## Features

- **Add models** by path with automatic name extraction or custom naming
- **Add LLM graphs** as MediaPipe pipelines for Large Language Models
- **Remove models/graphs** by name
- **List all configured items** with details (path, device, type)
- **Reload configuration** via OVMS REST API
- **Check server status** and loaded models
- **Validation** of model paths and duplicate names
- **Optional device targeting** (GPU/CPU/etc.)

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

# Reload configuration on the server
python ovms_manager.py reload

# Check server status
python ovms_manager.py status
```

### Advanced Options

```bash
# Use custom config file and server URL
python ovms_manager.py --config /path/to/config.json --server http://localhost:9000 list
```

### Command Reference

| Command | Description | Options |
|---------|-------------|---------|
| `add <path>` | Add model/graph to configuration | `--name`, `--device`, `--llm` |
| `remove <name>` | Remove model/graph by name | None |
| `list` | List all configured models and graphs | None |
| `reload` | Reload server configuration | None |
| `status` | Check server status | None |

### Global Options

| Option | Description | Default |
|--------|-------------|---------|
| `--config`, `-c` | Configuration file path | `ovms_config.json` |
| `--server`, `-s` | OVMS server URL | `http://localhost:8000` |

## Configuration Format

The script manages JSON configuration files in the OVMS format:

### Regular Model
```json
{
  "model_config_list": [
    {
      "config": {
        "name": "model-name",
        "base_path": "/path/to/model",
        "target_device": "GPU",
        "plugin_config": {
          "PERFORMANCE_HINT": "LATENCY"
        }
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
        "base_path": "/path/to/llm",
        "target_device": "GPU",
        "plugin_config": {
          "PERFORMANCE_HINT": "LATENCY"
        }
      }
    }
  ],
  "mediapipe_config_list": [
    {
      "name": "llm-name",
      "graph_path": "/models/ov/server/graph.pbtxt"
    }
  ]
}
```

## API Integration

The script uses the OVMS REST API for configuration reloading:

- **Reload endpoint**: `POST /v1/config/reload`
- **Status endpoint**: `GET /v1/config`

## Requirements

- Python 3.11+
- `requests` library
- Running OpenVINO Model Server (for reload/status commands)

## Error Handling

- **Path validation**: Warns if model paths don't exist
- **Duplicate detection**: Prevents adding models with existing names
- **Server connectivity**: Graceful handling of connection errors
- **JSON validation**: Validates configuration file format

## Examples

### Typical Workflow

```bash
# Start with listing current models and graphs
python ovms_manager.py list

# Add a new LLM as a graph
python ovms_manager.py add /models/ov/mistral/Ministral-3b-instruct-openvino --name ministral --llm

# Add a regular model
python ovms_manager.py add /models/ov/vision/yolo-v8 --name yolo

# Reload the server configuration
python ovms_manager.py reload

# Check that the models are loaded
python ovms_manager.py status

# Remove a model when no longer needed
python ovms_manager.py remove ministral
python ovms_manager.py reload
```

### Batch Operations

```bash
# Add multiple models and LLMs
python ovms_manager.py add /models/ov/llama/7b --name llama-7b --llm
python ovms_manager.py add /models/ov/llama/13b --name llama-13b --device CPU --llm
python ovms_manager.py add /models/ov/vision/resnet --name resnet

# Reload once after all additions
python ovms_manager.py reload
```

## LLM Graph Support

When using the `--llm` flag, the script creates:
1. A model configuration with `_model` suffix
2. A MediaPipe configuration that references the model by naming convention
3. Uses the default graph path: `/models/ov/server/graph.pbtxt`

This is required for Large Language Models in OpenVINO Model Server as they need to be served as MediaPipe graphs rather than regular models.

**Configuration structure:**
- `model_config_list`: Contains the model definition (name: `{graph_name}_model`)
- `mediapipe_config_list`: Contains the graph/pipeline definition (name: `{graph_name}`)
- The model is linked to the graph by naming convention: graph name + `_model` suffix.