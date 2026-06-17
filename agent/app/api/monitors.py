from __future__ import annotations

import asyncio
import logging
import requests
from typing import Any
from uuid import UUID
from sqlalchemy import select

from app.db.base import SessionLocal
from app.db.models import Repository, SeenFailure, PlatformType
from app.api.utils import get_platform_credentials
from app.agent_runtime import analyze_failure_log

logger = logging.getLogger(__name__)


async def poll_github_repo(
    repo: Repository,
    db: Any,
    seen_run_ids: set[str],
    is_initialized: bool,
    broadcast_fn: Any
) -> None:
    repo_name = repo.name
    if "/" not in repo_name:
        return

    owner, name = repo_name.split("/", 1)
    creds = await get_platform_credentials("github", repo_name, repo.org_id, db)
    api_url = creds.get("url") or "https://api.github.com"
    token = creds.get("token")
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    url = f"{api_url}/repos/{owner}/{name}/actions/runs"
    try:
        response = requests.get(url, headers=headers, params={"per_page": 5}, timeout=10)
        if response.status_code != 200:
            broadcast_fn({
                "event": "monitor_status",
                "repo": repo_name,
                "status": "error",
                "message": f"HTTP Error {response.status_code}"
            })
            return
        
        runs = response.json().get("workflow_runs", [])
        
        broadcast_fn({
            "event": "monitor_status",
            "repo": repo_name,
            "status": "healthy"
        })

        db_modified = False
        for run in runs:
            run_id = str(run.get("id"))
            conclusion = run.get("conclusion")
            status = run.get("status")

            if status == "completed" and conclusion == "failure" and run_id not in seen_run_ids:
                new_seen = SeenFailure(
                    org_id=repo.org_id,
                    repo_id=repo.id,
                    platform=repo.platform,
                    repo_name=repo.name,
                    run_id=run_id
                )
                db.add(new_seen)
                seen_run_ids.add(run_id)
                db_modified = True

                if is_initialized:
                    # Fetch failed log
                    log_url = f"{api_url}/repos/{owner}/{name}/actions/runs/{run_id}/logs"
                    log_res = requests.get(log_url, headers=headers, timeout=15)
                    log_text = ""
                    if log_res.status_code == 200:
                        import zipfile, io
                        try:
                            z = zipfile.ZipFile(io.BytesIO(log_res.content))
                            logs = []
                            for zname in sorted(z.namelist())[:3]:
                                if zname.endswith(".txt"):
                                    logs.append(z.read(zname).decode("utf-8", errors="replace"))
                            log_text = "\n".join(logs)[:8000]
                        except Exception:
                            pass

                    # Broadcast failure alert
                    broadcast_fn({
                        "event": "failure",
                        "platform": "github",
                        "repo": repo_name,
                        "id": run_id,
                        "title": run.get("name", "Workflow Run"),
                        "trigger": run.get("event", "push")
                    })

                    # Stream AI analysis in background
                    if log_text:
                        async def stream_analysis():
                            analysis_text = ""
                            async for chunk in analyze_failure_log(
                                log=log_text,
                                platform="GitHub Actions",
                                repo=repo_name,
                                job=run.get("name", "workflow"),
                                trigger=run.get("event", "push")
                            ):
                                analysis_text += chunk
                                broadcast_fn({
                                    "event": "analysis_chunk",
                                    "repo": repo_name,
                                    "id": run_id,
                                    "chunk": chunk
                                })
                        asyncio.create_task(stream_analysis())

        if db_modified:
            await db.commit()
    except Exception as exc:
        broadcast_fn({
            "event": "monitor_status",
            "repo": repo_name,
            "status": "error",
            "message": str(exc)
        })


