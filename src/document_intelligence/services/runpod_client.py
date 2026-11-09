from __future__ import annotations

import base64
import logging
import os
from typing import Callable

import httpx

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 600.0
_USER_AGENT = "Mozilla/5.0 (compatible; document-intelligence/0.1)"
_SERVERLESS_OPENAI_ROOT = "https://api.runpod.ai/v2"


class RunPodClient:
    """OpenAI-compatible RunPod client: GPU pod proxy or serverless vLLM."""

    def __init__(
        self,
        api_key: str | None = None,
        endpoint_id: str | None = None,
        model: str | None = None,
        host: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.api_key = (
            api_key if api_key is not None else os.environ.get("RUNPOD_API_KEY", "")
        ).strip()
        self.endpoint_id = (
            endpoint_id
            if endpoint_id is not None
            else os.environ.get("RUNPOD_ENDPOINT_ID", "")
        ).strip()
        self.model = (
            model if model is not None else os.environ.get("RUNPOD_MODEL", "")
        ).strip()
        self.host = (
            host if host is not None else os.environ.get("RUNPOD_HOST", "")
        ).strip()
        self.timeout = timeout

    @property
    def is_configured(self) -> bool:
        if not self.model:
            return False
        if self.host:
            return True
        return bool(self.api_key and self.endpoint_id)

    @property
    def base_url(self) -> str:
        if self.host:
            return self._openai_root_from_host(self.host)
        if self.endpoint_id:
            return f"{_SERVERLESS_OPENAI_ROOT}/{self.endpoint_id}/openai/v1"
        return ""

    @property
    def request_headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "User-Agent": _USER_AGENT,
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    @staticmethod
    def _openai_root_from_host(host: str) -> str:
        root = host.strip().rstrip("/")
        if root.endswith("/openai/v1") or root.endswith("/v1"):
            return root
        return f"{root}/v1"

    def missing_config_hint(self) -> str:
        missing: list[str] = []
        if not self.model:
            missing.append("RUNPOD_MODEL")
        if not self.host and not self.endpoint_id:
            missing.append("RUNPOD_HOST or RUNPOD_ENDPOINT_ID")
        elif not self.host and not self.api_key:
            missing.append("RUNPOD_API_KEY")
        if not missing:
            return ""
        return f"(set {', '.join(missing)} in .env)"

    def _chat_completion(
        self,
        api_model: str,
        messages: list[dict],
        *,
        should_cancel: Callable[[], bool] | None = None,
    ) -> str:
        if not self.is_configured:
            hint = self.missing_config_hint()
            raise RuntimeError(
                "RunPod is not configured" + (f" {hint}" if hint else ".")
            )

        url = f"{self.base_url}/chat/completions"
        payload = {"model": api_model, "messages": messages}
        logger.debug("RunPod POST %s model=%r", url, api_model)

        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(url, headers=self.request_headers, json=payload)
            if should_cancel and should_cancel():
                raise InterruptedError("Cancelled")
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                detail = exc.response.text
                try:
                    err = exc.response.json().get("error", {})
                    if isinstance(err, dict):
                        detail = err.get("message", detail)
                    else:
                        detail = str(err) or detail
                except Exception:
                    pass
                raise RuntimeError(detail or str(exc)) from exc
            data = response.json()

        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError("RunPod returned no choices")
        message = choices[0].get("message") or {}
        content = message.get("content", "")
        if isinstance(content, list):
            parts = [
                part.get("text", "")
                for part in content
                if isinstance(part, dict) and part.get("type") == "text"
            ]
            return "".join(parts).strip()
        return str(content).strip()

    def read_page(
        self,
        prompt: str,
        image_png: bytes,
        *,
        should_cancel: Callable[[], bool] | None = None,
    ) -> str:
        b64 = base64.b64encode(image_png).decode("ascii")
        return self._chat_completion(
            self.model,
            [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{b64}"},
                        },
                    ],
                }
            ],
            should_cancel=should_cancel,
        )
