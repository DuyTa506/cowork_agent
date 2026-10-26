# Model serving

Serves the models for the document AI application on a single GPU (RTX PRO 6000 Blackwell, 95.6 GiB): LLM, embedding, rerank and OCR.
Runs fully offline: every model loads from a local path and nothing is pulled from the Internet at run time (the
`vllm/vllm-openai:v0.32.0` image must already be present).

| service | model | port | protocol |
|---|---|---:|---|
| LLM | Qwen3.6-35B-A3B NVFP4 (`/opt/intramind/models/llm/...-v1`), served as `qwen3.6-35b-a3b` | 8201 | OpenAI `/v1/chat/completions`, tool calling `qwen3_coder`, reasoning `qwen3`, thinking on |
| embedding | `microsoft/harrier-oss-v1-270m`, 640 dimensions, 32,768 tokens | 8204 (adapter) | `POST /api/v1/embed {texts, input_type}` |
| rerank | `BAAI/bge-reranker-v2-m3`, 8,192 tokens | 8204 (adapter) | `POST /api/v1/rerank {query, documents, top_k}` |
| OCR (batch) | Peppercorn v3 (`d48sh-muon`), served as `peppercorn-v3` | 8205 | OpenAI `/v1/chat/completions`, page images |

Ports 8202 and 8203 are the vLLM backends for embedding and rerank (listening on 127.0.0.1 only). The adapter (`adapter/app.py`) speaks
the same contract as the intramind serving layer (:5003), so the application needs no code change.

## Running

```bash
cp .env.example .env        # edit paths, ports and GPU fractions if needed
scripts/up.sh all           # llm -> embedding -> rerank -> adapter (order matters: vLLM checks free memory at startup)
scripts/up.sh ocr           # OCR runs separately, in batches; needs OCR_DIR in .env (see ocr/README.md)
scripts/health.sh           # status of each service + GPU memory
scripts/down.sh all         # stop everything (only this repo's containers, other containers are untouched)
scripts/selftest.sh         # adapter contract test, no GPU needed
```

Requires docker permissions (the scripts use `sg docker` automatically if the current shell is not in the docker group). The LLM takes about 5-6 minutes to come up.
By default everything listens on `127.0.0.1` only; set `BIND_ADDR=0.0.0.0` in `.env` if the application runs on another machine, and only do so on a trusted
internal network, since no API key is set.

## GPU memory (measured with nvidia-smi)

| component | MiB | GiB | configuration |
|---|---:|---:|---|
| LLM | 78,026 | 76.2 | `LLM_GPU_UTIL=0.78`, 3.37M KV tokens, 25.7 concurrent 131k sessions |
| embedding | 4,146 | 4.05 | `EMBED_GPU_UTIL=0.04` |
| rerank | 2,564 | 2.5 | `RERANK_GPU_UTIL=0.04` |
| OCR (when on) | ~4,140 | ~4.0 | `OCR_GPU_UTIL=0.05`, 308k KV tokens |
| **total with all four on** | **88,608** | **86.5** | about 9.3 GiB free |

- The maximum length does not increase memory: embedding at 32,768 tokens and at 4,096 tokens uses almost the same amount (memory is set by
  `*_GPU_UTIL`, not by the length).
- After heavy tests (a ~41k-token document, a batch of 32 x 1,200 tokens) memory grows by about 1 GiB, so keep some headroom.
- For a lighter LLM: `LLM_GPU_UTIL=0.65` leaves 18.6 concurrent 131k sessions (2.44M KV tokens), 0.50 leaves 10.4 sessions.

## Application settings (Admin → System)

| field | value (replace `HOST` with this machine's address) |
|---|---|
| LLM base_url | `http://HOST:8201/v1` |
| LLM model | `qwen3.6-35b-a3b` |
| Embedding | type `intramind`, address `http://HOST:8204` (route `/api/v1/embed`) |
| Rerank | address `http://HOST:8204` (route `/api/v1/rerank`) |
| OCR base_url / model | `http://HOST:8205/v1` / `peppercorn-v3` |

## Verified behavior

- vLLM 0.32 returns reasoning in the **`reasoning`** field (not `reasoning_content`); the application's harness reads both.
- Parallel tool calling works; `chat_template_kwargs.enable_thinking=false` works without a 400 error.
- With thinking on, the second turn spends many reasoning tokens (both tries with `max_tokens=1500` ran out of budget); set `max_tokens` high enough.
- Prompts shorter than one cache block (2176 tokens) are not prefix-cached with this hybrid model. `--prefix-match-unit 16`
  (set in `LLM_EXTRA_ARGS`) gives finer-grained caching, but has only been tested on a different configuration and has its own cost (fewer idle sessions are kept).
- Embedding through the adapter vs transformers: cosine >= 0.99988; the reranker matches the transformers scores (max deviation 0.0002).
  The adapter truncates (does not reject) inputs over the limit, and returns `{"results": []}` right away when there are no documents.
- The adapter does not implement the intramind layer's `X-Intramind-Attempt-ID` / `Expected-Revision` headers.

## Not done yet

- KV offload to RAM (`--kv-offloading-size`): not enabled because the real number of idle sessions is unknown; the RAM tier must hold the whole working set (13.3 KB per token).
- A long soak test; bge-reranker is not under `/opt/intramind/models/rerank` yet (run `scripts/stage_rerank.sh` once to copy it there).
- OCR quality and multi-page throughput have not been measured.

LLM configuration source: github.com/DuyTa506/sm120-vllm-kernels (`CONFIG=next`); the patch files are in `vllm_patches/`.
Internal data: do not commit weights or checkpoints (see `.gitignore`). Remote: https://github.com/DuyTa506/cowork_agent
