from app.services.mongodb_service import get_db

def check_db():
    db = get_db()
    
    watched = list(db.langfuse_watched_users.find({}, {"_id": 0}))
    print(f"Watched users in DB: {watched}")
    
    traces = list(db.langfuse_traces.find({"langfuse_user_id": "anonymous"}).sort("timestamp", -1).limit(5))
    print(f"\nFound {len(traces)} traces for 'anonymous' in MongoDB:")
    for t in traces:
        print(f" - ID: {t['trace_id'][:8]}..., Name: {t.get('name')}, Time: {t['timestamp']}")

if __name__ == "__main__":
    check_db()
