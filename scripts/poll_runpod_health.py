import os
import time

import httpx
from dotenv import load_dotenv

load_dotenv()


def main() -> None:
    key = os.environ["RUNPOD_API_KEY"].strip()
    eid = os.environ["RUNPOD_ENDPOINT_ID"].strip()
    h = {"Authorization": f"Bearer {key}"}
    with httpx.Client(timeout=180) as c:
        for i in range(12):
            health = c.get(f"https://api.runpod.ai/v2/{eid}/health", headers=h).json()
            w = health.get("workers", {})
            failed = health.get("jobs", {}).get("failed")
            print(
                f"poll {i}: ready={w.get('ready')} running={w.get('running')} failed_jobs={failed}"
            )
            if w.get("ready", 0) > 0:
                r = c.get(f"https://api.runpod.ai/v2/{eid}/openai/v1/models", headers=h)
                if r.status_code == 200 and "Bad gateway" not in r.text:
                    print("models OK", r.text[:300])
                    return
                rs = c.post(
                    f"https://api.runpod.ai/v2/{eid}/runsync",
                    headers=h,
                    json={"input": {"openai_route": "/v1/models", "openai_input": {}}},
                    timeout=600,
                )
                print("runsync", rs.status_code, rs.text[:500])
                if "startup_error" not in rs.text and '"status":"FAILED"' not in rs.text:
                    return
            time.sleep(30)
    print("gave up polling")


if __name__ == "__main__":
    main()
