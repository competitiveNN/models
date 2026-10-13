# GRIMOIRE on 2x Intel Arc B580 (Battlemage, BMG-G21)

Containerized GRIMOIRE inference engine. The engine is compiled AOT for **both
Battlemage dies** (`bmg_g31` for the B70/B65, `bmg_g21` for the B580/B60/B50) —
an AOT image built for one die does NOT run on the other.

Model checkpoints stay on the host and are mounted read-only; nothing is
copied into the image.

## Files

| File | What it does |
|---|---|
| `Dockerfile` | Two-stage build: oneAPI builder → slim runtime with the Intel GPU driver userspace |
| `docker-compose.yml` | Service definitions for each model (server + one-shot CLI) |
| `.env.example` | Copy to `.env` for `RENDER_GID` / `MODELS_DIR` |
| `run-b580.sh` | Build image + sanity-check generate |

## Build

```bash
cp .env.example .env     # then edit
./run-b580.sh            # builds + runs one-shot generate
# or:
docker compose build
```

**SELinux note.** The model directory is on a bcachefs volume with SELinux
labels, and the container's rootfs is an overlay with a different label set.
A plain `-v` mount therefore denies reads from inside the container even
though the host can read the files fine. Add `security_opt: label=disable`
to every service that mounts the models (all of them here). Verified: the
same files read fine as `fra` on the host and as `root` in the container
once the label is disabled.

## GPU setup

Both Arc B580s live at `04:00.0` and `86:00.0` and surface as
`renderD128` / `renderD129`. The compose file maps exactly those nodes plus
`/dev/dri/by-path:ro` (so a reboot that renumbers the nodes does not break the
lookup). `group_add: [render_gid]` is all the permission it needs — never run
`--privileged`.

## Models

| Compose service | Checkpoint (mounted at `/models/…`) | Engine flags |
|---|---|---|
| `qwen27b` | `Qwen3.8-27B-GPTQ-Int4-sym-G128-MTP-BF16` | `--proj int4`, MTP on (`GRIMOIRE_MTP=1`) |
| `ornith35b` | `Ornith-1.5-35B-A3B-NVFP4` | `--proj mxfp4` (NVFP4 is decoded at load and repacked), MoE flags |
| `qwen-generate` | same Qwen checkpoint | one-shot CLI, one card |
| `ornith-generate` | same Ornith checkpoint | one-shot CLI, one card |

## Run

```bash
docker compose up -d qwen27b     # OpenAI-compatible at http://localhost:8027/v1
docker compose up -d ornith35b   # OpenAI-compatible at http://localhost:8035/v1

# quick one-shot test on a single card:
docker compose run --rm qwen-generate
docker compose run --rm ornith-generate
```

`multi` in the entrypoint runs one `grimoire-server` rank per GPU in the same
container (pipeline parallel). Only rank 0 binds the HTTP port; the other
follows it. `GRIMOIRE_PP_SPLIT` is how many layers the first GPU keeps
(Qwen3.8-27B has 64, Ornith-1.5-35B-A3B has 40).

## Notes

- **MTP on Qwen**: the GPTQ checkpoint ships its own multi-token-prediction
  head, so `-e GRIMOIRE_MTP=1` is all it needs (`GRIMOIRE_MTP_K=4` drafts/step).
  Every token you get is still the model's own greedy choice — MTP only
  proposes.
- **MTP on Ornith**: leave it off. Speculative decoding is not faster on that
  model yet.
- **Ornith NVFP4**: no NVFP4 kernel — the format is decoded at load and
  repacked, so `--proj mxfp4` is the measured fast path (same move as ROCm
  CDNA4 and vllm-mxfp4 for RDNA4).
- **Two cards vs one**: a model that fits one B580 runs faster on one GPU than
  split across two. Both of these are 27B/35B class, so they need the split.
- **`--ctx` is reserved for every slot.** Keep it as small as you need —
  the server prints `prefill chunk up to N tokens per call` at startup.
- **`--init` and a generous stop timeout are required.** Killing a container
  with GPU work in flight can drop the card off the PCI bus until a power
  cycle. `docker-compose.yml` sets both.
