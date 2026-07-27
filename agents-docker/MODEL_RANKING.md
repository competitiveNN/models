# Model Ranking & Auxiliary Task Assignment

Generated from the curated marklist in `fetch-free-models.py` (the
source of truth for which models are free on Ollama Cloud) plus the
live `fetch-free-models.py` output for Kilo Code and OpenCode Zen, and
NVIDIA NIM as the paid fallback tier.

Last regenerated: 2026-08.

---

## 1. Provider inventory

| Provider | Free IDs | Paid IDs (used as fallbacks) |
|----------|----------|------------------------------|
| Ollama Cloud | 4 curated (per `OLLAMA_FREE_MODELS` in fetch script) | n/a — only the curated set is used |
| OpenCode Zen | 6 (per `OPENCODE_FREE_MODELS_CTX` in fetch script) | n/a — only free tier |
| Kilo Code | 12 (from `fetch-free-models.py --kilocode-only`) | n/a — only free tier |
| NVIDIA NIM | n/a (paid) | 18 used in fallback chains |

**Total models in catalog: 40.** Of those, 27 distinct slugs are used
across 60 slots in the auxiliary assignments below (68% on free
providers).

---

## 2. Tier rubric

| Tier | Description | Typical use |
|------|-------------|-------------|
| **1 — Frontier** | ≥250B MoE; deep reasoning, JSON planning, summarization | kanban, curator, aggregator |
| **2 — Strong** | 100–200B; tool-call, structured output, mid-complex reasoning | mcp, moa_reference, session_search, vision |
| **3 — Medium** | 30–120B / flash; classification, extraction | approval, goal_judge, profile, monitor |
| **4 — Lightweight** | <30B / distilled; short calls, latency-critical | monitor, tts_audio_tags |
| **Vision** | Has native image input | vision task only |

---

## 3. Catalog (40 models, ranked by tier)

### Tier 1 — Frontier
| Provider | Slug | Context | Free? |
|----------|------|---------|-------|
| ollama-cloud | `gemma4:31b` | 262,144 | Y |
| ollama-cloud | `nemotron-3-ultra` | 1,000,000 | Y |
| opencode | `nemotron-3-ultra-free` | 1,000,000 | Y |
| kilocode | `nvidia/nemotron-3-ultra-550b-a55b:free` | 1,000,000 | Y |
| nvidia | `nvidia/nemotron-3-ultra-550b-a55b` | 1,000,000 | N |
| nvidia | `nvidia/llama-3.1-nemotron-ultra-253b-v1` | 131,072 | N |
| nvidia | `qwen/qwen3.5-397b-a17b` | 262,144 | N |
| nvidia | `moonshotai/kimi-k2.7` | 262,144 | N |

### Tier 2 — Strong
| Provider | Slug | Context | Free? |
|----------|------|---------|-------|
| ollama-cloud | `minimax-m3` | 262,144 | Y |
| ollama-cloud | `nemotron-3-super` | 262,144 | Y |
| kilocode | `nvidia/nemotron-3-super-120b-a12b:free` | 262,144 | Y |
| kilocode | `openrouter/free` | 200,000 | Y |
| kilocode | `kilo-auto/free` | 256,000 | Y |
| nvidia | `nvidia/nemotron-3-super-120b-a12b` | 262,144 | N |
| nvidia | `qwen/qwen3.5-122b-a10b` | 262,144 | N |
| nvidia | `mistralai/mistral-medium-3.5-128b` | 262,144 | N |
| nvidia | `deepseek-ai/deepseek-v4-pro` | 262,144 | N |
| nvidia | `thinkingmachines/inkling` | 262,144 | N |
| nvidia | `z-ai/glm-5.2` | 262,144 | N |
| nvidia | `minimaxai/minimax-m3` | 262,144 | N |

### Tier 3 — Medium
| Provider | Slug | Context | Free? |
|----------|------|---------|-------|
| kilocode | `stepfun/step-3.7-flash:free` | 262,144 | Y |
| kilocode | `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` | 256,000 | Y |
| kilocode | `poolside/laguna-xs-2.1:free` | 262,144 | Y |
| opencode | `deepseek-v4-flash-free` | 131,072 | Y |
| nvidia | `deepseek-ai/deepseek-v4-flash` | 262,144 | N |
| nvidia | `mistralai/mistral-small-4-119b-2603` | 262,144 | N |
| nvidia | `stepfun-ai/step-3.7-flash` | 262,144 | N |
| nvidia | `poolside/laguna-xs-2.1` | 262,144 | N |

