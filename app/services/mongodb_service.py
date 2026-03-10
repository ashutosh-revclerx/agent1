"""
db.py (MongoDB Service + Helpers)
- Optimized MongoDB connection reuse + ping health check
- Helpers to standardize instance/ip/port parsing and source object
- Validator to ensure only real Prometheus instance labels are treated as instance
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple

from pymongo import MongoClient
from pymongo.errors import PyMongoError

from app.core.config import MONGO_URI, DB_NAME
from app.core.logging import logger

_mongo_client: Optional[MongoClient] = None
_db_connected: bool = False


def get_db():
    """Get MongoDB database connection (cached)."""
    global _mongo_client, _db_connected

    uri = (MONGO_URI or "").strip()
    if not uri:
        logger.error("[MongoDB Error] MONGO_URI not set")
        return None

    try:
        if _mongo_client is None:
            logger.info("[MongoDB] Connecting...")
            _mongo_client = MongoClient(
                uri,
                serverSelectionTimeoutMS=10000,
                connectTimeoutMS=10000,
                socketTimeoutMS=10000,
                maxPoolSize=10,
                minPoolSize=1,
                retryWrites=True,
            )
            _db_connected = False

        if not _db_connected:
            _mongo_client.admin.command("ping")
            _db_connected = True
            logger.info("[MongoDB] Connected!")

        return _mongo_client[DB_NAME]

    except PyMongoError as e:
        logger.error(f"[MongoDB Error] {e}")
    except Exception as e:
        logger.error(f"[MongoDB Error] Unexpected: {e}")

    _mongo_client = None
    _db_connected = False
    return None


def parse_instance(instance: str) -> Tuple[str, Optional[int]]:
    """
    Parse:
      - 'ip:port' / 'host:port' -> ('ip_or_host', port)
      - '[::1]:9182' -> ('::1', 9182)
      - 'host' -> ('host', None)
    Returns (host_or_ip, port|None)
    """
    if not instance:
        return ("unknown", None)

    inst = instance.strip()

    # IPv6 bracket format: [::1]:9182
    if inst.startswith("[") and "]" in inst:
        host = inst.split("]")[0].lstrip("[")
        rest = inst.split("]")[1]
        if rest.startswith(":"):
            try:
                return (host, int(rest[1:]))
            except Exception:
                return (host, None)
        return (host, None)

    # host:port
    if ":" in inst:
        host, port_str = inst.rsplit(":", 1)
        try:
            return (host, int(port_str))
        except Exception:
            return (host, None)

    return (inst, None)


def build_source(
    *,
    instance: Optional[str] = None,
    job: Optional[str] = None,
    labels: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Consistent source object to store in every collection."""
    inst = (instance or "unknown").strip()
    ip, port = parse_instance(inst)

    src: Dict[str, Any] = {"instance": inst, "ip": ip}
    if port is not None:
        src["port"] = port
    if job:
        src["job"] = job
    if labels:
        src["labels"] = labels
    return src


# Accept only real targets for "instance" (ip:port / host:port / ipv6 forms)
_INSTANCE_RE = re.compile(
    r"""
    ^(
        \[[0-9a-fA-F:]+\](:\d+)? |          # [::1]:9182
        [A-Za-z0-9\.\-]+:\d+ |              # host:port
        \d{1,3}(\.\d{1,3}){3}(:\d+)?         # ipv4[:port]
    )$
    """,
    re.VERBOSE,
)


def looks_like_instance(value: Optional[str]) -> bool:
    """Return True if value looks like a Prometheus instance label."""
    if not value:
        return False
    return bool(_INSTANCE_RE.match(value.strip()))
