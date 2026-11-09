import os

import httpx
from dotenv import load_dotenv

load_dotenv()


def main() -> None:
    key = os.environ["RUNPOD_API_KEY"].strip()
    h = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    env = {
        "MODEL_NAME": "Qwen/Qwen3-VL-8B-Instruct",
        "OPENAI_SERVED_MODEL_NAME_OVERRIDE": "qwen3-vl-8b-instruct",
        "TRUST_REMOTE_CODE": "true",
        "DTYPE": "float16",
        "GPU_MEMORY_UTILIZATION": "0.90",
        "MAX_MODEL_LEN": "8192",
        "MAX_NUM_SEQS": "1",
        "MAX_CONCURRENCY": "1",
        "HF_HUB_CACHE": "/tmp/hf-cache",
        # vLLM 0.32 JSON flags via dotted CLI (survives VLLM_EXTRA_ARGS shlex parsing).
        "VLLM_EXTRA_ARGS": "--limit-mm-per-prompt.image 1 --limit-mm-per-prompt.video 0",
    }
    r = httpx.patch(
        "https://rest.runpod.io/v1/templates/unizif6mtq", headers=h, json={"env": env}, timeout=60
    )
    print("template", r.status_code, r.text[:800])
    r2 = httpx.post(
        "https://api.runpod.ai/v2/uga4ewiccgnq36/purge-queue",
        headers={"Authorization": f"Bearer {key}"},
        timeout=60,
    )
    print("purge", r2.status_code)


if __name__ == "__main__":
    main()