### Tier 4 — Lightweight
| Provider | Slug | Context | Free? |
|----------|------|---------|-------|
| kilocode | `poolside/laguna-s-2.1:free` | 262,144 | Y |
| kilocode | `poolside/laguna-m.1:free` | 262,144 | Y |
| kilocode | `cohere/north-mini-code:free` | 256,000 | Y |
| kilocode | `inclusionai/ling-3.0-flash:free` | 262,144 | Y |
| opencode | `laguna-s-2.1-free` | 131,072 | Y |
| opencode | `ling-3.0-flash-free` | 131,072 | Y |
| opencode | `mimo-v2.5-free` | 131,072 | Y |
| opencode | `north-mini-code-free` | 131,072 | Y |

### Vision
| Provider | Slug | Context | Free? |
|----------|------|---------|-------|
| ollama-cloud | `gemma4:31b` | 262,144 | Y |
| kilocode | `nvidia/nemotron-3.5-content-safety:free` | 128,000 | Y |
| nvidia | `google/gemma-4-31b-it` | 262,144 | N |
| nvidia | `google/diffusiongemma-26b-a4b-it` | 262,144 | N |

---

## 4. Auxiliary task → assignment

Each task has **3 slots** (`primary`, `fallback1`, `fallback2`). Every
chain uses **3 different providers** and **3 unique slugs** to spread
load and avoid 429 throttling. The `vision` task is the exception
(only 2 vision-capable providers exist).

| Task | Primary | Fallback 1 | Fallback 2 | Rationale |
|------|---------|-----------|-----------|-----------|
| `kanban_decomposer` | ollama-cloud / nemotron-3-ultra | kilocode / nemotron-3-ultra-550b-a55b:free | opencode / nemotron-3-ultra-free | Frontier tier, 1M ctx for long plan traces |
| `curator` | nvidia / qwen/qwen3.5-397b-a17b | ollama-cloud / gemma4:31b | kilocode / nemotron-3-super-120b-a12b:free | Frontier reasoning for skills/profiles |
| `moa_aggregator` | ollama-cloud / gemma4:31b | nvidia / moonshotai/kimi-k2.7 | kilocode / nemotron-3-ultra-550b-a55b:free | Frontier aggregator across many model outputs |
| `flush_memories` | nvidia / moonshotai/kimi-k2.7 | ollama-cloud / gemma4:31b | kilocode / nemotron-3-super-120b-a12b:free | Frontier summarization to durable store |
| `compression` | ollama-cloud / nemotron-3-ultra | kilocode / nemotron-3-ultra-550b-a55b:free | nvidia / nemotron-3-ultra-550b-a55b | Only 4 models with 1M ctx — all nemotron-3-ultra |
| `mcp` | nvidia / qwen/qwen3.5-122b-a10b | ollama-cloud / minimax-m3 | kilocode / stepfun/step-3.7-flash:free | Tool-call specialist + fast fallback |
| `moa_reference` | ollama-cloud / nemotron-3-super | kilocode / nemotron-3-super-120b-a12b:free | nvidia / nemotron-3-super-120b-a12b | Strong tier, consistent family on fallback |
| `session_search` | nvidia / qwen/qwen3.5-122b-a10b | ollama-cloud / nemotron-3-super | kilocode / openrouter/free | Strong extraction quality |
| `triage_specifier` | ollama-cloud / nemotron-3-super | kilocode / nemotron-3-super-120b-a12b:free | nvidia / deepseek-ai/deepseek-v4-pro | Classification + reasoning |
| `web_extract` | nvidia / mistralai/mistral-medium-3.5-128b | ollama-cloud / minimax-m3 | kilocode / nemotron-3-ultra-550b-a55b:free | Extraction with 128K ctx, 1M fallback |
| `profile_describer` | kilocode / stepfun/step-3.7-flash:free | nvidia / mistralai/mistral-small-4-119b-2603 | opencode / deepseek-v4-flash-free | Tier 3 medium, short desc |
| `approval` | nvidia / mistralai/mistral-small-4-119b-2603 | kilocode / stepfun/step-3.7-flash:free | ollama-cloud / gemma4:31b | Tier 3 yes/no classification |
| `title_generation` | kilocode / stepfun/step-3.7-flash:free | nvidia / stepfun-ai/step-3.7-flash | opencode / deepseek-v4-flash-free | Tier 3 short generation |
| `goal_judge` | ollama-cloud / nemotron-3-super | kilocode / nemotron-3-super-120b-a12b:free | nvidia / deepseek-ai/deepseek-v4-pro | Tier 3 classification |
| `background_review` | nvidia / mistralai/mistral-medium-3.5-128b | kilocode / openrouter/free | ollama-cloud / gemma4:31b | Tier 2 review of completed runs |
| `memory_query_rewrite` | kilocode / cohere/north-mini-code:free | opencode / north-mini-code-free | nvidia / stepfun-ai/step-3.7-flash | Tier 4 lightweight rewrite |
| `skills_hub` | nvidia / stepfun-ai/step-3.7-flash | kilocode / stepfun/step-3.7-flash:free | ollama-cloud / minimax-m3 | Tier 3 fast lookup |
| `monitor` | kilocode / inclusionai/ling-3.0-flash:free | opencode / ling-3.0-flash-free | ollama-cloud / minimax-m3 | Tier 4 lightweight heartbeat |
| `tts_audio_tags` | kilocode / poolside/laguna-s-2.1:free | opencode / laguna-s-2.1-free | nvidia / stepfun-ai/step-3.7-flash | Tier 4 lightweight structured tags |
| `vision` | ollama-cloud / gemma4:31b | nvidia / google/gemma-4-31b-it | nvidia / google/diffusiongemma-26b-a4b-it | Vision specialist (only 2 vision providers) |

