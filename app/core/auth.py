"""
Authentication Utilities
JWT token generation, validation, and password hashing
"""
import os
from datetime import datetime, timedelta
from typing import Optional

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from bson import ObjectId

from app.services.mongodb_service import get_db
from app.schemas.user import User, TokenData
from app.core.logging import logger

# Password hashing with Argon2 (Production-grade settings)
ph = PasswordHasher(
    time_cost=3,        # Number of iterations (production: 3-4)
    memory_cost=65536,  # Memory usage in KiB (production: 65536)
    parallelism=4       # Number of parallel threads (production: 4)
)

# JWT settings
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-this-in-production")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

# Security scheme
security = HTTPBearer()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its Argon2 hash"""
    try:
        ph.verify(hashed_password, plain_password)
        return True
    except VerifyMismatchError:
        return False


def get_password_hash(password: str) -> str:
    """Hash a password using Argon2"""
    return ph.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT access token"""
    to_encode = data.copy()
    to_encode["type"] = "access"  # Mark as access token
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def create_refresh_token(user_id: str, session_id: str) -> str:
    """Create JWT refresh token with longer expiry"""
    to_encode = {
        "user_id": user_id,
        "session_id": session_id,
        "type": "refresh"
    }
    
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire})
    
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_refresh_token(token: str) -> dict:
    """Decode and validate refresh token"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        
        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        user_id: str = payload.get("user_id")
        session_id: str = payload.get("session_id")
        
        if not user_id or not session_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        return {"user_id": user_id, "session_id": session_id}
    
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def decode_access_token(token: str) -> TokenData:
    """Decode and validate JWT token"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("user_id")
        username: str = payload.get("username")
        
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        return TokenData(user_id=user_id, username=username)
    
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> User:
    """
    Dependency to get current authenticated user.
    Maintains compatibility with local JWTs but prefers Firebase ID tokens.
    """
    token = credentials.credentials
    db = get_db()
    
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable"
        )

    # 1. Try Firebase Token Verification
    from app.core.firebase import verify_firebase_token
    firebase_user = verify_firebase_token(token)
    
    if firebase_user:
        email = firebase_user.get("email")
        if not email:
            raise HTTPException(status_code=401, detail="Firebase token missing email")
            
        # Find user in our DB by email
        user_doc = db.users.find_one({"email": email})
        if not user_doc:
            # Auto-provision user if they exist in Firebase but not in our DB
            logger.info(f"[Auth] Auto-provisioning user for Firebase email: {email}")
            user_doc = {
                "username": email.split("@")[0],
                "email": email,
                "firebase_uid": firebase_user.get("uid"),
                "active": True,
                "created_at": datetime.utcnow()
            }
            res = db.users.insert_one(user_doc)
            user_doc["_id"] = res.inserted_id

        return User(
            id=str(user_doc["_id"]),
            username=user_doc["username"],
            email=user_doc["email"],
            active=user_doc.get("active", True)
        )

    # 2. Fallback to Local JWT
    try:
        token_data = decode_access_token(token)
        user_doc = db.users.find_one({"_id": ObjectId(token_data.user_id)})
        
        if not user_doc:
            raise HTTPException(status_code=401, detail="User not found")
            
        if not user_doc.get("active", True):
            raise HTTPException(status_code=403, detail="User account is inactive")
            
        return User(
            id=str(user_doc["_id"]),
            username=user_doc["username"],
            email=user_doc["email"],
            active=user_doc.get("active", True)
        )
    except Exception as e:
        logger.error(f"[Auth] JWT fallback failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False))
) -> Optional[User]:
    """
    Optional authentication - returns None if no token provided.
    Useful for endpoints that work with or without authentication.
    """
    if credentials is None:
        return None
    
    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None
