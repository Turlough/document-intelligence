"""One-shot RunPod text + tiny vision probe (loads repo-root .env)."""

from __future__ import annotations

import base64
import io
import sys

import httpx
from dotenv import load_dotenv
from PIL import Image

load_dotenv()

sys.path.insert(0, "src")
from document_intelligence.services.runpod_client import RunPodClient


def main() -> int:
    client = RunPodClient()
    if not client.is_configured:
        print(f"Missing: {client.missing_config_hint()}", file=sys.stderr)
        return 1

    ok = True
    with httpx.Client(timeout=600.0) as http:
        r = http.get(f"{client.base_url}/models", headers=client.request_headers)
        print(f"GET /models -> {r.status_code}")
        if r.status_code == 200 and "Bad gateway" not in r.text:
            print(r.text[:400])
        else:
            print(r.text[:200])
            ok = False

        payload = {
            "model": client.model,
            "messages": [
                {"role": "user", "content": "Reply with exactly one word: Hello"}
            ],
            "max_tokens": 32,
        }
        r2 = http.post(
            f"{client.base_url}/chat/completions",
            headers=client.request_headers,
            json=payload,
        )
        print(f"POST /chat/completions (text) -> {r2.status_code}")
        if r2.is_success:
            content = r2.json()["choices"][0]["message"]["content"]
            print(f"  assistant: {content!r}")
        else:
            print(r2.text[:400])
            ok = False

        img = Image.new("RGB", (64, 64), color=(200, 50, 50))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        vp = {
            "model": client.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "What is the dominant color? One word only.",
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{b64}"},
                        },
                    ],
                }
            ],
            "max_tokens": 32,
        }
        r3 = http.post(
            f"{client.base_url}/chat/completions",
            headers=client.request_headers,
            json=vp,
        )
        print(f"POST /chat/completions (vision) -> {r3.status_code}")
        if r3.is_success:
            content = r3.json()["choices"][0]["message"]["content"]
            print(f"  assistant: {content!r}")
        else:
            print(r3.text[:400])
            ok = False

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
