"""
Target Management Routes
Add/Remove Prometheus scrape targets dynamically.
"""
import json
import os
from typing import List

from fastapi import APIRouter, HTTPException, Depends
from app.schemas.target import Target
from app.schemas.user import User
from app.core.auth import get_current_user
from app.services.mongodb_service import get_db
from app.core.logging import logger

router = APIRouter()

TARGETS_FILE = "targets.json"

def _regenerate_targets_file(db):
    """Regenerate targets.json from MongoDB with user_id labels"""
    try:
        # Get ALL enabled targets from ALL users
        targets = list(db.targets.find({"enabled": True}))
        
        file_sd_content = []
        for t in targets:
            # Include user_id in labels for filtering
            labels = {
                "job": "dynamic-targets", 
                "name": t.get("name", "Unknown"),
                "user_id": t.get("user_id", "unknown"),  # Critical: user_id label
                **(t.get("labels", {}) or {})
            }
            
            file_sd_content.append({
                "targets": [t["endpoint"]],
                "labels": labels
            })
            
        # Write to file
        with open(TARGETS_FILE, "w") as f:
            json.dump(file_sd_content, f, indent=2)
            
        logger.info(f"[Targets] Regenerated {TARGETS_FILE} with {len(targets)} targets")
        logger.debug(f"[Targets] File contents: {file_sd_content}")
        return True
    except Exception as e:
        logger.error(f"[Targets] Failed to regenerate file: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update targets file: {str(e)}"
        )


@router.get("/agent/targets", response_model=List[Target])
def get_targets(user: User = Depends(get_current_user)):
    """Get all configured targets for current user"""
    db = get_db()
    if db is None:
        return []
        
    # Filter by user_id
    targets = list(db.targets.find({"user_id": user.id}))
    results = []
    for t in targets:
        results.append(Target(
            name=t.get("name", ""),
            endpoint=t.get("endpoint", ""),
            labels=t.get("labels", {}),
            enabled=t.get("enabled", True)
        ))
    return results


@router.post("/agent/targets")
def add_target(target: Target, user: User = Depends(get_current_user)):
    """Add a new monitoring target for current user"""
    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Database error")
        
    # Check if target already exists for this user
    if db.targets.find_one({"endpoint": target.endpoint, "user_id": user.id}):
        raise HTTPException(status_code=400, detail="Target already exists")
    
    # Add user_id to target document
    target_doc = target.model_dump()
    target_doc["user_id"] = user.id
    
    db.targets.insert_one(target_doc)
    
    # Regenerate targets.json with ALL users' targets
    _regenerate_targets_file(db)
    
    logger.info(f"[Targets] User {user.username} added target: {target.endpoint}")
    
    return {"message": "Target added and monitoring updated"}


@router.delete("/agent/targets/{endpoint}")
def remove_target(endpoint: str, user: User = Depends(get_current_user)):
    """Remove a target for current user"""
    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Database error")
        
    # Only delete if it belongs to this user
    res = db.targets.delete_one({"endpoint": endpoint, "user_id": user.id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Target not found or not owned by you")
        
    # Regenerate file
    _regenerate_targets_file(db)
    
    logger.info(f"[Targets] User {user.username} removed target: {endpoint}")
    
    return {"message": "Target removed"}

