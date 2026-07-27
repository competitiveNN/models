# Model Ranking & Auxiliary Task Assignment

Generated from `fetch-free-models.py` + live Kilo/OpenCode fetches
+ NVIDIA NIM as the paid fallback tier.

## Tier rubric

| Tier | Description |
|------|-------------|
| 1 | Frontier (≥250B MoE) — reasoning, JSON, planning |
| 2 | Strong (100–200B) — tool-call, structured output |
| 3 | Medium (30–120B) — classification, extraction |
| 4 | Lightweight (<30B) — short calls |
| Vision | Native image input |

## Catalog

### Tier 1 — Frontier

| Provider | Slug | Context | Free? |
|----------|------|---------|-------|
| kilocode | `nvidia/nemotron-3-ultra-550b-a55b:free` | 1,000,000 | Y |
| nvidia | `google/gemma-4-31b-it` | 262,144 | N |
| nvidia | `moonshotai/kimi-k2.7` | 262,144 | N |
| nvidia | `nvidia/llama-3.1-nemotron-ultra-253b-v1` | 131,072 | N |
| nvidia | `nvidia/nemotron-3-ultra-550b-a55b` | 1,000,000 | N |
| nvidia | `qwen/qwen3.5-397b-a17b` | 262,144 | N |
| ollama-cloud | `gemma4:31b` | 262,144 | Y |
| ollama-cloud | `nemotron-3-ultra` | 1,000,000 | Y |
| opencode | `nemotron-3-ultra-free` | 1,000,000 | Y |

### Tier 2 — Strong

| Provider | Slug | Context | Free? |
|----------|------|---------|-------|
| kilocode | `kilo-auto/free` | 256,000 | Y |
| kilocode | `nvidia/nemotron-3-super-120b-a12b:free` | 262,144 | Y |
| kilocode | `openrouter/free` | 200,000 | Y |
| nvidia | `deepseek-ai/deepseek-v4-pro` | 262,144 | N |
| nvidia | `minimaxai/minimax-m3` | 262,144 | N |
| nvidia | `mistralai/mistral-medium-3.5-128b` | 262,144 | N |
| nvidia | `moonshotai/kimi-k2.6` | 262,144 | N |
| nvidia | `nvidia/nemotron-3-super-120b-a12b` | 262,144 | N |
| nvidia | `qwen/qwen3.5-122b-a10b` | 262,144 | N |
| nvidia | `thinkingmachines/inkling` | 262,144 | N |
| nvidia | `z-ai/glm-5.2` | 262,144 | N |
| ollama-cloud | `minimax-m3` | 262,144 | Y |
| ollama-cloud | `nemotron-3-super` | 262,144 | Y |

### Tier 3 — Medium

| Provider | Slug | Context | Free? |
|----------|------|---------|-------|
| kilocode | `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` | 256,000 | Y |
| kilocode | `poolside/laguna-xs-2.1:free` | 262,144 | Y |
| kilocode | `stepfun/step-3.7-flash:free` | 262,144 | Y |
| nvidia | `deepseek-ai/deepseek-v4-flash` | 262,144 | N |
| nvidia | `mistralai/mistral-small-4-119b-2603` | 262,144 | N |
| nvidia | `poolside/laguna-xs-2.1` | 262,144 | N |
| nvidia | `stepfun-ai/step-3.7-flash` | 262,144 | N |
| opencode | `deepseek-v4-flash-free` | 131,072 | Y |

### Tier 4 — Lightweight

| Provider | Slug | Context | Free? |
|----------|------|---------|-------|
| kilocode | `cohere/north-mini-code:free` | 256,000 | Y |
| kilocode | `inclusionai/ling-3.0-flash:free` | 262,144 | Y |
| kilocode | `poolside/laguna-m.1:free` | 262,144 | Y |
| kilocode | `poolside/laguna-s-2.1:free` | 262,144 | Y |
| opencode | `laguna-s-2.1-free` | 131,072 | Y |
| opencode | `ling-3.0-flash-free` | 131,072 | Y |
| opencode | `mimo-v2.5-free` | 131,072 | Y |
| opencode | `north-mini-code-free` | 131,072 | Y |

### Vision

| Provider | Slug | Context | Free? |
|----------|------|---------|-------|
| kilocode | `nvidia/nemotron-3.5-content-safety:free` | 128,000 | Y |
| nvidia | `google/diffusiongemma-26b-a4b-it` | 262,144 | N |

## Auxiliary task → assignment

