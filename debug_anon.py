import asyncio
from app.services.langfuse_ingestion_service import _auth
from app.core.config import LANGFUSE_HOST
import requests

from datetime import datetime, timedelta, timezone

def _ts(dt: datetime) -> str:
    """Format datetime as ISO string exactly like _ts in ingestion service"""
    return dt.isoformat()

def debug():
    print(f"LANGFUSE_HOST: {LANGFUSE_HOST}")
    
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=2)  # Expanded window to 2 hours for testing
    
    print(f"\n--- Emulating polling for ANY user ---")
    params = {
        "limit": 10,
    }
    print(f"Params: {params}")
    try:
        res = requests.get(
            f"{LANGFUSE_HOST}/api/public/traces",
            auth=_auth(),
            params=params,
            timeout=10
        )
        res.raise_for_status()
        data = res.json().get("data", [])
        print(f"Found {len(data)} traces.")
        for t in data:
            print(f" - ID: {t['id'][:8]}..., UserID: {t.get('userId')}, Name: {t.get('name')}, Time: {t['timestamp']}")
    except Exception as e:
        print(f"Failed to fetch traces: {e}")
        if hasattr(e, "response") and e.response is not None:
            print(f"Response: {e.response.text}")

if __name__ == "__main__":
    debug()
