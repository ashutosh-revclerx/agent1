from typing import Optional, Dict
from pydantic import BaseModel, Field, field_validator

# Hard limits — validated by Pydantic before the request reaches the endpoint
MAX_MESSAGE_LEN = 2_000      # characters
MAX_CONTEXT_KEYS = 10
MAX_CONTEXT_KEY_LEN = 50     # per key
MAX_CONTEXT_VALUE_LEN = 200  # per value (also enforced in endpoint sanitiser)


class ChatMessage(BaseModel):
    message: str = Field(
        ...,
        min_length=1,
        max_length=MAX_MESSAGE_LEN,
        description=f"User message. Max {MAX_MESSAGE_LEN} characters.",
    )
    context: Dict[str, str] = Field(
        default_factory=dict,
        description=(
            f"Optional key/value context. "
            f"Max {MAX_CONTEXT_KEYS} keys, "
            f"{MAX_CONTEXT_KEY_LEN} chars per key, "
            f"{MAX_CONTEXT_VALUE_LEN} chars per value."
        ),
    )
    session_id: Optional[str] = Field(
        default=None,
        max_length=64,
        description="Existing session ID to continue a conversation.",
    )

    @field_validator("context")
    @classmethod
    def validate_context(cls, v: dict) -> dict:
        if len(v) > MAX_CONTEXT_KEYS:
            raise ValueError(
                f"context may contain at most {MAX_CONTEXT_KEYS} keys, got {len(v)}"
            )
        for key, value in v.items():
            if not isinstance(key, str) or len(key) > MAX_CONTEXT_KEY_LEN:
                raise ValueError(
                    f"context key {key!r} exceeds {MAX_CONTEXT_KEY_LEN} characters"
                )
            if not isinstance(value, str) or len(value) > MAX_CONTEXT_VALUE_LEN:
                raise ValueError(
                    f"context value for key {key!r} exceeds {MAX_CONTEXT_VALUE_LEN} characters"
                )
        return v


class ChatResponse(BaseModel):
    response: str
    session_id: str