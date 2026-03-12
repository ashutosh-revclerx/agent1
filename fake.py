"""
Langfuse Fake Data Generator
Sends fake LLM traces directly via the Langfuse HTTP Ingestion API.
No tracing SDK needed — just requests + python-dotenv.

Usage: .\.venv\Scripts\python.exe fake.py
"""
import os
import time
import random
import uuid
import base64
import json
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
import requests

# Load environment variables from .env
load_dotenv()

LANGFUSE_PUBLIC_KEY = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
LANGFUSE_SECRET_KEY = os.environ.get("LANGFUSE_SECRET_KEY", "")
LANGFUSE_HOST = os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com").rstrip("/")

USER_ID = "anon 2"

MODELS = ["gemini-2.0-flash", "gpt-4-turbo", "claude-3-opus", "gemma3:1b"]

TRACE_NAMES = [
    "Process Document", "Answer Question", "Summarize Text",
    "Extract Entities", "Format Code", "Generate Report"
]

# Basic auth header: base64(PUBLIC_KEY:SECRET_KEY)
_creds = base64.b64encode(f"{LANGFUSE_PUBLIC_KEY}:{LANGFUSE_SECRET_KEY}".encode()).decode()
HEADERS = {
    "Authorization": f"Basic {_creds}",
    "Content-Type": "application/json",
}
INGEST_URL = f"{LANGFUSE_HOST}/api/public/ingestion"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ingest(events: list) -> bool:
    """POST events to the Langfuse ingestion endpoint."""
    try:
        resp = requests.post(
            INGEST_URL,
            headers=HEADERS,
            json={"batch": events},
            timeout=15,
        )
        if resp.ok:
            return True
        print(f"  [!] Langfuse API error: {resp.status_code} {resp.text[:200]}")
        return False
    except Exception as e:
        print(f"  [!] Request error: {e}")
        return False


def generate_trace():
    trace_id = str(uuid.uuid4())
    generation_id = str(uuid.uuid4())
    session_id = f"session-{uuid.uuid4().hex[:8]}"
    trace_name = random.choice(TRACE_NAMES)

    is_error = random.random() < 0.1
    model_name = random.choice(MODELS)
    input_tokens = random.randint(10, 500)
    output_tokens = random.randint(5, 200) if not is_error else 0
    total_cost = (input_tokens * 0.000001) + (output_tokens * 0.000002)

    start_time = now_iso()
    time.sleep(random.uniform(0.5, 2.0))
    end_time = now_iso()

    print(f"[{start_time}] Generating trace '{trace_name}' for user: {USER_ID}...")

    events = [
        # 1. Create the trace
        {
            "id": str(uuid.uuid4()),
            "type": "trace-create",
            "timestamp": start_time,
            "body": {
                "id": trace_id,
                "name": trace_name,
                "userId": USER_ID,
                "sessionId": session_id,
                "tags": ["testing", "live-data"],
                "timestamp": start_time,
            },
        },
        # 2. Create the generation (child of trace)
        {
            "id": str(uuid.uuid4()),
            "type": "generation-create",
            "timestamp": end_time,
            "body": {
                "id": generation_id,
                "traceId": trace_id,
                "name": "llm-generation",
                "model": model_name,
                "startTime": start_time,
                "endTime": end_time,
                "input": "User asks a question...",
                "output": "LLM provides an answer..." if not is_error else None,
                "usage": {
                    "input": input_tokens,
                    "output": output_tokens,
                    "totalCost": total_cost,
                },
                "level": "ERROR" if is_error else "DEFAULT",
                "statusMessage": "Failed to process prompt" if is_error else "Success",
            },
        },
    ]

    success = ingest(events)
    status = "✅ sent" if success else "❌ failed"
    print(f" -> [{status}] '{trace_name}' (Model: {model_name}, Error: {is_error})")
    return success


if __name__ == "__main__":
    if not LANGFUSE_PUBLIC_KEY or not LANGFUSE_SECRET_KEY:
        print("❌ LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY must be set in .env")
        exit(1)

    print(f"Starting Langfuse live data generator for user '{USER_ID}'...")
    print(f"Target: {LANGFUSE_HOST}")
    print("Press Ctrl+C to stop.\n")

    # Send one immediately on startup
    try:
        generate_trace()
    except Exception as e:
        print(f"Failed to send trace: {e}")

    while True:
        try:
            time.sleep(30)  # Every 2 minutes
            generate_trace()
        except KeyboardInterrupt:
            print("\nStopping script...")
            break
        except Exception as e:
            print(f"Error generating trace: {e}")
            time.sleep(5)
