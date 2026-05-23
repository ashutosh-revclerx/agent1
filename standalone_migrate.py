from pymongo import MongoClient

def migrate():
    # Correct DB name is 'observability'
    client = MongoClient("mongodb://localhost:27017")
    db = client["observability"]
    old_id = "697db48e10965d8fb0ff3bb7"
    new_id = "69999d8241b8b92a94be4509"
    
    print(f"Migrating {old_id} -> {new_id} in 'observability' database...")
    
    collections = ['targets', 'rca', 'incidents', 'anomalies', 'email_config', 'alert_windows']
    
    for coll_name in collections:
        coll = db[coll_name]
        # Update top-level user_id if it matches old_id
        res1 = coll.update_many({"user_id": old_id}, {"$set": {"user_id": new_id}})
        print(f"Updated {res1.modified_count} docs in {coll_name} (top-level)")
        
        # Update labels.user_id in targets if it exists and matches old_id
        if coll_name == 'targets':
            res2 = coll.update_many({"labels.user_id": old_id}, {"$set": {"labels.user_id": new_id}})
            print(f"Updated {res2.modified_count} docs in targets (labels)")
    
    print("Migration complete")

if __name__ == "__main__":
    migrate()
