from pydantic import BaseModel, field_validator
from typing import Optional, Dict
import re

class Target(BaseModel):
    name: str = "My Server"
    endpoint: str  # e.g. "192.168.1.5:9100"
    labels: Optional[Dict[str, str]] = None
    enabled: bool = True
    
    @field_validator('endpoint')
    @classmethod
    def validate_endpoint(cls, v: str) -> str:
        """Validate endpoint is a valid host:port or IP:port format"""
        if not v or not isinstance(v, str):
            raise ValueError('Endpoint must be a non-empty string')
        
        # Check for basic IP:port or hostname:port format
        if ':' not in v:
            raise ValueError('Endpoint must include port (e.g., 192.168.1.5:9100 or localhost:9100)')
        
        host, port_str = v.rsplit(':', 1)
        
        # Validate port is numeric
        try:
            port = int(port_str)
            if port < 1 or port > 65535:
                raise ValueError('Port must be between 1 and 65535')
        except ValueError:
            raise ValueError(f'Invalid port number: {port_str}')
        
        # Basic host validation (IP or hostname)
        if not host:
            raise ValueError('Host cannot be empty')
        
        return v


