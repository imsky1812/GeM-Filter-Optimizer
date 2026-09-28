"""
Tests for the chain-hunt job endpoints: start a search, poll it to a result.

The search itself is stubbed -- these check the job lifecycle, not the niche
search (see test_niche_search.py for that).
"""
import sys
import time

from fastapi.testclient import TestClient

import main
import niche_search

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}  {detail}")


def poll(client, job_id, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"/api/chain-hunt/jobs/{job_id}").json()
        if body["status"] in ("done", "error"):
            return body
        time.sleep(0.05)
    return body


client = TestClient(main.app)
REQ = {"category_url": "https://mkp.gem.gov.in/x/search", "target_price": 500,
       "golden_filters": [{"filterKey": "k", "filterName": "k", "isGolden": True, "values": ["a"]}]}

print("\nA search runs as a job and is polled to its result")
niche_search.find_l1_niches = lambda **kw: (time.sleep(0.2), {"status": "WIN", "target": kw["target_price"]})[1]
start = client.post("/api/chain-hunt/jobs", json=REQ)
check("start returns 202 with a job id", start.status_code == 202 and start.json().get("jobId"), start.text)
first = client.get(f"/api/chain-hunt/jobs/{start.json()['jobId']}").json()
check("it is not done the moment it starts", first["status"] in ("queued", "running"), first)
done = poll(client, start.json()["jobId"])
check("it finishes with the search's result", done["status"] == "done" and done["result"] == {"status": "WIN", "target": 500}, done)

print("\nBad input is rejected up front, not minutes later")
bad = client.post("/api/chain-hunt/jobs", json={**REQ, "target_price": 0})
check("zero price -> 400", bad.status_code == 400, bad.text)
bad = client.post("/api/chain-hunt/jobs", json={**REQ, "category_url": "https://evil.example/x"})
check("non-GeM URL -> 400", bad.status_code == 400, bad.text)
bad = client.post("/api/chain-hunt/jobs", json={**REQ, "golden_filters": []})
check("no golden filters -> 422", bad.status_code == 422, bad.text)

print("\nA search that fails reports the failure")


def boom(**kw):
    raise RuntimeError("GeM unreachable")


niche_search.find_l1_niches = boom
job = client.post("/api/chain-hunt/jobs", json=REQ).json()["jobId"]
res = poll(client, job)
check("status error with the reason", res["status"] == "error" and "GeM unreachable" in res["error"], res)

print("\nAn unknown or expired job is a 404")
check("unknown id -> 404", client.get("/api/chain-hunt/jobs/nope").status_code == 404)

print(f"\n{'=' * 60}\n{passed} passed, {failed} failed\n{'=' * 60}")
sys.exit(1 if failed else 0)
