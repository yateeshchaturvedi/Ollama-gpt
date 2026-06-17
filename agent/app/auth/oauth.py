from __future__ import annotations

import httpx
from typing import Dict, Any, Optional

from app.config import settings

async def get_github_authorize_url(state: Optional[str] = None) -> str:
    """Construct the GitHub OAuth authorize redirect URL."""
    scope = "read:user user:email"
    url = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={settings.github_client_id}"
        f"&redirect_uri={settings.github_redirect_uri}"
        f"&scope={scope}"
    )
    if state:
        url += f"&state={state}"
    return url

async def exchange_github_code(code: str) -> Optional[Dict[str, Any]]:
    """Exchange the authorization code for an access token from GitHub."""
    url = "https://github.com/login/oauth/access_token"
    headers = {"Accept": "application/json"}
    data = {
        "client_id": settings.github_client_id,
        "client_secret": settings.github_client_secret,
        "code": code,
        "redirect_uri": settings.github_redirect_uri,
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, data=data, timeout=15.0)
        if response.status_code != 200:
            return None
        res_data = response.json()
        if "error" in res_data:
            return None
        return res_data  # contains: access_token, token_type, scope, etc.

async def get_github_user_profile(access_token: str) -> Optional[Dict[str, Any]]:
    """Fetch GitHub user profile information.
    
    If primary email is private, fetches list of email addresses and selects primary verified email.
    """
    url = "https://api.github.com/user"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "User-Agent": "DevOps-AI-Agent-Portal"
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers, timeout=15.0)
        if response.status_code != 200:
            return None
        profile = response.json()
        
        # Fallback to email endpoint if primary email is private/missing
        if not profile.get("email"):
            emails_response = await client.get(f"{url}/emails", headers=headers, timeout=15.0)
            if emails_response.status_code == 200:
                emails = emails_response.json()
                primary_email = None
                for email_item in emails:
                    if email_item.get("primary") and email_item.get("verified"):
                        primary_email = email_item.get("email")
                        break
                if not primary_email and emails:
                    # Choose first verified, or just first email
                    verified_emails = [e.get("email") for e in emails if e.get("verified")]
                    primary_email = verified_emails[0] if verified_emails else emails[0].get("email")
                
                profile["email"] = primary_email
                
        return profile
