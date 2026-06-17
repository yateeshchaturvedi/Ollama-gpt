from __future__ import annotations

from typing import Dict, Any, List, Optional
from fastapi import Depends, HTTPException, Request, WebSocket, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.auth.jwt import decode_access_token

security = HTTPBearer(auto_error=False)

async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Dict[str, Any]:
    """Stateless dependency to authenticate requests using JWT access tokens.
    
    Verifies token signature and claims without making a database query.
    Returns the decoded token claims (sub/user_id, org_id, role, username).
    """
    token = None
    if credentials:
        token = credentials.credentials
    elif "access_token" in request.cookies:
        token = request.cookies.get("access_token")

    if not token:
        raise HTTPException(
            status_code=401, 
            detail="Not authenticated"
        )
        
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=401, 
            detail="Invalid or expired authentication credentials"
        )
    return payload

async def get_current_user_ws(websocket: WebSocket) -> Optional[Dict[str, Any]]:
    """Stateless dependency to authenticate WebSocket requests."""
    token = websocket.cookies.get("access_token")
    if not token:
        # Check query params as fallback for clients without cookie support
        token = websocket.query_params.get("token")
        
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return None
        
    payload = decode_access_token(token)
    if not payload:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return None
    return payload

def require_role(allowed_roles: List[str]):
    """Parametric dependency to enforce user roles on route entry."""
    async def dependency(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        if current_user.get("role") not in allowed_roles:
            raise HTTPException(
                status_code=403, 
                detail="Access forbidden: insufficient permissions"
            )
        return current_user
    return dependency

# Helper dependencies for common role checks
require_admin = require_role(["owner", "admin"])
require_analyst_or_above = require_role(["owner", "admin", "analyst"])
require_viewer_or_above = require_role(["owner", "admin", "analyst", "viewer"])
