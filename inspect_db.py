from app.services.mongodb_service import get_db
import json
from bson import json_util

problematic_id = "697db48e10965d8fb0ff3bb7"
db = get_db()

if db is not None:
    print(f"Searching for {problematic_id} in all collections...")
    for coll_name in db.list_collection_names():
        coll = db[coll_name]
        # Search in all fields using $regex or exact match
        count = coll.count_documents({"$or": [
            {"user_id": problematic_id},
            {"labels.user_id": problematic_id}
        ]})
        if count > 0:
            print(f"Found {count} matches in {coll_name}")
            docs = list(coll.find({"$or": [
                {"user_id": problematic_id},
                {"labels.user_id": problematic_id}
            ]}))
            print(json.dumps(docs, default=json_util.default, indent=2))
else:
    print("Failed to connect to DB")
