# For building the docker container on fedora silverblue
use the flag `--security-opt label=disable` like:
```
docker build --security-opt label=disable -f docker/Dockerfile.xpu -t vllm-xpu-env --shm-size=4g . --no-cache
```
to avoid permission denied error of volumes mounted inside container.

Note:
VLLM from master (0.16) doesn't work, because it lacks IPEX (which has also been deprecated)

---

## Multi-instance vLLM with docker-compose

The `docker-compose.yaml` runs two vLLM OpenAI-compatible servers side-by-side, each pinned to a different Intel GPU (XPU) and listening on its own port.

### Services
| service | container | XPU | port | model (config) |
|---------|-----------|-----|------|----------------|
| `vllm-a` | `vllm-a` | 0 (`ZE_AFFINITY_MASK=0`) | 8009 | `config.a.yaml` |
| `vllm-b` | `vllm-b` | 1 (`ZE_AFFINITY_MASK=1`) | 8010 | `config.b.yaml` |

Each service has:
- its own config file (`config.a.yaml` / `config.b.yaml`)
- its own entrypoint script (`entrypoint.a.sh` / `entrypoint.b.sh`)
- dedicated 16 GB shared memory (`shm_size: "16gb"`)
- GPU pinned via `ZE_AFFINITY_MASK` + `ONEAPI_DEVICE_SELECTOR`
- host networking (`network_mode: host`)

### Start both
```bash
docker compose up vllm-a vllm-b
# or with podman
podman-compose up vllm-a vllm-b
```

### Verify
```bash
# health / ready
curl http://localhost:8009/health
curl http://localhost:8010/health

# chat completions
curl -X POST http://localhost:8009/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"model-a","messages":[{"role":"user","content":"Hello"}]}'
```

### Config files
- `config.a.yaml` — Ornith-1.0-9B-AWQ-INT4 on XPU 0, port 8009
- `config.b.yaml` — gemma-4-12B-it-qat-AWQ-INT4 on XPU 1, port 8010

Edit the `model:` path in each config to point at your local model directories under `$HOME/data/models/`.