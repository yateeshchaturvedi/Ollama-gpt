from __future__ import annotations

import logging
from typing import Any, Literal, Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.dependencies import get_db
from app.db.models import Repository, PlatformCredential, PlatformType
from app.auth.dependencies import require_viewer_or_above, require_admin
from app.api.db_utils import ensure_encryption_key, check_plan_limit

logger = logging.getLogger(__name__)

router = APIRouter()


class RepoConfig(BaseModel):
    id: Optional[UUID] = None
    type: Literal["github", "gitlab", "jenkins", "azure"]
    name: str  # e.g., "owner/repo", "my-gitlab-project", "JenkinsJobName"
    url: Optional[str] = None
    token: Optional[str] = None # Deprecated inline token
    credential_id: Optional[UUID] = None
    extra: dict[str, Any] = Field(default_factory=dict)

class DiscoverResponseItem(BaseModel):
    name: str
    url: Optional[str] = None
    already_added: bool = False

class BulkImportRequest(BaseModel):
    platform: Literal["github", "gitlab", "jenkins", "azure"]
    names: List[str]
    credential_id: UUID
    extra: dict[str, Any] = Field(default_factory=dict)


@router.get("", response_model=List[RepoConfig])
async def list_repos(
    db: AsyncSession = Depends(get_db),
    current_user: Dict[str, Any] = Depends(require_viewer_or_above)
):
    """List all configured repositories (with sensitive tokens masked)."""
    org_id = UUID(current_user["org_id"])
    
    # Query all active repositories with their linked credentials
    stmt = (
        select(Repository, PlatformCredential)
        .outerjoin(PlatformCredential, Repository.credential_id == PlatformCredential.id)
        .where(
            Repository.org_id == org_id,
            Repository.is_active == True
        )
    )
    res = await db.execute(stmt)
    rows = res.all()
    
    result = []
    for repo, cred in rows:
        # Map DB PlatformType enum back to API Literal
        api_type = "azure" if repo.platform == PlatformType.azure_devops else repo.platform
        
        token_val = None
        url_val = None
        if cred:
            token_val = "********" if cred.token_encrypted else None
            url_val = cred.api_url
            
        result.append(
            RepoConfig(
                id=repo.id,
                type=api_type,
                name=repo.name,
                url=url_val,
                token=token_val,
                extra=repo.extra or {}
            )
        )
    return result


@router.post("", response_model=RepoConfig, status_code=status.HTTP_201_CREATED)
async def add_repo(
    repo: RepoConfig,
    db: AsyncSession = Depends(get_db),
    current_user: Dict[str, Any] = Depends(require_admin)
):
    """Add a new repository configuration using an existing org-level credential."""
    org_id = UUID(current_user["org_id"])
    user_id = UUID(current_user["sub"])
    
    # Enforce plan limit
    can_add = await check_plan_limit(org_id, db, "repos")
    if not can_add:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your organization has reached the maximum number of repositories allowed by its plan."
        )
    
    db_platform = PlatformType.azure_devops if repo.type == "azure" else PlatformType(repo.type)
    
    # Check if duplicate name + platform exists for this org
    stmt = select(Repository).where(
        Repository.org_id == org_id,
        Repository.platform == db_platform,
        Repository.name == repo.name,
        Repository.is_active == True
    )
    dup = await db.execute(stmt)
    if dup.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Repo '{repo.name}' of type '{repo.type}' already exists."
        )
        
    # Verify credential belongs to org
    if repo.credential_id:
        cred_stmt = select(PlatformCredential).where(
            PlatformCredential.id == repo.credential_id,
            PlatformCredential.org_id == org_id,
            PlatformCredential.is_active == True
        )
        if not (await db.execute(cred_stmt)).scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Credential not found or not active")

    # Create the Repository record
    new_repo = Repository(
        org_id=org_id,
        created_by=user_id,
        platform=db_platform,
        name=repo.name,
        credential_id=repo.credential_id,
        extra=repo.extra or {},
        is_active=True
    )
    db.add(new_repo)
    await db.commit()
    await db.refresh(new_repo)
    
    return RepoConfig(
        id=new_repo.id,
        type=repo.type,
        name=new_repo.name,
        credential_id=new_repo.credential_id,
        extra=new_repo.extra or {}
    )