async def poll_gitlab_repo(
    repo: Repository,
    db: Any,
    seen_run_ids: set[str],
    is_initialized: bool,
    broadcast_fn: Any
) -> None:
    project_id = repo.name
    creds = await get_platform_credentials("gitlab", project_id, repo.org_id, db)
    api_url = creds.get("url") or "https://gitlab.com"
    token = creds.get("token")
    headers = {}
    if token:
        headers["PRIVATE-TOKEN"] = token

    url = f"{api_url}/api/v4/projects/{project_id}/pipelines"
    try:
        response = requests.get(url, headers=headers, params={"per_page": 5}, timeout=10)
        if response.status_code != 200:
            broadcast_fn({
                "event": "monitor_status",
                "repo": project_id,
                "status": "error",
                "message": f"HTTP Error {response.status_code}"
            })
            return
        
        pipelines = response.json()

        broadcast_fn({
            "event": "monitor_status",
            "repo": project_id,
            "status": "healthy"
        })

        db_modified = False
        for pipe in pipelines:
            pipe_id = str(pipe.get("id"))
            status = pipe.get("status")

            if status == "failed" and pipe_id not in seen_run_ids:
                new_seen = SeenFailure(
                    org_id=repo.org_id,
                    repo_id=repo.id,
                    platform=repo.platform,
                    repo_name=repo.name,
                    run_id=pipe_id
                )
                db.add(new_seen)
                seen_run_ids.add(pipe_id)
                db_modified = True

                if is_initialized:
                    # Fetch failed trace log from first job
                    log_text = ""
                    try:
                        jobs_res = requests.get(f"{api_url}/api/v4/projects/{project_id}/pipelines/{pipe_id}/jobs", headers=headers, timeout=10)
                        if jobs_res.status_code == 200:
                            for job in jobs_res.json():
                                if job.get("status") == "failed":
                                    trace_res = requests.get(f"{api_url}/api/v4/projects/{project_id}/jobs/{job.get('id')}/trace", headers=headers, timeout=10)
                                    if trace_res.status_code == 200:
                                        log_text = trace_res.text[:8000]
                                        break
                    except Exception:
                        pass

                    # Broadcast failure
                    broadcast_fn({
                        "event": "failure",
                        "platform": "gitlab",
                        "repo": project_id,
                        "id": pipe_id,
                        "title": f"Pipeline #{pipe_id}",
                        "trigger": pipe.get("source", "unknown")
                    })

                    # Stream analysis
                    if log_text:
                        async def stream_analysis():
                            async for chunk in analyze_failure_log(
                                log=log_text,
                                platform="GitLab CI",
                                repo=project_id,
                                job=f"pipeline #{pipe_id}",
                                trigger=pipe.get("source", "unknown")
                            ):
                                broadcast_fn({
                                    "event": "analysis_chunk",
                                    "repo": project_id,
                                    "id": pipe_id,
                                    "chunk": chunk
                                })
                        asyncio.create_task(stream_analysis())

        if db_modified:
            await db.commit()
    except Exception as exc:
        broadcast_fn({
            "event": "monitor_status",
            "repo": project_id,
            "status": "error",
            "message": str(exc)
        })


