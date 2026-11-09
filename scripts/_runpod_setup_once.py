"""One-off RunPod serverless setup helpers (local only)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

API = "https://rest.runpod.io/v1"
EU_DCS = ["EU-RO-1", "EU-SE-1", "EU-CZ-1", "EU-NL-1", "EU-FR-1", "EUR-IS-1", "EUR-IS-2", "EUR-IS-3", "EUR-NO-1"]


def headers() -> dict[str, str]:
    key = os.environ.get("RUNPOD_API_KEY", "").strip()
    if not key:
        raise SystemExit("RUNPOD_API_KEY missing")
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def list_vllm_templates(client: httpx.Client) -> list[dict]:
    r = client.get(
        f"{API}/templates",
        headers=headers(),
        params={
            "includeRunpodTemplates": True,
            "includePublicTemplates": True,
            "includeEndpointBoundTemplates": True,
        },
    )
    r.raise_for_status()
    items = r.json()
    out = []
    for t in items:
        name = t.get("name") or ""
        image = t.get("imageName") or ""
        blob = f"{name} {image}".lower()
        if "vllm" in blob or "worker-v1-vllm" in blob:
            out.append(t)
    return out


def main_list() -> None:
    with httpx.Client(timeout=120) as client:
        templates = list_vllm_templates(client)
        print(json.dumps(templates, indent=2)[:12000])


PREFERRED_GPUS = [
    "NVIDIA L40S",
    "NVIDIA RTX 6000 Ada Generation",
    "NVIDIA L40",
    "NVIDIA A40",
    "NVIDIA RTX A6000",
    "NVIDIA GeForce RTX 4090",
    "NVIDIA RTX A5000",
]


def eu_gpu_plan(client: httpx.Client) -> tuple[list[str], list[str]]:
    r = client.get(
        "https://api.runpod.io/v2/catalog/datacenters",
        headers=headers(),
        params={"regions": "EUROPE", "include": "GPU_AVAILABILITY"},
    )
    r.raise_for_status()
    dcs = r.json().get("dataCenters") or []
    eu_ids = [dc["id"] for dc in dcs if dc.get("region") == "EUROPE"]
    available: set[str] = set()
    for dc in dcs:
        for gpu in dc.get("gpuAvailability") or []:
            if gpu.get("availability") in {"LOW", "MEDIUM", "HIGH"}:
                available.add(gpu["id"])
    gpus = [g for g in PREFERRED_GPUS if g in available]
  if not gpus:
        gpus = [g for g in PREFERRED_GPUS if any(
            g == x.get("id")
            for dc in dcs
            for x in (dc.get("gpuAvailability") or [])
        )][:3]
    if not gpus:
        gpus = ["NVIDIA L40S", "NVIDIA RTX 6000 Ada Generation", "NVIDIA A40"]
    return eu_ids, gpus


def create_endpoint() -> dict:
    worker_env = {
        "MODEL_NAME": "Qwen/Qwen3-VL-8B-Instruct",
        "OPENAI_SERVED_MODEL_NAME_OVERRIDE": "qwen3-vl-8b-instruct",
        "TRUST_REMOTE_CODE": "true",
        "DTYPE": "float16",
        "GPU_MEMORY_UTILIZATION": "0.90",
        "MAX_MODEL_LEN": "8192",
        "MAX_NUM_SEQS": "1",
        "MAX_CONCURRENCY": "1",
        "LIMIT_MM_PER_PROMPT": "image=1",
        "HF_HUB_CACHE": "/runpod-volume/hf-cache",
    }
    template_body = {
        "name": "doc-intel-qwen3-vl-8b-vllm",
        "imageName": "runpod/worker-v1-vllm:v2.30.1",
        "isServerless": True,
        "containerDiskInGb": 80,
        "volumeInGb": 50,
        "volumeMountPath": "/runpod-volume",
        "env": worker_env,
    }
    with httpx.Client(timeout=180) as client:
        eu_ids, gpu_ids = eu_gpu_plan(client)
        tr = client.post(f"{API}/templates", headers=headers(), json=template_body)
        if tr.status_code >= 400:
            raise SystemExit(f"template failed {tr.status_code}: {tr.text[:2000]}")
        template = tr.json()
        template_id = template["id"]
        endpoint_body = {
            "name": "document-intelligence-qwen3-vl-8b",
            "templateId": template_id,
            "computeType": "GPU",
            "gpuCount": 1,
            "gpuTypeIds": gpu_ids,
            "dataCenterIds": eu_ids or EU_DCS,
            "workersMin": 0,
            "workersMax": 2,
            "idleTimeout": 120,
            "executionTimeoutMs": 900_000,
            "env": worker_env,
            "flashboot": True,
        }
        er = client.post(f"{API}/endpoints", headers=headers(), json=endpoint_body)
        if er.status_code >= 400:
            raise SystemExit(f"endpoint failed {er.status_code}: {er.text[:2000]}")
        endpoint = er.json()
        return {
            "endpoint_id": endpoint.get("id"),
            "endpoint_name": endpoint.get("name"),
            "template_id": template_id,
            "data_centers": endpoint.get("dataCenterIds") or eu_ids,
            "gpu_types": endpoint.get("gpuTypeIds") or gpu_ids,
        }


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "list":
        main_list()
    elif len(sys.argv) > 1 and sys.argv[1] == "create":
        print(json.dumps(create_endpoint(), indent=2))
    else:
        print("usage: create | list")
