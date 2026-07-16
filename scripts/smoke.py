"""Live smoke test against a running instance. Not part of CI (depends on Twitter uptime).

Usage:
    BASE_URL=http://localhost:8000 TWEET_URL=https://x.com/.../status/... \
        backend/.venv/bin/python scripts/smoke.py
"""
import os
import sys

import httpx

base = os.environ.get("BASE_URL", "http://localhost:8000")
tweet = os.environ.get("TWEET_URL")
if not tweet:
    sys.exit("Set TWEET_URL to a public tweet that contains a video")

r = httpx.post(f"{base}/api/resolve", json={"url": tweet}, timeout=60)
print("resolve:", r.status_code)
r.raise_for_status()
data = r.json()
assert data["items"] and data["items"][0]["variants"], "no variants returned"
best = data["items"][0]["variants"][0]
print("best variant:", best["label"], best["url"][:60])

head = httpx.head(best["url"], timeout=30, follow_redirects=True)
print("variant HEAD:", head.status_code)
assert head.status_code == 200
print("smoke OK")
