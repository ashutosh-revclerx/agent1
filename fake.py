"""
Langfuse Fake Data Generator — Full Pipeline Test Suite
========================================================
Tests every case in the updated error-driven RCA pipeline.

Test Cases:
  1. Normal traces only          → ingested, NO RCA triggered
  2. Single error with session   → session RCA triggered, full session fetched
  3. Single error WITHOUT session → sessionless RCA using trace_id as key
  4. Multiple errors same session → grouped into ONE session RCA
  5. Multiple errors diff sessions → separate RCA per session
  6. Error with detailed message  → Gap 2: statusMessage captured in prompt
  7. Error with input/output      → Gap 3: payloads captured in prompt
  8. Mixed session (success+error)→ all session traces fetched for context

Usage:
  .\.venv\Scripts\python.exe fake.py              # run all test cases
  .\.venv\Scripts\python.exe fake.py --case 2     # run specific case
"""
import os
import sys
import time
import random
import uuid
import base64
import argparse
from datetime import datetime, timezone
from dotenv import load_dotenv
import requests

load_dotenv()

LANGFUSE_PUBLIC_KEY = os.environ.get("LANGFUSE_PUBLIC_KEY", "").strip()
LANGFUSE_SECRET_KEY = os.environ.get("LANGFUSE_SECRET_KEY", "").strip()
LANGFUSE_HOST = os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com").strip().rstrip("/")

# Use a dedicated test user so real data is not polluted
USER_ID = "anon"

MODELS = ["gemini-2.0-flash", "gpt-4-turbo", "claude-3-opus", "gemma3:1b"]

_creds = base64.b64encode(f"{LANGFUSE_PUBLIC_KEY}:{LANGFUSE_SECRET_KEY}".encode()).decode()
HEADERS = {
    "Authorization": f"Basic {_creds}",
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
}
INGEST_URL = f"{LANGFUSE_HOST}/api/public/ingestion"


# ── Helpers ────────────────────────────────────────────────────────────────────

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ingest(events: list) -> bool:
    try:
        resp = requests.post(
            INGEST_URL,
            headers=HEADERS,
            json={"batch": events},
            timeout=60,
        )
        if resp.ok:
            return True
        print(f"    [!] Langfuse API error: {resp.status_code} {resp.reason}")
        print(f"    [!] Details: {resp.text}")
        return False
    except Exception as e:
        print(f"    [!] Request error: {e}")
        return False


def make_trace_events(
    name: str,
    model: str,
    session_id: str | None,
    is_error: bool,
    error_message: str = "Internal server error",
    input_text: str = "User asks a question...",
    output_text: str = "LLM provides an answer...",
    input_tokens: int = None,
    output_tokens: int = None,
    sleep_s: float = 0.3,
) -> tuple[list, str]:
    """
    Build a (trace-create + generation-create) event pair.
    Returns (events, trace_id).
    """
    trace_id = str(uuid.uuid4())
    generation_id = str(uuid.uuid4())
    start_time = now_iso()
    time.sleep(sleep_s)
    end_time = now_iso()

    in_tok = input_tokens or random.randint(50, 400)
    out_tok = (output_tokens or random.randint(20, 150)) if not is_error else 0
    cost = round((in_tok * 0.000001) + (out_tok * 0.000002), 8)

    body_base = {
        "id": trace_id,
        "name": name,
        "userId": USER_ID,
        "tags": ["test"],
        "timestamp": start_time,
    }
    if session_id:
        body_base["sessionId"] = session_id

    events = [
        {
            "id": str(uuid.uuid4()),
            "type": "trace-create",
            "timestamp": start_time,
            "body": body_base,
        },
        {
            "id": str(uuid.uuid4()),
            "type": "generation-create",
            "timestamp": end_time,
            "body": {
                "id": generation_id,
                "traceId": trace_id,
                "name": "llm-generation",
                "model": model,
                "startTime": start_time,
                "endTime": end_time,
                "input": input_text,
                "output": output_text if not is_error else None,
                "usage": {
                    "input": in_tok,
                    "output": out_tok,
                    "totalCost": cost,
                },
                "level": "ERROR" if is_error else "DEFAULT",
                "statusMessage": error_message if is_error else "OK",
            },
        },
    ]
    return events, trace_id


def send(name: str, events: list, is_error: bool, session_id: str | None = None):
    ok = ingest(events)
    status = "✅" if ok else "❌"
    sess = f"session={session_id[:12]}..." if session_id else "sessionless"
    err = "ERROR" if is_error else "ok"
    print(f"    {status} {name} | {err} | {sess}")


def separator(title: str):
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print('─' * 60)


