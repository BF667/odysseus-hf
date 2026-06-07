# routes/bucket_routes.py
"""FastAPI routes for Hugging Face Storage Bucket management.

Provides REST endpoints for:
- Listing / creating / deleting buckets
- Selecting an active bucket
- Uploading / downloading / listing / deleting files in a bucket
- Syncing local uploads to cloud storage
- Getting bucket status and settings
"""

import os
import logging
from typing import Optional, List
from fastapi import APIRouter, Request, HTTPException, UploadFile, File
from pydantic import BaseModel

logger = logging.getLogger(__name__)


# ── Request/Response models ────────────────────────────────────────────────

class CreateBucketRequest(BaseModel):
    name: str
    private: bool = True
    namespace: Optional[str] = None
    region: Optional[str] = None

class SetActiveBucketRequest(BaseModel):
    bucket_id: str

class UploadToBucketRequest(BaseModel):
    remote_path: Optional[str] = None
    bucket_id: Optional[str] = None

class DeleteFilesRequest(BaseModel):
    paths: List[str]
    bucket_id: Optional[str] = None

class SyncDirectoryRequest(BaseModel):
    local_dir: str
    remote_prefix: str = ""
    bucket_id: Optional[str] = None

class UpdateTokenRequest(BaseModel):
    token: str


# ── Route setup ────────────────────────────────────────────────────────────

