from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from jose import JWTError, jwt
from app.config import settings

logger = logging.getLogger(__name__)

def create_access_token(
    user_id: str,
    org_id: str,
    role: str,
    username: str,
    expires_delta: Optional[timedelta] = None
) -> str:
    """Generate a stateless JWT access token.
    
    Carries user_id (sub), org_id, role, and username.
    """
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
        
    to_encode = {
        "jti": str(uuid.uuid4()),
        "sub": user_id,
        "org_id": org_id,
        "role": role,
        "username": username,
        "exp": expire,
        "type": "access"
    }
    
    encoded_jwt = jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return encoded_jwt

def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Decode and validate a JWT access token."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm]
        )
        # Verify it is an access token
        if payload.get("type") != "access":
            return None
        return payload
    except JWTError as e:
        logger.debug(f"JWT decode error: {e}")
        return None