async def poll_jenkins_repo(
    repo: Repository,
    db: Any,
    seen_run_ids: set[str],
    is_initialized: bool,
    broadcast_fn: Any
) -> None:
    job_name = repo.name
    creds = await get_platform_credentials("jenkins", job_name, repo.org_id, db)
    jenkins_url = creds.get("url") or ""
    user = creds.get("user") or ""
    token = creds.get("token") or ""
    if not jenkins_url:
        return

    url = f"{jenkins_url.rstrip('/')}/job/{job_name}/api/json"
    auth = (user, token) if user and token else None
    try:
        response = requests.get(url, params={"tree": "builds[number,result,building,url]"}, auth=auth, timeout=10)
        if response.status_code != 200:
            broadcast_fn({
                "event": "monitor_status",
                "repo": job_name,
                "status": "error",
                "message": f"HTTP Error {response.status_code}"
            })
            return
        
        builds = response.json().get("builds", [])

        broadcast_fn({
            "event": "monitor_status",
            "repo": job_name,
            "status": "healthy"
        })

        db_modified = False
        for build in builds:
            build_num = str(build.get("number"))
            result = build.get("result")

            if result == "FAILURE" and build_num not in seen_run_ids:
                new_seen = SeenFailure(
                    org_id=repo.org_id,
                    repo_id=repo.id,
                    platform=repo.platform,
                    repo_name=repo.name,
                    run_id=build_num
                )
                db.add(new_seen)
                seen_run_ids.add(build_num)
                db_modified = True

                if is_initialized:
                    # Fetch log
                    log_text = ""
                    try:
                        log_res = requests.get(f"{jenkins_url.rstrip('/')}/job/{job_name}/{build_num}/consoleText", auth=auth, timeout=10)
                        if log_res.status_code == 200:
                            log_text = log_res.text[:8000]
                    except Exception:
                        pass

                    # Broadcast failure
                    broadcast_fn({
                        "event": "failure",
                        "platform": "jenkins",
                        "repo": job_name,
                        "id": build_num,
                        "title": f"Build #{build_num}",
                        "trigger": "jenkins trigger"
                    })

                    # Stream analysis
                    if log_text:
                        async def stream_analysis():
                            async for chunk in analyze_failure_log(
                                log=log_text,
                                platform="Jenkins",
                                repo=job_name,
                                job=f"build #{build_num}",
                                trigger="poller"
                            ):
                                broadcast_fn({
                                    "event": "analysis_chunk",
                                    "repo": job_name,
                                    "id": build_num,
                                    "chunk": chunk
                                })
                        asyncio.create_task(stream_analysis())

        if db_modified:
            await db.commit()
    except Exception as exc:
        broadcast_fn({
            "event": "monitor_status",
            "repo": job_name,
            "status": "error",
            "message": str(exc)
        })


async def poll_azure_repo(
    repo: Repository,
    db: Any,
    seen_run_ids: set[str],
    is_initialized: bool,
    broadcast_fn: Any
) -> None:
    project_name = repo.name
    extra = repo.extra or {}
    pipeline_id = extra.get("pipeline_id")
    if not pipeline_id:
        return

    creds = await get_platform_credentials("azure", project_name, repo.org_id, db)
    org_url = creds.get("url") or ""
    pat = creds.get("token") or ""
    if not org_url:
        return

    url = f"{org_url.rstrip('/')}/{project_name}/_apis/pipelines/{pipeline_id}/runs"
    auth = ("", pat) if pat else None
    try:
        response = requests.get(url, params={"api-version": "7.1-preview.1", "$top": 5}, auth=auth, timeout=10)
        if response.status_code != 200:
            broadcast_fn({
                "event": "monitor_status",
                "repo": project_name,
                "status": "error",
                "message": f"HTTP Error {response.status_code}"
            })
            return
        
        runs = response.json().get("value", [])

        broadcast_fn({
            "event": "monitor_status",
            "repo": project_name,
            "status": "healthy"
        })

        db_modified = False
        for run in runs:
            run_id = str(run.get("id"))
            state = run.get("state")
            result = run.get("result")

            if state == "completed" and result == "failed" and run_id not in seen_run_ids:
                new_seen = SeenFailure(
                    org_id=repo.org_id,
                    repo_id=repo.id,
                    platform=repo.platform,
                    repo_name=repo.name,
                    run_id=run_id
                )
                db.add(new_seen)
                seen_run_ids.add(run_id)
                db_modified = True

                if is_initialized:
                    # Fetch log references
                    log_text = ""
                    try:
                        logs_url = f"{org_url.rstrip('/')}/{project_name}/_apis/pipelines/{pipeline_id}/runs/{run_id}/logs"
                        logs_res = requests.get(logs_url, params={"api-version": "7.1-preview.1"}, auth=auth, timeout=10)
                        if logs_res.status_code == 200:
                            logs_list = logs_res.json().get("value", [])
                            merged = []
                            for ref in logs_list[:3]:
                                ref_url = ref.get("url")
                                if ref_url:
                                    trace_res = requests.get(f"{ref_url}?$expand=signedContent", auth=auth, timeout=10)
                                    if trace_res.status_code == 200:
                                        merged.append(trace_res.text)
                            log_text = "\n".join(merged)[:8000]
                    except Exception:
                        pass

                    # Broadcast failure
                    broadcast_fn({
                        "event": "failure",
                        "platform": "azure",
                        "repo": project_name,
                        "id": run_id,
                        "title": run.get("name", f"Run #{run_id}"),
                        "trigger": "pipeline trigger"
                    })

                    # Stream analysis
                    if log_text:
                        async def stream_analysis():
                            async for chunk in analyze_failure_log(
                                log=log_text,
                                platform="Azure DevOps",
                                repo=project_name,
                                job=run.get("name", "pipeline"),
                                trigger="poller"
                            ):
                                broadcast_fn({
                                    "event": "analysis_chunk",
                                    "repo": project_name,
                                    "id": run_id,
                                    "chunk": chunk
                                })
                        asyncio.create_task(stream_analysis())

        if db_modified:
            await db.commit()
    except Exception as exc:
        broadcast_fn({
            "event": "monitor_status",
            "repo": project_name,
            "status": "error",
            "message": str(exc)
        })


