"""
Rate Limiting Middleware
Protects API endpoints from abuse and brute force attacks
"""
import os
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request, Response
from app.core.logging import logger

# Initialize rate limiter
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100/minute"],
    enabled=os.getenv("ENABLE_RATE_LIMITING", "true").lower() == "true"
)

# Rate limit configurations
AUTH_RATE_LIMIT = os.getenv("AUTH_RATE_LIMIT", "5/minute")
API_RATE_LIMIT = os.getenv("API_RATE_LIMIT", "100/minute")


async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> Response:
    """
    Custom handler for rate limit exceeded errors
    """
    client_ip = get_remote_address(request)
    logger.warning(f"[RateLimit] Rate limit exceeded for {client_ip} on {request.url.path}")
    
    return Response(
        content="Rate limit exceeded. Please try again in 60 seconds.",
        status_code=429,
        headers={"Retry-After": "60"}
    )
