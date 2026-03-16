"""
Authentication Endpoints
User registration, login, and profile management with refresh tokens and session management
"""
from datetime import datetime
from typing import List
from fastapi import APIRouter, HTTPException, Depends, status, Request
from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app.schemas.user import (
    UserRegister, UserLogin, Token, UserResponse, User,
    RefreshTokenRequest, SessionResponse
)
from app.core.auth import (
    get_password_hash,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    get_current_user
)
from app.core.session import (
    create_session,
    validate_session,
    revoke_session,
    revoke_all_sessions,
    get_user_sessions
)
from app.core.rate_limit import limiter, AUTH_RATE_LIMIT
from app.services.mongodb_service import get_db
from app.core.logging import logger
from app.core.time import now_ist, format_ist

router = APIRouter()


@router.post("/auth/register", response_model=Token, status_code=status.HTTP_201_CREATED)
@limiter.limit(AUTH_RATE_LIMIT)
async def register(request: Request, user_data: UserRegister):
    """
    Register a new user
    """
    db = get_db()
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable"
        )
    
    # Check if username already exists
    if db.users.find_one({"username": user_data.username}):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered"
        )
    
    # Check if email already exists
    if db.users.find_one({"email": user_data.email}):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Create user document
    created_at = now_ist()
    user_doc = {
        "username": user_data.username,
        "email": user_data.email,
        "password_hash": get_password_hash(user_data.password),
        "created_at": created_at,
        "created_at_str": format_ist(created_at, include_tz=True),
        "active": True,
        "settings": {
            "email_notifications": True,
            "slack_notifications": False
        }
    }
    
    try:
        result = db.users.insert_one(user_doc)
    except DuplicateKeyError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username or email already registered"
        )
    user_id = str(result.inserted_id)

    logger.info(f"[Auth] New user registered: {user_data.username} (ID: {user_id})")
    
    # Create session
    ip_address = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")
    session_id = create_session(user_id, ip_address, user_agent)
    
    # Create tokens
    access_token = create_access_token(
        data={"user_id": user_id, "username": user_data.username}
    )
    refresh_token = create_refresh_token(user_id, session_id)
    
    return Token(access_token=access_token, refresh_token=refresh_token)


@router.post("/auth/login", response_model=Token)
@limiter.limit(AUTH_RATE_LIMIT)
async def login(request: Request, credentials: UserLogin):
    """
    Login with username and password
    """
    db = get_db()
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable"
        )
    
    # Find user by username
    user_doc = db.users.find_one({"username": credentials.username})
    
    if not user_doc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password"
        )
    
    # Verify password
    if not verify_password(credentials.password, user_doc["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password"
        )
    
    # Check if user is active
    if not user_doc.get("active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )
    
    user_id = str(user_doc["_id"])
    logger.info(f"[Auth] User logged in: {credentials.username} (ID: {user_id})")
    
    # Create session
    ip_address = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")
    session_id = create_session(user_id, ip_address, user_agent)
    
    # Create tokens
    access_token = create_access_token(
        data={"user_id": user_id, "username": credentials.username}
    )
    refresh_token = create_refresh_token(user_id, session_id)
    
    return Token(access_token=access_token, refresh_token=refresh_token)


@router.get("/auth/me", response_model=UserResponse)
async def get_current_user_info(user: User = Depends(get_current_user)):
    """
    Get current authenticated user information
    """
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        active=user.active
    )


@router.post("/auth/refresh", response_model=Token)
async def refresh_token(token_request: RefreshTokenRequest):
    """
    Refresh access token using refresh token
    """
    # Decode and validate refresh token
    token_data = decode_refresh_token(token_request.refresh_token)
    user_id = token_data["user_id"]
    session_id = token_data["session_id"]
    
    # Validate session is still active
    if not validate_session(session_id, user_id):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has been revoked"
        )
    
    # Get user from database
    db = get_db()
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable"
        )
    
    user_doc = db.users.find_one({"_id": ObjectId(user_id)})
    if not user_doc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
    
    if not user_doc.get("active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )
    
    # Create new access token
    access_token = create_access_token(
        data={"user_id": user_id, "username": user_doc["username"]}
    )
    
    logger.info(f"[Auth] Token refreshed for user {user_id}")
    
    return Token(access_token=access_token)


@router.post("/auth/logout")
async def logout(token_request: RefreshTokenRequest, user: User = Depends(get_current_user)):
    """
    Logout and revoke refresh token/session
    """
    try:
        token_data = decode_refresh_token(token_request.refresh_token)
        session_id = token_data["session_id"]
        
        # Revoke the session
        revoked = revoke_session(session_id, user.id)
        
        if revoked:
            logger.info(f"[Auth] User {user.username} logged out, session {session_id} revoked")
            return {"message": "Logged out successfully"}
        else:
            return {"message": "Session already revoked"}
    
    except HTTPException:
        # Token already expired or invalid, that's fine
        return {"message": "Logged out successfully"}


@router.get("/auth/sessions", response_model=List[SessionResponse])
async def get_sessions(request: Request, user: User = Depends(get_current_user)):
    """
    Get all active sessions for the current user
    """
    sessions = get_user_sessions(user.id)
    
    # Get current session info to mark it
    current_ip = request.client.host if request.client else "unknown"
    current_ua = request.headers.get("user-agent", "unknown")
    
    response_sessions = []
    for session in sessions:
        is_current = (
            session["ip_address"] == current_ip and 
            session["user_agent"] == current_ua
        )
        
        response_sessions.append(SessionResponse(
            session_id=session["session_id"],
            device=session["device"],
            ip_address=session["ip_address"],
            created_at_str=session["created_at_str"],
            last_active_str=session["last_active_str"],
            is_current=is_current
        ))
    
    return response_sessions


@router.delete("/auth/sessions/{session_id}")
async def revoke_session_endpoint(session_id: str, user: User = Depends(get_current_user)):
    """
    Revoke a specific session
    """
    revoked = revoke_session(session_id, user.id)
    
    if revoked:
        logger.info(f"[Auth] Session {session_id} revoked by user {user.username}")
        return {"message": "Session revoked successfully"}
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found or already revoked"
        )


@router.post("/auth/sessions/revoke-all")
async def revoke_all_sessions_endpoint(
    request: Request,
    keep_current: bool = True,
    user: User = Depends(get_current_user)
):
    """
    Revoke all sessions except optionally the current one
    """
    current_session_id = None
    
    if keep_current:
        # Try to find current session
        current_ip = request.client.host if request.client else "unknown"
        current_ua = request.headers.get("user-agent", "unknown")
        sessions = get_user_sessions(user.id)
        
        for session in sessions:
            if session["ip_address"] == current_ip and session["user_agent"] == current_ua:
                current_session_id = session["session_id"]
                break
    
    count = revoke_all_sessions(user.id, except_session_id=current_session_id)
    
    logger.info(f"[Auth] Revoked {count} sessions for user {user.username}")
    
    return {"message": f"Revoked {count} session(s) successfully"}




