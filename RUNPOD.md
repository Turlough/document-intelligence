# RunPod (Qwen3-VL)

Operator notes for **File → Upload**. Client: `src/document_intelligence/services/runpod_client.py`.

**`RUNPOD_HOST` (GPU pod) wins** if both pod host and serverless id are set. For serverless testing, comment out `RUNPOD_HOST` and set `RUNPOD_ENDPOINT_ID` + `RUNPOD_API_KEY`.

| Variable | Purpose |
|----------|---------|
| `RUNPOD_HOST` | Pod OpenAI proxy, e.g. `https://{POD_ID}-8000.proxy.runpod.net` |
| `RUNPOD_ENDPOINT_ID` | Serverless endpoint id only |
| `RUNPOD_MODEL` | Served model id (`qwen3-vl-8b-instruct`) |
| `RUNPOD_API_KEY` | Required for serverless |

Serverless OpenAI root: `https://api.runpod.ai/v2/{RUNPOD_ENDPOINT_ID}/openai/v1`

Prefer EU `dataCenterIds` on the endpoint (e.g. EU-RO-1, EU-SE-1, EU-NL-1). Worker env: vLLM image with `LIMIT_MM_PER_PROMPT=image=1` for vision.

## Document Intelligence serverless (EU)

| Setting | Value |
|---------|--------|
| Endpoint name | `document-intelligence-qwen3-vl-8b` |
| **Endpoint id** | `uga4ewiccgnq36` |
| Template | `doc-intel-qwen3-vl-8b-vllm` (`runpod/worker-v1-vllm:v2.30.1`) |
| GPUs (priority) | RTX 6000 Ada, L40, L40S, A40, RTX A6000 |
| Data centers | EU only (`EU-RO-1`, `EU-SE-1`, `EU-CZ-1`, `EU-NL-1`, `EU-FR-1`, Iceland/Norway EU sites) |
| Workers | min 0, max 2, 15 min job timeout, `LIMIT_MM_PER_PROMPT=image=1` |

Cold start: first `/models` or upload can take several minutes (model pull + vLLM boot). A `502` on the OpenAI route until a worker is healthy is normal.

See `form_reader_comparitor_llm/RUNPOD.md` for vLLM serve args, probes, and failure cheatsheet.
