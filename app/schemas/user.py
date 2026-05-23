"""
User Authentication Schemas
"""
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, field_validator


class UserRegister(BaseModel):
    """User registration request"""
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=6)
    
    @field_validator('email')
    @classmethod
    def validate_email_format(cls, v: str) -> str:
        """Validate email format"""
        return v.lower()


class UserLogin(BaseModel):
    """User login request"""
    username: str
    password: str


class UserResponse(BaseModel):
    """User response (no password)"""
    id: str
    username: str
    email: str
    active: bool = True
    
    class Config:
        from_attributes = True


class Token(BaseModel):
    """JWT token response"""
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"


class RefreshTokenRequest(BaseModel):
    """Refresh token request"""
    refresh_token: str


class TokenData(BaseModel):
    """Token payload data"""
    user_id: Optional[str] = None
    username: Optional[str] = None
    session_id: Optional[str] = None


class User(BaseModel):
    """User model for dependency injection"""
    id: str
    username: str
    email: str
    active: bool = True
    session_id: Optional[str] = None


class SessionResponse(BaseModel):
    """Session information response"""
    session_id: str
    device: dict
    ip_address: str
    created_at_str: str
    last_active_str: str
    is_current: bool = False

