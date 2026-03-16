"""
Helper Utility Functions
"""
import json


def parse_json(text: str) -> dict:
    """
    Parse JSON from text, even if embedded in other text
    """
    if not text:
        return {}
    try:
        s, e = text.find("{"), text.rfind("}") + 1
        return json.loads(text[s:e]) if s != -1 and e > s else {}
    except Exception:
        return {}


def mask_webhook(url: str) -> str:
    """
    Mask webhook URL for logging
    """
    if not url:
        return ""
    return url[:30] + "..." + url[-8:] if len(url) > 45 else "***"