async def monitor_poller_loop(broadcast_fn: Any, interval: int = 60) -> None:
    """Background polling task that checks all user-configured repositories in the database."""
    logger.info("Dashboard background monitors poller started.")
    
    # Track which repositories have been initialized in this process lifecycle
    # to prevent backfilling historic failures with alerts on startup.
    initialized_repos: set[UUID] = set()

    while True:
        try:
            async with SessionLocal() as db:
                # Query all active repositories
                stmt = select(Repository).where(Repository.is_active == True)
                res = await db.execute(stmt)
                repos = res.scalars().all()
                
                for repo in repos:
                    try:
                        # 1. Fetch seen failures from the DB for this repository
                        seen_stmt = select(SeenFailure.run_id).where(
                            SeenFailure.org_id == repo.org_id,
                            SeenFailure.platform == repo.platform,
                            SeenFailure.repo_name == repo.name
                        )
                        seen_res = await db.execute(seen_stmt)
                        seen_run_ids = set(seen_res.scalars().all())
                        
                        is_initialized = repo.id in initialized_repos
                        if not is_initialized:
                            initialized_repos.add(repo.id)
                            
                        # 2. Poll repository depending on platform
                        if repo.platform == PlatformType.github:
                            await poll_github_repo(repo, db, seen_run_ids, is_initialized, broadcast_fn)
                        elif repo.platform == PlatformType.gitlab:
                            await poll_gitlab_repo(repo, db, seen_run_ids, is_initialized, broadcast_fn)
                        elif repo.platform == PlatformType.jenkins:
                            await poll_jenkins_repo(repo, db, seen_run_ids, is_initialized, broadcast_fn)
                        elif repo.platform == PlatformType.azure_devops:
                            await poll_azure_repo(repo, db, seen_run_ids, is_initialized, broadcast_fn)
                            
                    except Exception as repo_exc:
                        logger.error(f"Error polling repository {repo.platform}/{repo.name}: {repo_exc}", exc_info=True)
                        
        except Exception as exc:
            logger.error("Error in dashboard monitors poller loop: %s", exc, exc_info=True)
            
        await asyncio.sleep(interval)


def start_dashboard_monitors(broadcast_fn: Any, event_loop: asyncio.AbstractEventLoop) -> None:
    """Spawns the dashboard monitor loop in the FastAPI event loop."""
    asyncio.run_coroutine_threadsafe(
        monitor_poller_loop(broadcast_fn),
        event_loop
    )