def wait(msg: str = "Waiting for poller to ingest..."):
    print(f"\n  ⏳ {msg}")
    time.sleep(5)


# ── Test Cases ─────────────────────────────────────────────────────────────────

def case_1_normal_traces_only():
    """
    Case 1: All success traces — RCA pipeline should NOT be triggered.
    Expectation: traces ingested, no LLM call, no session stored.
    """
    separator("CASE 1 — Normal traces only (no RCA expected)")
    model = random.choice(MODELS)

    for i in range(3):
        events, _ = make_trace_events(
            name=f"Normal-Call-{i+1}",
            model=model,
            session_id=None,
            is_error=False,
        )
        send(f"Normal-Call-{i+1}", events, is_error=False)

    print("  ✔ Expected: traces stored, 0 LLM calls, no RCA in langfuse_rca")


def case_2_single_error_with_session():
    """
    Case 2: One error trace tied to a session that also has success traces.
    Expectation: full session fetched, session RCA run, stored in langfuse_stored_sessions.
    """
    separator("CASE 2 — Single error with session (full session RCA expected)")
    session_id = f"session-{uuid.uuid4().hex[:8]}"
    model = random.choice(MODELS)

    # 2 success traces in the session first
    for i in range(2):
        events, _ = make_trace_events(
            name=f"Step-{i+1}",
            model=model,
            session_id=session_id,
            is_error=False,
        )
        send(f"Step-{i+1} (success)", events, is_error=False, session_id=session_id)

    # 1 error trace in the same session
    events, trace_id = make_trace_events(
        name="Step-3-Failed",
        model=model,
        session_id=session_id,
        is_error=True,
        error_message="NullPointerException at line 42",
    )
    send("Step-3-Failed (error)", events, is_error=True, session_id=session_id)

    print(f"  ✔ Expected: session={session_id} stored, RCA covers all 3 traces")


def case_3_error_without_session():
    """
    Case 3: Error trace with NO session_id.
    Expectation: trace_id used as session key, stored as is_sessionless=True.
    """
    separator("CASE 3 — Error without session_id (sessionless RCA expected)")
    model = random.choice(MODELS)

    events, trace_id = make_trace_events(
        name="Sessionless-Error",
        model=model,
        session_id=None,   # ← no session
        is_error=True,
        error_message="TimeoutError: LLM did not respond within 30s",
    )
    send("Sessionless-Error", events, is_error=True, session_id=None)

    print(f"  ✔ Expected: trace_id={trace_id[:12]}... used as session key, is_sessionless=True")


def case_4_multiple_errors_same_session():
    """
    Case 4: Multiple errors all in the same session.
    Expectation: grouped into ONE session RCA (not one per error trace).
    """
    separator("CASE 4 — Multiple errors in the same session (grouped into 1 RCA)")
    session_id = f"session-{uuid.uuid4().hex[:8]}"
    model = random.choice(MODELS)

    for i in range(3):
        events, _ = make_trace_events(
            name=f"Retry-Attempt-{i+1}",
            model=model,
            session_id=session_id,
            is_error=True,
            error_message=f"RateLimitError: quota exceeded (attempt {i+1})",
        )
        send(f"Retry-Attempt-{i+1} (error)", events, is_error=True, session_id=session_id)

    print(f"  ✔ Expected: 3 errors grouped into 1 session RCA for session={session_id}")


def case_5_multiple_errors_different_sessions():
    """
    Case 5: Errors in completely separate sessions.
    Expectation: one session RCA per session — 2 RCA docs, 2 stored sessions.
    """
    separator("CASE 5 — Errors in different sessions (separate RCA per session)")

    for i in range(2):
        session_id = f"session-{uuid.uuid4().hex[:8]}"
        model = random.choice(MODELS)

        # 1 success + 1 error per session
        events, _ = make_trace_events(
            name=f"Session-{i+1}-Step-1",
            model=model,
            session_id=session_id,
            is_error=False,
        )
        send(f"Session-{i+1}-Step-1 (success)", events, is_error=False, session_id=session_id)

        events, _ = make_trace_events(
            name=f"Session-{i+1}-Step-2-Error",
            model=model,
            session_id=session_id,
            is_error=True,
            error_message=f"AuthenticationError: invalid API key for session {i+1}",
        )
        send(f"Session-{i+1}-Step-2-Error (error)", events, is_error=True, session_id=session_id)

    print("  ✔ Expected: 2 session RCA docs, 2 entries in langfuse_stored_sessions")


