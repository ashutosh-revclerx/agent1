import asyncio
import os
import sys
from datetime import datetime

# Adjust path to import app modules
sys.path.append(os.getcwd())

from app.services.mongodb_service import get_db
from app.services.chat_service import chat_service
from app.core.logging import logger

async def test_chatbot_integration():
    db = get_db()
    if db is None:
        print("❌ MongoDB not available")
        return

    # 1. Find a monitoring session (incident)
    batch = db.metrics_batches.find_one({"incident_id": {"$exists": True}})
    if batch:
        session_id = batch.get("session_id") or str(batch.get("incident_id"))
        print(f"🔍 Testing MONITORING context for session: {session_id}")
        
        # Test direct context retrieval
        context = chat_service.get_monitoring_context(db, session_id)
        print(f"✅ Monitoring context retrieved: Type={context.get('type')}, Anoms={len(context.get('anomalies', []))}")
        
        # Test full query (mock message)
        response = await chat_service.query_session(session_id, "monitoring", "test_user", "What were the main anomalies in this monitoring session?")
        print(f"🤖 Chatbot Response (Monitoring):\n{response}\n")
    else:
        print("⚠️ No monitoring incidents found in DB to test.")

    # 2. Find a Langfuse session
    trace = db.langfuse_traces.find_one({"session_id": {"$exists": True}})
    if trace:
        session_id = trace.get("session_id")
        print(f"🔍 Testing LANGFUSE context for session: {session_id}")
        
        # Test direct context retrieval
        context = chat_service.get_langfuse_context(db, session_id)
        print(f"✅ Langfuse context retrieved: Type={context.get('type')}, Traces={len(context.get('traces', []))}")
        
        # Test full query
        response = await chat_service.query_session(session_id, "langfuse", "test_user", "Tell me about the errors in this LLM session.")
        print(f"🤖 Chatbot Response (Langfuse):\n{response}\n")
    else:
        # Fallback to any trace
        trace = db.langfuse_traces.find_one({})
        if trace:
             print(f"🔍 Testing LANGFUSE fallback for trace: {trace.get('trace_id')}")
             # In a real scenario, the chatbot would pass the session_id or trace_id
             # We'll use the user_id context fallback if session_id is missing
             context = chat_service.get_langfuse_context(db, None) 
             print(f"✅ Langfuse context (fallback) retrieved")

    print("🏁 Verification script complete.")

if __name__ == "__main__":
    asyncio.run(test_chatbot_integration())