@router.put("/{repo_id}", response_model=RepoConfig)
async def update_repo(
    repo_id: UUID,
    repo: RepoConfig,
    db: AsyncSession = Depends(get_db),
    current_user: Dict[str, Any] = Depends(require_admin)
):
    """Update an existing repository configuration."""
    org_id = UUID(current_user["org_id"])
    user_id = UUID(current_user["sub"])
    
    stmt = select(Repository).where(
        Repository.id == repo_id,
        Repository.org_id == org_id,
        Repository.is_active == True
    )
    existing_repo = (await db.execute(stmt)).scalar_one_or_none()
    if not existing_repo:
        raise HTTPException(status_code=404, detail=f"Repo with ID '{repo_id}' not found.")
        
    db_platform = PlatformType.azure_devops if repo.type == "azure" else PlatformType(repo.type)
    
    if repo.credential_id:
        cred_stmt = select(PlatformCredential).where(
            PlatformCredential.id == repo.credential_id,
            PlatformCredential.org_id == org_id,
            PlatformCredential.is_active == True
        )
        if not (await db.execute(cred_stmt)).scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Credential not found or not active")

    existing_repo.name = repo.name
    existing_repo.platform = db_platform
    existing_repo.credential_id = repo.credential_id
    existing_repo.extra = repo.extra or {}
    existing_repo.updated_by = user_id
    
    await db.commit()
    
    return RepoConfig(
        id=existing_repo.id,
        type=repo.type,
        name=existing_repo.name,
        credential_id=existing_repo.credential_id,
        extra=existing_repo.extra or {}
    )


@router.delete("/{repo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_repo(
    repo_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Dict[str, Any] = Depends(require_admin)
):
    """Remove a repository configuration (but keep the shared org-level credential)."""
    org_id = UUID(current_user["org_id"])
    
    stmt = select(Repository).where(
        Repository.id == repo_id,
        Repository.org_id == org_id,
        Repository.is_active == True
    )
    res = await db.execute(stmt)
    repo = res.scalar_one_or_none()
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repo with ID '{repo_id}' not found."
        )
            
    await db.delete(repo)
    await db.commit()
    return None

