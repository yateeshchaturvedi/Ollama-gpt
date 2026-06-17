from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Iterator
from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from fastapi.responses import FileResponse
from app.config import settings

router = APIRouter()


def _get_audit_log_path() -> Path:
    return Path(settings.tool_audit_log_path).resolve()

def reverse_read_lines(filepath: Path, buffer_size: int = 8192) -> Iterator[str]:
    """Read a file backwards line by line in chunks."""
    with open(filepath, "rb") as f:
        f.seek(0, os.SEEK_END)
        file_size = f.tell()
        remainder = b""
        
        position = file_size
        while position > 0:
            to_read = min(buffer_size, position)
            position -= to_read
            f.seek(position)
            chunk = f.read(to_read) + remainder
            
            lines = chunk.split(b"\n")
            remainder = lines.pop(0)
            
            for line in reversed(lines):
                if line:
                    yield line.decode("utf-8")
        if remainder:
            yield remainder.decode("utf-8")


@router.get("")
def get_logs(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=500),
    tool: str | None = None,
    allowed: bool | None = None,
    reason: str | None = None,
):
    """Get paginated and filtered list of audit log entries."""
    log_path = _get_audit_log_path()
    if not log_path.exists():
        return {"total": 0, "logs": [], "page": page, "per_page": per_page}

    paginated_entries = []
    total = 0
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page

    try:
        for line in reverse_read_lines(log_path):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                # Apply filters
                if tool and entry.get("tool") != tool:
                    continue
                if allowed is not None and entry.get("allowed") != allowed:
                    continue
                if reason and entry.get("reason") != reason:
                    continue
                
                if total >= start_idx and total < end_idx:
                    paginated_entries.append(entry)
                total += 1
            except Exception:
                continue
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read logs: {exc}")

    return {
        "total": total,
        "logs": paginated_entries,
        "page": page,
        "per_page": per_page
    }


@router.get("/download")
def download_logs():
    """Download the full audit log file."""
    log_path = _get_audit_log_path()
    if not log_path.exists():
        # Create empty file so we can return it
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.touch()

    return FileResponse(
        path=log_path,
        media_type="text/plain",
        filename="tool_audit.log"
    )


async def tail_audit_log_websocket(websocket: WebSocket):
    """Stream new audit log entries via WebSocket in real-time."""
    await websocket.accept()
    log_path = _get_audit_log_path()

    # If log file doesn't exist, create it or wait
    if not log_path.exists():
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.touch()

    try:
        # Open file and move pointer to end
        with open(log_path, "r", encoding="utf-8") as f:
            f.seek(0, 2)  # Seek to end
            while True:
                # Read new line
                line = f.readline()
                if not line:
                    await asyncio.sleep(0.5)
                    continue
                line = line.strip()
                if line:
                    try:
                        # Verify it is valid JSON before sending
                        json.loads(line)
                        await websocket.send_text(line)
                    except json.JSONDecodeError:
                        # Fallback to plain text if somehow corrupt
                        await websocket.send_text(json.dumps({"ts": 0, "message": line}))
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        try:
            await websocket.send_text(json.dumps({"error": str(exc)}))
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