---

## 5. Cross-reference summary

### Provider usage across 60 slots

| Provider | Slots | Share |
|----------|-------|-------|
| kilocode | 19 | 31.7% |
| nvidia | 19 | 31.7% |
| ollama-cloud | 16 | 26.7% |
| opencode | 6 | 10.0% |

### Free-vs-paid

| Type | Slots | Share |
|------|-------|-------|
| Free (ollama-cloud, kilocode, opencode) | 41 | **68.3%** |
| Paid (nvidia) | 19 | 31.7% |

### Slug frequency (top reused)

| Slug | Reuses | Note |
|------|--------|------|
| `gemma4:31b` | 6 | Free frontier; ollama-cloud |
| `nvidia/nemotron-3-super-120b-a12b:free` | 5 | Free strong; kilocode |
| `stepfun/step-3.7-flash:free` | 5 | Free medium; kilocode |
| `nvidia/nemotron-3-ultra-550b-a55b:free` | 4 | Free frontier; kilocode |
| `minimax-m3` | 4 | Free strong; ollama-cloud |
| `nemotron-3-super` | 4 | Free strong; ollama-cloud |
| `stepfun-ai/step-3.7-flash` | 4 | Paid medium; nvidia |

### Per-tier task distribution

| Tier | Tasks |
|------|-------|
| Tier 1 (frontier) | kanban_decomposer, curator, moa_aggregator, flush_memories, compression |
| Tier 2 (strong) | mcp, moa_reference, session_search, triage_specifier, web_extract, vision |
| Tier 3 (medium) | profile_describer, approval, title_generation, goal_judge, background_review, skills_hub |
| Tier 4 (lightweight) | memory_query_rewrite, monitor, tts_audio_tags |

---

## 6. Regeneration

The catalog above is regenerated from these sources:

1. **Ollama Cloud free list**: `OLLAMA_FREE_MODELS` set in
   `fetch-free-models.py` (the authoritative curated marklist).
2. **OpenCode Zen free list**: OpenCode Zen's `/v1/models` filtered by
   `-free` suffix; context from `OPENCODE_FREE_MODELS_CTX` in
   `fetch-free-models.py`.
3. **Kilo Code free list**: `python fetch-free-models.py --kilocode-only`
   output (auto-discovered via `:free` suffix / `isFree=True` flag).
4. **NVIDIA NIM**: `fetch-free-models.py` does not query NIM. The list
   above was hand-curated from previous live lookups of
   `https://integrate.api.nvidia.com/v1/models`.

When the Ollama free list changes, edit the `OLLAMA_FREE_MODELS` set in
`fetch-free-models.py` (this is the source of truth) and re-run the
assignment script.