def setup_bucket_routes() -> APIRouter:
    router = APIRouter(prefix="/api/buckets", tags=["buckets"])

    def _get_storage(request: Request):
        """Get HfBucketStorage from app state."""
        storage = getattr(request.app.state, "hf_bucket_storage", None)
        if not storage:
            raise HTTPException(503, "HF Bucket storage not initialized")
        return storage

    # ── Status & Settings ──────────────────────────────────────────────

    @router.get("/status")
    async def bucket_status(request: Request):
        """Get the current bucket configuration status."""
        storage = _get_storage(request)
        whoami = await _run_in_thread(storage.whoami)
        return {
            "configured": storage.is_configured,
            "active_bucket_id": storage.active_bucket_id,
            "has_token": bool(storage.hf_token),
            "user": whoami,
            "settings": storage.settings,
        }

    @router.get("/settings")
    async def get_settings(request: Request):
        """Get current HF bucket settings."""
        storage = _get_storage(request)
        return storage.settings

    # ── Token Management ───────────────────────────────────────────────

    @router.post("/token")
    async def update_token(request: Request, body: UpdateTokenRequest):
        """Update the HF token."""
        storage = _get_storage(request)
        try:
            await _run_in_thread(storage.update_token, body.token)
            whoami = await _run_in_thread(storage.whoami)
            return {"success": True, "user": whoami}
        except Exception as e:
            raise HTTPException(400, f"Invalid token: {e}")

    # ── Bucket CRUD ────────────────────────────────────────────────────

    @router.get("/list")
    async def list_buckets(request: Request, namespace: Optional[str] = None):
        """List available buckets."""
        storage = _get_storage(request)
        try:
            buckets = await _run_in_thread(storage.list_buckets, namespace=namespace)
            return {"buckets": buckets}
        except RuntimeError as e:
            raise HTTPException(400, str(e))
        except Exception as e:
            raise HTTPException(500, f"Failed to list buckets: {e}")

    @router.post("/create")
    async def create_bucket(request: Request, body: CreateBucketRequest):
        """Create a new storage bucket."""
        storage = _get_storage(request)
        try:
            result = await _run_in_thread(
                storage.create_bucket,
                name=body.name,
                private=body.private,
                namespace=body.namespace,
                region=body.region,
            )
            return {"success": True, "bucket": result}
        except Exception as e:
            raise HTTPException(500, f"Failed to create bucket: {e}")

    @router.get("/info/{bucket_id:path}")
    async def get_bucket_info(request: Request, bucket_id: str):
        """Get metadata about a specific bucket."""
        storage = _get_storage(request)
        try:
            info = await _run_in_thread(storage.get_bucket_info, bucket_id)
            return info
        except Exception as e:
            raise HTTPException(404, f"Bucket not found: {e}")

    @router.delete("/delete/{bucket_id:path}")
    async def delete_bucket(request: Request, bucket_id: str):
        """Delete a bucket (irreversible!)."""
        storage = _get_storage(request)
        try:
            await _run_in_thread(storage.delete_bucket, bucket_id)
            return {"success": True, "deleted": bucket_id}
        except Exception as e:
            raise HTTPException(500, f"Failed to delete bucket: {e}")

    # ── Active Bucket Selection ────────────────────────────────────────

    @router.post("/select")
    async def select_bucket(request: Request, body: SetActiveBucketRequest):
        """Set the active bucket for storage operations."""
        storage = _get_storage(request)
        try:
            info = await _run_in_thread(storage.set_active_bucket, body.bucket_id)
            return {"success": True, "bucket": info}
        except Exception as e:
            raise HTTPException(400, f"Failed to select bucket: {e}")

    @router.post("/clear")
    async def clear_active_bucket(request: Request):
        """Clear the active bucket selection."""
        storage = _get_storage(request)
        await _run_in_thread(storage.clear_active_bucket)
        return {"success": True}

    # ── File Operations ────────────────────────────────────────────────

    @router.post("/upload")
    async def upload_file(
        request: Request,
        file: UploadFile = File(...),
        remote_path: Optional[str] = None,
        bucket_id: Optional[str] = None,
    ):
        """Upload a file to the active bucket."""
        storage = _get_storage(request)

        # Save to temp file first
        import tempfile
        suffix = os.path.splitext(file.filename or "upload")[1] or ".bin"
        fd, tmp_path = tempfile.mkstemp(suffix=suffix)
        try:
            content = await file.read()
            with os.fdopen(fd, "wb") as f:
                f.write(content)

            result = await _run_in_thread(
                storage.upload_file,
                local_path=tmp_path,
                remote_path=remote_path or file.filename,
                bucket_id=bucket_id,
            )
            return {"success": True, "upload": result}
        except ValueError as e:
            raise HTTPException(400, str(e))
        except Exception as e:
            raise HTTPException(500, f"Upload failed: {e}")
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    @router.get("/files")
    async def list_files(
        request: Request,
        prefix: Optional[str] = None,
        recursive: bool = True,
        bucket_id: Optional[str] = None,
    ):
        """List files in the active bucket."""
        storage = _get_storage(request)
        try:
            files = await _run_in_thread(
                storage.list_files,
                prefix=prefix,
                recursive=recursive,
                bucket_id=bucket_id,
            )
            return {"files": files}
        except ValueError as e:
            raise HTTPException(400, str(e))
        except Exception as e:
            raise HTTPException(500, f"Failed to list files: {e}")

    @router.post("/files/delete")
    async def delete_files(request: Request, body: DeleteFilesRequest):
        """Delete files from the active bucket."""
        storage = _get_storage(request)
        try:
            await _run_in_thread(
                storage.delete_files,
                paths=body.paths,
                bucket_id=body.bucket_id,
            )
            return {"success": True, "deleted_count": len(body.paths)}
        except ValueError as e:
            raise HTTPException(400, str(e))
        except Exception as e:
            raise HTTPException(500, f"Failed to delete files: {e}")

    @router.post("/sync")
    async def sync_directory(request: Request, body: SyncDirectoryRequest):
        """Sync a local directory to the bucket."""
        storage = _get_storage(request)
        try:
            result = await _run_in_thread(
                storage.sync_directory,
                local_dir=body.local_dir,
                remote_prefix=body.remote_prefix,
                bucket_id=body.bucket_id,
            )
            return result
        except ValueError as e:
            raise HTTPException(400, str(e))
        except Exception as e:
            raise HTTPException(500, f"Sync failed: {e}")

    # ── Sync uploads to bucket ─────────────────────────────────────────

    @router.post("/sync-uploads")
    async def sync_uploads_to_bucket(request: Request):
        """Sync the local uploads directory to the active bucket."""
        storage = _get_storage(request)
        upload_dir = os.path.join("data", "uploads")
        if not os.path.isdir(upload_dir):
            raise HTTPException(400, "No local uploads directory found")
        try:
            result = await _run_in_thread(
                storage.sync_directory,
                local_dir=upload_dir,
                remote_prefix="uploads",
            )
            return result
        except ValueError as e:
            raise HTTPException(400, str(e))
        except Exception as e:
            raise HTTPException(500, f"Upload sync failed: {e}")

    # ── Download proxy ─────────────────────────────────────────────────

    @router.get("/download/{bucket_id:path}/{remote_path:path}")
    async def download_file(
        request: Request,
        bucket_id: str,
        remote_path: str,
    ):
        """Download a file from a bucket and serve it."""
        storage = _get_storage(request)
        try:
            local_path = await _run_in_thread(
                storage.download_file,
                remote_path=remote_path,
                bucket_id=bucket_id,
            )
            from fastapi.responses import FileResponse
            import mimetypes
            mime = mimetypes.guess_type(remote_path)[0] or "application/octet-stream"
            return FileResponse(local_path, media_type=mime, filename=os.path.basename(remote_path))
        except ValueError as e:
            raise HTTPException(400, str(e))
        except Exception as e:
            raise HTTPException(500, f"Download failed: {e}")

    return router


# ── Helpers ────────────────────────────────────────────────────────────────

import asyncio

async def _run_in_thread(func, *args, **kwargs):
    """Run a synchronous function in a thread pool."""
    return await asyncio.to_thread(func, *args, **kwargs)