import httpx
@router.get("/discover", response_model=List[DiscoverResponseItem])
async def discover_repos(
    platform: Literal["github", "gitlab", "jenkins", "azure"],
    credential_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Dict[str, Any] = Depends(require_viewer_or_above)
):
    org_id = UUID(current_user["org_id"])
    db_platform = PlatformType.azure_devops if platform == "azure" else PlatformType(platform)

    # 1. Fetch the credential
    await ensure_encryption_key(db)
    stmt = select(
        PlatformCredential.api_url,
        func.pgp_sym_decrypt(
            PlatformCredential.token_encrypted,
            func.current_setting('app.encryption_key')
        ).label("token")
    ).where(
        PlatformCredential.id == credential_id,
        PlatformCredential.org_id == org_id,
        PlatformCredential.platform == db_platform,
        PlatformCredential.is_active == True
    )
    row = (await db.execute(stmt)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Credential not found")
        
    api_url, token = row
    
    # 2. Fetch existing repos to mark as already_added
    existing_stmt = select(Repository.name).where(
        Repository.org_id == org_id,
        Repository.platform == db_platform,
        Repository.is_active == True
    )
    existing_names = set((await db.execute(existing_stmt)).scalars().all())
    
    results = []
    
    # 3. Platform specific fetching
    try:
        async with httpx.AsyncClient() as client:
            if platform == "github":
                headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
                if token: headers["Authorization"] = f"Bearer {token}"
                url = f"{api_url or 'https://api.github.com'}/user/repos?per_page=100&affiliation=owner,collaborator,organization_member"
                res = await client.get(url, headers=headers, timeout=10.0)
                res.raise_for_status()
                for r in res.json():
                    name = r.get("full_name")
                    results.append(DiscoverResponseItem(name=name, url=r.get("html_url"), already_added=name in existing_names))
                    
            elif platform == "gitlab":
                headers = {"PRIVATE-TOKEN": token} if token else {}
                url = f"{api_url or 'https://gitlab.com'}/api/v4/projects?membership=true&per_page=100"
                res = await client.get(url, headers=headers, timeout=10.0)
                res.raise_for_status()
                for p in res.json():
                    name = p.get("path_with_namespace")
                    results.append(DiscoverResponseItem(name=name, url=p.get("web_url"), already_added=name in existing_names))
                    
            elif platform == "jenkins":
                if not api_url:
                    raise HTTPException(status_code=400, detail="Jenkins credential must have an API URL")
                cred_full = (await db.execute(select(PlatformCredential).where(PlatformCredential.id == credential_id))).scalar_one()
                auth = (cred_full.jenkins_username, token) if cred_full.jenkins_username and token else None
                
                url = f"{api_url.rstrip('/')}/api/json?tree=jobs[name,url]"
                res = await client.get(url, auth=auth, timeout=10.0)
                res.raise_for_status()
                for j in res.json().get("jobs", []):
                    name = j.get("name")
                    results.append(DiscoverResponseItem(name=name, url=j.get("url"), already_added=name in existing_names))
                    
            elif platform == "azure":
                if not api_url:
                    raise HTTPException(status_code=400, detail="Azure DevOps credential must have an Organization URL")
                auth = ("", token) if token else None
                url = f"{api_url.rstrip('/')}/_apis/projects?api-version=7.1-preview.1"
                res = await client.get(url, auth=auth, timeout=10.0)
                res.raise_for_status()
                for p in res.json().get("value", []):
                    proj_name = p.get("name")
                    # Now fetch pipelines for this project
                    pipe_url = f"{api_url.rstrip('/')}/{proj_name}/_apis/pipelines?api-version=7.1-preview.1"
                    try:
                        pipe_res = await client.get(pipe_url, auth=auth, timeout=5.0)
                        if pipe_res.status_code == 200:
                            for pipe in pipe_res.json().get("value", []):
                                pipe_name = pipe.get("name")
                                full_name = f"{proj_name}/{pipe_name}"
                                results.append(DiscoverResponseItem(name=full_name, already_added=full_name in existing_names))
                    except Exception:
                        pass
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code if e.response else 500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        
    return results


@router.post("/import", response_model=List[RepoConfig])
async def bulk_import_repos(
    req: BulkImportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Dict[str, Any] = Depends(require_admin)
):
    org_id = UUID(current_user["org_id"])
    user_id = UUID(current_user["sub"])
    db_platform = PlatformType.azure_devops if req.platform == "azure" else PlatformType(req.platform)
    
    # Enforce plan limit for each new repo added
    # But it's better to check if current + len(req.names) > max_repos, but req.names might include duplicates.
    # We will do a generic plan limit check during the loop.
    
    # Verify credential
    cred_stmt = select(PlatformCredential).where(
        PlatformCredential.id == req.credential_id,
        PlatformCredential.org_id == org_id,
        PlatformCredential.is_active == True
    )
    if not (await db.execute(cred_stmt)).scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Credential not found")
        
    # Find existing
    existing_stmt = select(Repository.name).where(
        Repository.org_id == org_id,
        Repository.platform == db_platform,
        Repository.name.in_(req.names),
        Repository.is_active == True
    )
    existing_names = set((await db.execute(existing_stmt)).scalars().all())
    
    added_repos = []
    for name in req.names:
        if name in existing_names:
            continue
            
        # Check limit per repo to prevent exceeding
        if not await check_plan_limit(org_id, db, "repos"):
            # Only raise if we haven't added anything, else just stop adding and commit what we have
            if not added_repos:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Your organization has reached the maximum number of repositories allowed by its plan."
                )
            break
            
        extra = dict(req.extra)
        if req.platform == "azure" and "/" in name:
            # We don't have pipeline ID automatically here, but we can set it to a placeholder or try to parse if provided
            pass
            
        new_repo = Repository(
            org_id=org_id,
            created_by=user_id,
            platform=db_platform,
            name=name,
            credential_id=req.credential_id,
            extra=extra,
            is_active=True
        )
        db.add(new_repo)
        added_repos.append(new_repo)
        
    await db.commit()
    
    # Refresh to get IDs
    res = []
    for repo in added_repos:
        await db.refresh(repo)
        res.append(RepoConfig(
            id=repo.id,
            type=req.platform,
            name=repo.name,
            credential_id=repo.credential_id,
            extra=repo.extra or {}
        ))
        
    return res
