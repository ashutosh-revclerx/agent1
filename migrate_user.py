import asyncio
from app.services.mongodb_service import get_db
from app.api.endpoints.target import _regenerate_targets_file
from app.services.monitoring_service import monitor_manager

async def migrate():
    old_id = "697db48e10965d8fb0ff3bb7"
    new_id = "69999d8241b8b92a94be4509"
    
    db = get_db()
    if db is None:
        print("Failed to connect to DB")
        return

    collections = ['targets', 'rca', 'incidents', 'anomalies', 'email_config', 'alert_windows']
    
    print(f"Migrating {old_id} -> {new_id}...")
    
    for coll_name in collections:
        coll = db[coll_name]
        res = coll.update_many({"user_id": old_id}, {"$set": {"user_id": new_id}})
        print(f"Updated {res.modified_count} docs in {coll_name}")
        
        # Also check for user_id inside labels for targets
        if coll_name == 'targets':
            res_labels = coll.update_many({"labels.user_id": old_id}, {"$set": {"labels.user_id": new_id}})
            print(f"Updated {res_labels.modified_count} docs in targets (labels)")

    print("Regenerating targets.json...")
    _regenerate_targets_file(db)
    
    print("Refreshing monitors...")
    await monitor_manager.refresh_monitors()
    
    print("Done!")

if __name__ == "__main__":
    asyncio.run(migrate())