Each task has 3 slots. Every chain uses 3 different providers and
3 unique slugs (the `vision` task is the only exception — only 2
vision-capable providers exist).

| Task | Primary | Fallback 1 | Fallback 2 |
|------|---------|-----------|-----------|
| `kanban_decomposer` | ollama-cloud / `nemotron-3-ultra` | kilocode / `nvidia/nemotron-3-ultra-550b-a55b:free` | opencode / `nemotron-3-ultra-free` |
| `curator` | nvidia / `qwen/qwen3.5-397b-a17b` | ollama-cloud / `gemma4:31b` | kilocode / `nvidia/nemotron-3-super-120b-a12b:free` |
| `moa_aggregator` | ollama-cloud / `gemma4:31b` | nvidia / `moonshotai/kimi-k2.7` | kilocode / `nvidia/nemotron-3-ultra-550b-a55b:free` |
| `flush_memories` | nvidia / `moonshotai/kimi-k2.7` | ollama-cloud / `gemma4:31b` | kilocode / `nvidia/nemotron-3-super-120b-a12b:free` |
| `compression` | ollama-cloud / `nemotron-3-ultra` | kilocode / `nvidia/nemotron-3-ultra-550b-a55b:free` | nvidia / `nvidia/nemotron-3-ultra-550b-a55b` |
| `mcp` | nvidia / `qwen/qwen3.5-122b-a10b` | ollama-cloud / `minimax-m3` | kilocode / `stepfun/step-3.7-flash:free` |
| `moa_reference` | ollama-cloud / `nemotron-3-super` | kilocode / `nvidia/nemotron-3-super-120b-a12b:free` | nvidia / `nvidia/nemotron-3-super-120b-a12b` |
| `session_search` | nvidia / `qwen/qwen3.5-122b-a10b` | ollama-cloud / `nemotron-3-super` | kilocode / `openrouter/free` |
| `triage_specifier` | ollama-cloud / `nemotron-3-super` | kilocode / `nvidia/nemotron-3-super-120b-a12b:free` | nvidia / `deepseek-ai/deepseek-v4-pro` |
| `web_extract` | nvidia / `mistralai/mistral-medium-3.5-128b` | ollama-cloud / `minimax-m3` | kilocode / `nvidia/nemotron-3-ultra-550b-a55b:free` |
| `profile_describer` | kilocode / `stepfun/step-3.7-flash:free` | nvidia / `mistralai/mistral-small-4-119b-2603` | opencode / `deepseek-v4-flash-free` |
| `approval` | nvidia / `mistralai/mistral-small-4-119b-2603` | kilocode / `stepfun/step-3.7-flash:free` | ollama-cloud / `gemma4:31b` |
| `title_generation` | kilocode / `stepfun/step-3.7-flash:free` | nvidia / `stepfun-ai/step-3.7-flash` | opencode / `deepseek-v4-flash-free` |
| `goal_judge` | ollama-cloud / `nemotron-3-super` | kilocode / `nvidia/nemotron-3-super-120b-a12b:free` | nvidia / `deepseek-ai/deepseek-v4-pro` |
| `background_review` | nvidia / `mistralai/mistral-medium-3.5-128b` | kilocode / `openrouter/free` | ollama-cloud / `gemma4:31b` |
| `memory_query_rewrite` | kilocode / `cohere/north-mini-code:free` | opencode / `north-mini-code-free` | nvidia / `stepfun-ai/step-3.7-flash` |
| `skills_hub` | nvidia / `stepfun-ai/step-3.7-flash` | kilocode / `stepfun/step-3.7-flash:free` | ollama-cloud / `minimax-m3` |
| `monitor` | kilocode / `inclusionai/ling-3.0-flash:free` | opencode / `ling-3.0-flash-free` | ollama-cloud / `minimax-m3` |
| `tts_audio_tags` | kilocode / `poolside/laguna-s-2.1:free` | opencode / `laguna-s-2.1-free` | nvidia / `stepfun-ai/step-3.7-flash` |
| `vision` | ollama-cloud / `gemma4:31b` | nvidia / `google/gemma-4-31b-it` | nvidia / `google/diffusiongemma-26b-a4b-it` |

## Provider usage

| Provider | Slots | Share |
|----------|-------|-------|
| kilocode | 19 | 31.7% |
| nvidia | 19 | 31.7% |
| ollama-cloud | 16 | 26.7% |
| opencode | 6 | 10.0% |

## Free-vs-paid

- Free slots: **41** / 60
- Paid slots: **19** / 60