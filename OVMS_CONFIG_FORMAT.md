# OpenVINO Model Server Configuration Format

## Correct JSON Structure

### For LLMs (MediaPipe Graphs)

```json
{
  "model_config_list": [
    {
      "config": {
        "name": "model-name_model",
        "base_path": "/path/to/model"
      }
    }
  ],
  "mediapipe_config_list": [
    {
      "name": "model-name",
      "graph_path": "/path/to/model/graph.pbtxt"
    }
  ]
}
```

### For Regular Models

```json
{
  "model_config_list": [
    {
      "config": {
        "name": "model-name",
        "base_path": "/path/to/model"
      }
    }
  ]
}
```

## Key Points

1. **LLMs require MediaPipe graphs**: Use `mediapipe_config_list` (NOT `graph_config_list`)
2. **Configuration structure:**
   - `model_config_list`: Contains the model definition (name: `{graph_name}_model`)
   - `mediapipe_config_list`: Contains the graph/pipeline definition (name: `{graph_name}`)
   - The model is linked to the graph by naming convention: graph name + `_model` suffix.
3. **Model naming convention**: LLM models should have `_model` suffix, graph uses the base name.
4. **No graph_variables needed**: The model is linked by naming convention (graph_name + `_model`).
5. **target_device is optional**: If omitted, OVMS defaults to CPU or uses the device specified in the graph `.pbtxt`.

## Common Errors

❌ **Wrong**: `graph_config_list` (this key doesn't exist)
✅ **Correct**: `mediapipe_config_list`

❌ **Wrong**: `"graph_name": "model-name"` in mediapipe config
✅ **Correct**: `"name": "model-name"` in mediapipe config

❌ **Wrong**: Including `graph_variables` section
✅ **Correct**: Omit `graph_variables`, use naming convention instead

### When using the `--llm` flag, the script creates:
1. A model configuration with `_model` suffix
2. A MediaPipe configuration that references the model by naming convention
