from __future__ import annotations

import uuid
import pytest
import httpx


from app.api.main import app
from app.config import settings
from sqlalchemy import select
from app.db.base import SessionLocal
from app.db.models import VerificationToken, User, Organisation

@pytest.mark.asyncio
async def test_full_auth_and_admin_flow():
    # We will use httpx AsyncClient to test the async endpoints of FastAPI
    # since we are running inside pytest and app uses async databases.
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Create a unique organization slug and username for testing
        test_id = uuid.uuid4().hex[:6]
        org_slug = f"test-org-{test_id}"
        username = f"user_{test_id}"
        email = f"user_{test_id}@example.com"
        password = "securePassword123!"

        # 1. REGISTER ORG & OWNER
        register_payload = {
            "org_slug": org_slug,
            "org_display_name": f"Test Org {test_id}",
            "email": email,
            "username": username,
            "password": password
        }
        
        reg_resp = await client.post("/api/auth/register", json=register_payload)
        assert reg_resp.status_code == 200, reg_resp.text
        reg_data = reg_resp.json()
        assert reg_data["status"] == "success"
        
        async with SessionLocal() as session:
            stmt = select(User).where(User.username == username)
            test_user = (await session.execute(stmt)).scalar()
            test_user.is_email_verified = True
            
            org_stmt = select(Organisation).where(Organisation.id == test_user.org_id)
            test_org = (await session.execute(org_stmt)).scalar()
            test_org.is_email_verified = True
            
            await session.commit()

        # 3. LOGIN
        login_payload = {
            "org_slug": org_slug,
            "username_or_email": username,
            "password": password
        }
        login_resp = await client.post("/api/auth/login", json=login_payload)
        assert login_resp.status_code == 200, login_resp.text
        login_data = login_resp.json()
        assert "access_token" in login_data
        assert "refresh_token" in login_data
        access_token = login_data["access_token"]
        refresh_token = login_data["refresh_token"]
        
        # Verify role and properties
        assert login_data["user"]["role"] == "owner"
        assert login_data["user"]["username"] == username

        # 4. ADMIN PORTAL CRUD: ADD CREDENTIAL (requires Authorization header)
        headers = {
            "Authorization": f"Bearer {access_token}"
        }
        cred_payload = {
            "platform": "github",
            "label": "Prod GitHub PAT",
            "token": "ghp_secure_secret_token_123456",
            "github_owner": "org-owner",
            "token_scopes": ["repo", "workflow"]
        }
        
        cred_resp = await client.post("/api/admin/credentials", json=cred_payload, headers=headers)
        assert cred_resp.status_code == 200, cred_resp.text
        cred_data = cred_resp.json()
        assert cred_data["label"] == "Prod GitHub PAT"
        assert cred_data["token_hint"] == "●●●● 3456" # verify masking/last 4 chars hint
        assert "ghp_secure_secret_token_123456" not in str(cred_data) # verify secret is never returned

        # 5. ADMIN PORTAL: LIST CREDENTIALS
        list_resp = await client.get("/api/admin/credentials", headers=headers)
        assert list_resp.status_code == 200, list_resp.text
        creds = list_resp.json()
        assert len(creds) >= 1
        assert creds[0]["label"] == "Prod GitHub PAT"
        assert "ghp_secure_secret_token_123456" not in str(creds)

        # 6. ROTATE REFRESH TOKEN
        refresh_payload = {
            "refresh_token": refresh_token
        }
        ref_resp = await client.post("/api/auth/refresh", json=refresh_payload)
        assert ref_resp.status_code == 200, ref_resp.text
        ref_data = ref_resp.json()
        assert "access_token" in ref_data
        assert "refresh_token" in ref_data
        
        new_access = ref_data["access_token"]
        new_refresh = ref_data["refresh_token"]
        assert new_access != access_token
        assert new_refresh != refresh_token

        # 7. REUSE ROTATED REFRESH TOKEN (THEFT DETECTION ALERT)
        # Reusing the old refresh token should trigger an exception and immediate eviction
        reuse_resp = await client.post("/api/auth/refresh", json=refresh_payload)
        assert reuse_resp.status_code == 401
        assert "Reuse of rotated refresh token detected" in reuse_resp.json()["detail"]

        # 8. LOGOUT
        logout_payload = {
            "refresh_token": new_refresh
        }
        logout_resp = await client.post("/api/auth/logout", json=logout_payload)
        assert logout_resp.status_code == 200
        assert logout_resp.json()["status"] == "success"
