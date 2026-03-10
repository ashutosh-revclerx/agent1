from pydantic import BaseModel
from typing import Optional, Dict

class Target(BaseModel):
    name: str = "My Server"
    endpoint: str  # e.g. "192.168.1.5:9100"
    labels: Optional[Dict[str, str]] = None
    enabled: bool = True


