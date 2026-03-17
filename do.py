import os
import uuid
import base64
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv

# ── Load env ─────────────────────────────────────────────
load_dotenv()

LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY")
LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY")
LANGFUSE_HOST = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com").rstrip("/")

# Try BOTH endpoints (hosted versions differ)
ENDPOINTS = [
    f"{LANGFUSE_HOST}/api/public/ingestion",
    f"{LANGFUSE_HOST}/api/public/ingest",
]

# ── Helpers ─────────────────────────────────────────────
def now_iso():
    return datetime.now(timezone.utc).isoformat()

def build_payload():
    return {
        "batch": [
            {
                "id": str(uuid.uuid4()),
                "type": "trace-create",
                "timestamp": now_iso(),
                "body": {
                    "id": str(uuid.uuid4()),
                    "name": "single-test-trace",
                    "userId": "test-user"
                }
            }
        ]
    }

# ── Auth خيارات ──────────────────────────────────────────
def get_headers_basic():
    creds = base64.b64encode(
        f"{LANGFUSE_PUBLIC_KEY}:{LANGFUSE_SECRET_KEY}".encode()
    ).decode()

    return {
        "Authorization": f"Basic {creds}",
        "Content-Type": "application/json",
    }

def get_headers_bearer():
    return {
        "Authorization": f"Bearer {LANGFUSE_SECRET_KEY}",
        "Content-Type": "application/json",
    }

# ── Test Runner ──────────────────────────────────────────
def test_all_configs():
    payload = build_payload()

    configs = [
        ("Basic Auth", get_headers_basic()),
        ("Bearer Auth", get_headers_bearer()),
    ]

    print("\n🚀 Testing Langfuse ingestion...\n")

    for endpoint in ENDPOINTS:
        for name, headers in configs:
            print(f"👉 Trying: {endpoint}")
            print(f"   Auth: {name}")

            try:
                res = requests.post(
                    endpoint,
                    headers=headers,
                    json=payload,
                    timeout=10
                )

                print("   Status :", res.status_code)
                print("   Response:", res.text[:300])
                print("-" * 50)

                # Stop early if success
                if res.status_code == 200:
                    print("\n✅ SUCCESS — Working configuration found!")
                    print(f"Endpoint: {endpoint}")
                    print(f"Auth    : {name}")
                    return

            except Exception as e:
                print("   ❌ Request failed:", e)
                print("-" * 50)

    print("\n❌ All configurations failed → Issue is on Langfuse server side")


# ── Main ────────────────────────────────────────────────
if __name__ == "__main__":
    if not LANGFUSE_PUBLIC_KEY or not LANGFUSE_SECRET_KEY:
        print("❌ Missing LANGFUSE_PUBLIC_KEY or LANGFUSE_SECRET_KEY in .env")
    else:
        print(f"Host: {LANGFUSE_HOST}")
        test_all_configs()