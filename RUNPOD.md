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

See `form_reader_comparitor_llm/RUNPOD.md` for vLLM serve args, probes, and failure cheatsheet.
