import os
import time
import random
import uuid
from datetime import datetime, timezone
from dotenv import load_dotenv
from langfuse import Langfuse

# Load environment variables from .env
load_dotenv()

# Initialize Langfuse client
langfuse = Langfuse(
    public_key=os.environ.get("LANGFUSE_PUBLIC_KEY"),
    secret_key=os.environ.get("LANGFUSE_SECRET_KEY"),
    host=os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com")
)

USER_ID = "anon"

MODELS = ["gemini-2.0-flash", "gpt-4-turbo", "claude-3-opus", "gemma3:1b"]

def generate_trace():
    print(f"[{datetime.now(timezone.utc).isoformat()}] Generating new trace for user: {USER_ID}...")
    
    session_id = f"session-{uuid.uuid4().hex[:8]}"
    trace_name = random.choice([
        "Process Document", "Answer Question", "Summarize Text", 
        "Extract Entities", "Format Code", "Generate Report"
    ])
    
    # 1. Create a Trace
    trace = langfuse.trace(
        name=trace_name,
        user_id=USER_ID,
        session_id=session_id,
        tags=["testing", "live-data"]
    )
    
    # Simulate some processing delay
    time.sleep(random.uniform(0.5, 2.0))
    
    # Simulate an error occasionally (10% chance)
    is_error = random.random() < 0.1
    level = "ERROR" if is_error else "DEFAULT"
    status_message = "Failed to process prompt" if is_error else "Success"
    
    model_name = random.choice(MODELS)
    input_tokens = random.randint(10, 500)
    output_tokens = random.randint(5, 200) if not is_error else 0
    total_cost = (input_tokens * 0.000001) + (output_tokens * 0.000002)
    
    # 2. Add an LLM Generation to the trace
    trace.generation(
        name="llm-generation",
        model=model_name,
        input="User asks a question...",
        output="LLM provides an answer..." if not is_error else None,
        usage={
            "input": input_tokens,
            "output": output_tokens,
            "totalCost": total_cost
        },
        level=level,
        status_message=status_message,
    )
    
    # Flush to ensure it's sent to the Langfuse API immediately
    langfuse.flush()
    print(f" -> Trace '{trace_name}' sent! (Model: {model_name}, Error: {is_error})")


if __name__ == "__main__":
    print(f"Starting Langfuse live data generator for user '{USER_ID}'...")
    print("Press Ctrl+C to stop.")
    
    # Send one immediately on startup
    try:
        generate_trace()
    except Exception as e:
        print(f"Failed to send trace: {e}")
        
    while True:
        try:
            # Sleep for 120 seconds (2 minutes)
            time.sleep(120)
            generate_trace()
        except KeyboardInterrupt:
            print("\nStopping script...")
            break
        except Exception as e:
            print(f"Error generating trace: {e}")
            time.sleep(5)  # backoff on error
