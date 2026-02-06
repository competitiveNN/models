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
      "graph_path": "/models/ov/server/graph.pbtxt"
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
2. **Graph name field**: Use `name` (NOT `graph_name`) in mediapipe_config_list
3. **Model naming convention**: LLM models should have `_model` suffix, graph uses the base name
4. **No graph_variables needed**: The model is linked by naming convention (graph_name + `_model`)

## Common Errors

❌ **Wrong**: `graph_config_list` (this key doesn't exist)
✅ **Correct**: `mediapipe_config_list`

❌ **Wrong**: `"graph_name": "model-name"` in mediapipe config
✅ **Correct**: `"name": "model-name"` in mediapipe config

❌ **Wrong**: Including `graph_variables` section
✅ **Correct**: Omit `graph_variables`, use naming convention instead
