import asyncio
from app.services.langfuse_ingestion_service import _get_watched_user_ids_sync, _ingest_for_user_sync, _auth
from app.core.config import LANGFUSE_HOST
import requests

def debug():
    print(f"LANGFUSE_HOST: {LANGFUSE_HOST}")
    
    watched = _get_watched_user_ids_sync()
    print(f"Watched Users in MongoDB: {watched}")
    
    print("\n--- Fetching latest traces overall (no user filter) ---")
    try:
        res = requests.get(
            f"{LANGFUSE_HOST}/api/public/traces",
            auth=_auth(),
            params={"limit": 5},
            timeout=10
        )
        res.raise_for_status()
        data = res.json().get("data", [])
        print(f"Found {len(data)} total overall traces in Langfuse.")
        for t in data:
            print(f" - ID: {t['id'][:8]}..., UserID: {t.get('userId')}, Name: {t.get('name')}, Timestamp: {t['timestamp']}")
    except Exception as e:
        print(f"Failed to fetch overall traces: {e}")
        if hasattr(e, "response") and e.response is not None:
            print(f"Response: {e.response.text}")

    if not watched:
        print("No users being watched.")
        return

    for user_id in watched:
        print(f"\n--- Testing ingestion for watched user: '{user_id}' ---")
        try:
            # Check what's directly in Langfuse API for this user
            res = requests.get(
                f"{LANGFUSE_HOST}/api/public/traces",
                auth=_auth(),
                params={"limit": 5, "userId": user_id},
                timeout=10
            )
            res.raise_for_status()
            data = res.json().get("data", [])
            print(f"Langfuse API returned {len(data)} traces for this user.")
            for t in data:
                print(f" - Trace ID: {t['id']}, Timestamp: {t['timestamp']}")
                
            # Now run the ingest function
            ingested = _ingest_for_user_sync(user_id)
            print(f"=> Ingestion processed: {ingested} new traces inserted into MongoDB.")
        except Exception as e:
            print(f"Error querying user {user_id}: {e}")
            if hasattr(e, "response") and e.response is not None:
                print(f"Response: {e.response.text}")

if __name__ == "__main__":
    debug()