def case_6_error_with_detailed_message():
    """
    Case 6: Error with a rich statusMessage.
    Verifies Gap 2 — error_messages field captured and passed to LLM prompt.
    """
    separator("CASE 6 — Detailed error message (Gap 2: error_messages in prompt)")
    session_id = f"session-{uuid.uuid4().hex[:8]}"
    model = "gemini-2.0-flash"

    events, _ = make_trace_events(
        name="Document-Processing-Error",
        model=model,
        session_id=session_id,
        is_error=True,
        error_message=(
            "ValueError: input document exceeds maximum token limit. "
            "Got 8192 tokens, max allowed is 4096. "
            "Traceback: app/services/doc_service.py line 87 in process_document()"
        ),
    )
    send("Document-Processing-Error (detailed error)", events, is_error=True, session_id=session_id)

    print("  ✔ Expected: full error message visible in LLM prompt, RCA mentions token limit")


def case_7_error_with_payloads():
    """
    Case 7: Error trace with explicit input/output content.
    Verifies Gap 3 — input_payload and output_payload captured and passed to LLM prompt.
    """
    separator("CASE 7 — Error with input/output payloads (Gap 3: payloads in prompt)")
    session_id = f"session-{uuid.uuid4().hex[:8]}"
    model = "gpt-4-turbo"

    events, _ = make_trace_events(
        name="Code-Generation-Failed",
        model=model,
        session_id=session_id,
        is_error=True,
        error_message="ContentFilterError: response blocked by safety policy",
        input_text=(
            '{"role": "user", "content": "Write a Python script to automate '
            'bulk data extraction from the internal API using admin credentials"}'
        ),
        output_text=None,  # blocked — no output
    )
    send("Code-Generation-Failed (with payloads)", events, is_error=True, session_id=session_id)

    print("  ✔ Expected: input_payload and output_payload visible in RCA prompt")


def case_8_mixed_session():
    """
    Case 8: Session with many success traces and one late error.
    Verifies full session context is used for RCA (not just error trace).
    """
    separator("CASE 8 — Mixed session: success traces + 1 late error (full context RCA)")
    session_id = f"session-{uuid.uuid4().hex[:8]}"
    model = random.choice(MODELS)
    steps = [
        ("Intent-Classification", False),
        ("Context-Retrieval",     False),
        ("Document-Summarization",False),
        ("Response-Generation",   False),
        ("Post-Processing-Error", True),   # ← only this one fails
    ]

    for name, is_error in steps:
        events, _ = make_trace_events(
            name=name,
            model=model,
            session_id=session_id,
            is_error=is_error,
            error_message="MemoryError: unable to allocate buffer for response post-processing",
            sleep_s=0.2,
        )
        send(name, events, is_error=is_error, session_id=session_id)

    print(f"  ✔ Expected: all 5 traces fetched for session={session_id}, RCA covers full flow")


# ── Runner ─────────────────────────────────────────────────────────────────────

CASES = {
    1: case_1_normal_traces_only,
    2: case_2_single_error_with_session,
    3: case_3_error_without_session,
    4: case_4_multiple_errors_same_session,
    5: case_5_multiple_errors_different_sessions,
    6: case_6_error_with_detailed_message,
    7: case_7_error_with_payloads,
    8: case_8_mixed_session,
}

if __name__ == "__main__":
    if not LANGFUSE_PUBLIC_KEY or not LANGFUSE_SECRET_KEY:
        print("❌ LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY must be set in .env")
        sys.exit(1)

    parser = argparse.ArgumentParser(description="Langfuse pipeline test data generator")
    parser.add_argument(
        "--case", type=int, choices=CASES.keys(),
        help="Run a specific test case (1-8). Omit to run all."
    )
    args = parser.parse_args()

    print(f"\n{'═' * 60}")
    print(f"  Langfuse Pipeline Test Suite")
    print(f"  Target : {LANGFUSE_HOST}")
    print(f"  User ID: {USER_ID}")
    print(f"{'═' * 60}")

    if args.case:
        CASES[args.case]()
    else:
        for num, fn in CASES.items():
            fn()
            # Small pause between cases so traces don't overlap in the 3-min ingest window
            # Increased to 5s to prevent overloading the Free Tier Langfuse server
            if num < len(CASES):
                time.sleep(5)

    print(f"\n{'═' * 60}")
    print("  All traces sent. Poller ingests every 2 min.")
    print("  RCA triggers only for cases 2–8 (error traces).")
    print("  Check:")
    print("    GET /api/langfuse-monitor/traces  → all ingested traces")
    print("    GET /api/langfuse-monitor/rca?rca_type=session  → session RCAs")
    print("    GET /api/langfuse-monitor/sessions/stored  → stored error sessions")
    print(f"{'═' * 60}\n")