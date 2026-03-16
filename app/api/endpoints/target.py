"""
Target Management Routes
Add/Remove Prometheus scrape targets dynamically.
"""
import json
import os
from typing import List
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Depends
from app.schemas.target import Target
from app.schemas.user import User
from app.core.auth import get_current_user
from app.services.mongodb_service import get_db
from app.core.logging import logger
from app.services.monitoring_service import monitor_manager

router = APIRouter()

TARGETS_FILE = "targets.json"


def _regenerate_targets_file(db):
    """
    Regenerate targets.json from MongoDB.

    System labels (user_id, job, name) are applied AFTER merging user labels
    so they can never be overridden by user-supplied label values.
    """
    try:
        targets = list(db.targets.find({"enabled": True}))

        file_sd_content = []
        for t in targets:
            # Start with user-supplied labels (already validated — no reserved keys)
            user_labels = dict(t.get("labels") or {})

            # System labels applied last — always win over user labels
            system_labels = {
                "job": "dynamic-targets",
                "name": t.get("name", "Unknown"),
                "user_id": str(t.get("user_id", "unknown")),
            }

            labels = {**user_labels, **system_labels}

            file_sd_content.append({
                "targets": [t["endpoint"]],
                "labels": labels,
            })

        with open(TARGETS_FILE, "w") as f:
            json.dump(file_sd_content, f, indent=2)

        logger.info(f"[Targets] Regenerated {TARGETS_FILE} with {len(targets)} targets")
        return True

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Targets] Failed to regenerate file: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to update targets file",
        )


@router.get("/agent/targets", response_model=List[Target])
def get_targets(user: User = Depends(get_current_user)):
    """Get all configured targets for current user."""
    db = get_db()
    if db is None:
        return []

    targets = list(db.targets.find({"user_id": user.id}))
    return [
        Target(
            name=t.get("name", ""),
            endpoint=t.get("endpoint", ""),
            labels=t.get("labels") or None,
            enabled=t.get("enabled", True),
        )
        for t in targets
    ]


@router.post("/agent/targets")
async def add_target(target: Target, user: User = Depends(get_current_user)):
    """Add a new monitoring target for current user."""
    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Database error")

    if db.targets.find_one({"endpoint": target.endpoint, "user_id": user.id}):
        raise HTTPException(status_code=400, detail="Target already exists")

    target_doc = target.model_dump()
    target_doc["user_id"] = user.id  # always set server-side, never from payload

    db.targets.insert_one(target_doc)
    _regenerate_targets_file(db)
    await monitor_manager.refresh_monitors()

    logger.info(f"[Targets] User {user.username} added target: {target.endpoint}")
    return {"message": "Target added and monitoring updated"}


@router.delete("/agent/targets/{endpoint:path}")
async def remove_target(endpoint: str, user: User = Depends(get_current_user)):
    """Remove a target for current user."""
    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Database error")

    res = db.targets.delete_one({"endpoint": endpoint, "user_id": user.id})
    if res.deleted_count == 0:
        raise HTTPException(
            status_code=404, detail="Target not found or not owned by you"
        )

    _regenerate_targets_file(db)
    await monitor_manager.refresh_monitors()

    logger.info(f"[Targets] User {user.username} removed target: {endpoint}")
    return {"message": "Target removed"}