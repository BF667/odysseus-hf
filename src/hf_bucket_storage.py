# src/hf_bucket_storage.py
"""Hugging Face Storage Bucket integration for Odysseus.

Provides a storage abstraction layer that uses HF Storage Buckets (S3-like,
powered by Xet) as cloud storage. Users can create new buckets or select
existing ones for file storage, enabling seamless HF Spaces deployment.

API Reference: https://huggingface.co/docs/huggingface_hub/en/guides/buckets
"""

import os
import json
import logging
import asyncio
import tempfile
from datetime import datetime
from typing import Dict, Any, Optional, List
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Settings persistence
# ---------------------------------------------------------------------------

BUCKET_SETTINGS_FILE = os.path.join("data", "hf_bucket_settings.json")


def _load_bucket_settings() -> Dict[str, Any]:
    """Load HF bucket settings from disk."""
    if not os.path.exists(BUCKET_SETTINGS_FILE):
        return {}
    try:
        with open(BUCKET_SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning(f"Failed to load bucket settings: {e}")
        return {}


def _save_bucket_settings(settings: Dict[str, Any]) -> None:
    """Persist HF bucket settings to disk atomically."""
    os.makedirs(os.path.dirname(BUCKET_SETTINGS_FILE), exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=os.path.dirname(BUCKET_SETTINGS_FILE),
        prefix=".hf_bucket_settings-",
        suffix=".tmp",
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, BUCKET_SETTINGS_FILE)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# HfBucketStorage — main interface
# ---------------------------------------------------------------------------

class HfBucketStorage:
    """Manages Hugging Face Storage Buckets for Odysseus cloud storage.

    Features:
    - Create new HF buckets
    - List and select existing buckets
    - Upload / download / delete files in a bucket
    - Configure which bucket to use for storage
    - Sync local uploads to HF bucket

    All bucket operations use the `huggingface_hub` Python library.
    """

    def __init__(self, hf_token: Optional[str] = None):
        self._hf_token = hf_token or os.getenv("HF_TOKEN") or os.getenv("HUGGING_FACE_HUB_TOKEN")
        self._settings = _load_bucket_settings()
        self._api = None
        if self._hf_token:
            try:
                from huggingface_hub import HfApi
                self._api = HfApi(token=self._hf_token)
                logger.info("HfBucketStorage: initialized with HF token")
            except ImportError:
                logger.warning("huggingface_hub not installed — HF bucket features disabled")
            except Exception as e:
                logger.warning(f"HfBucketStorage: failed to initialize HfApi: {e}")

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_configured(self) -> bool:
        """True when an HF token and an active bucket are set."""
        return bool(self._hf_token and self._api and self.active_bucket_id)

    @property
    def active_bucket_id(self) -> Optional[str]:
        """The currently selected bucket ID (e.g. 'username/my-bucket')."""
        return self._settings.get("active_bucket_id")

    @property
    def hf_token(self) -> Optional[str]:
        return self._hf_token

    @property
    def settings(self) -> Dict[str, Any]:
        return dict(self._settings)

    # ------------------------------------------------------------------
    # Bucket CRUD
    # ------------------------------------------------------------------

    def list_buckets(self, namespace: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all available buckets in a namespace.

        Args:
            namespace: HF username or org. Defaults to the current user.

        Returns:
            List of dicts with keys: id, private, size, total_files, created_at
        """
        if not self._api:
            raise RuntimeError("HfApi not initialized — set HF_TOKEN first")
        from huggingface_hub import list_buckets
        buckets = []
        try:
            for b in list_buckets(namespace=namespace):
                buckets.append({
                    "id": b.id,
                    "private": getattr(b, "private", None),
                    "size": getattr(b, "size", 0),
                    "total_files": getattr(b, "total_files", 0),
                    "created_at": str(getattr(b, "created_at", "")),
                })
        except Exception as e:
            logger.error(f"Failed to list buckets: {e}")
            raise
        return buckets

    def create_bucket(
        self,
        name: str,
        private: bool = True,
        namespace: Optional[str] = None,
        region: Optional[str] = None,
        exist_ok: bool = True,
    ) -> Dict[str, Any]:
        """Create a new HF storage bucket.

        Args:
            name: Bucket name (no spaces, slug-friendly).
            private: Whether the bucket should be private.
            namespace: Owner org or username (defaults to current user).
            region: Storage region (e.g. "us").
            exist_ok: Don't error if bucket already exists.

        Returns:
            Dict with bucket info (id, uri, url).
        """
        if not self._api:
            raise RuntimeError("HfApi not initialized — set HF_TOKEN first")
        from huggingface_hub import create_bucket

        bucket_name = f"{namespace}/{name}" if namespace else name
        try:
            result = create_bucket(
                bucket_name,
                private=private,
                exist_ok=exist_ok,
                region=region,
                token=self._hf_token,
            )
            info = {
                "id": result.bucket_id,
                "uri": result.uri.to_uri() if hasattr(result.uri, "to_uri") else str(result.uri),
                "url": f"https://huggingface.co/buckets/{result.bucket_id}",
            }
            logger.info(f"Created/verified bucket: {info['id']}")
            return info
        except Exception as e:
            logger.error(f"Failed to create bucket: {e}")
            raise

    def get_bucket_info(self, bucket_id: str) -> Dict[str, Any]:
        """Get metadata about a bucket."""
        if not self._api:
            raise RuntimeError("HfApi not initialized — set HF_TOKEN first")
        from huggingface_hub import bucket_info
        try:
            info = bucket_info(bucket_id)
            return {
                "id": info.id,
                "private": getattr(info, "private", None),
                "size": getattr(info, "size", 0),
                "total_files": getattr(info, "total_files", 0),
                "created_at": str(getattr(info, "created_at", "")),
            }
        except Exception as e:
            logger.error(f"Failed to get bucket info for {bucket_id}: {e}")
            raise

    def delete_bucket(self, bucket_id: str) -> None:
        """Delete a bucket (irreversible!)."""
        if not self._api:
            raise RuntimeError("HfApi not initialized — set HF_TOKEN first")
        from huggingface_hub import delete_bucket
        try:
            delete_bucket(bucket_id)
            # If the deleted bucket was active, clear it
            if self.active_bucket_id == bucket_id:
                self._settings["active_bucket_id"] = None
                _save_bucket_settings(self._settings)
            logger.info(f"Deleted bucket: {bucket_id}")
        except Exception as e:
            logger.error(f"Failed to delete bucket {bucket_id}: {e}")
            raise

    # ------------------------------------------------------------------
    # Bucket selection / settings
    # ------------------------------------------------------------------

    def set_active_bucket(self, bucket_id: str) -> Dict[str, Any]:
        """Set the active bucket for storage operations.

        Also validates that the bucket exists and is accessible.
        """
        # Verify the bucket exists
        info = self.get_bucket_info(bucket_id)
        self._settings["active_bucket_id"] = bucket_id
        self._settings["active_bucket_set_at"] = datetime.utcnow().isoformat()
        _save_bucket_settings(self._settings)
        logger.info(f"Active bucket set to: {bucket_id}")
        return info

    def clear_active_bucket(self) -> None:
        """Remove the active bucket selection."""
        self._settings["active_bucket_id"] = None
        _save_bucket_settings(self._settings)
        logger.info("Active bucket cleared")

    # ------------------------------------------------------------------
    # File operations
    # ------------------------------------------------------------------

    def upload_file(
        self,
        local_path: str,
        remote_path: Optional[str] = None,
        bucket_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Upload a local file to the active (or specified) bucket.

        Args:
            local_path: Path to the local file.
            remote_path: Destination path in the bucket. Defaults to the filename.
            bucket_id: Override bucket. Defaults to active bucket.

        Returns:
            Dict with upload details.
        """
        bid = bucket_id or self.active_bucket_id
        if not bid:
            raise ValueError("No bucket selected — call set_active_bucket() first")
        if not os.path.exists(local_path):
            raise FileNotFoundError(f"Local file not found: {local_path}")

        if remote_path is None:
            remote_path = os.path.basename(local_path)

        from huggingface_hub import batch_bucket_files
        try:
            batch_bucket_files(
                bid,
                add=[(local_path, remote_path)],
                token=self._hf_token,
            )
            result = {
                "bucket_id": bid,
                "local_path": local_path,
                "remote_path": remote_path,
                "uri": f"hf://buckets/{bid}/{remote_path}",
                "uploaded_at": datetime.utcnow().isoformat(),
            }
            logger.info(f"Uploaded {local_path} → {bid}/{remote_path}")
            return result
        except Exception as e:
            logger.error(f"Failed to upload {local_path} to bucket: {e}")
            raise

    def upload_bytes(
        self,
        data: bytes,
        remote_path: str,
        bucket_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Upload raw bytes to a bucket.

        Args:
            data: Bytes to upload.
            remote_path: Destination path in the bucket.
            bucket_id: Override bucket.

        Returns:
            Dict with upload details.
        """
        bid = bucket_id or self.active_bucket_id
        if not bid:
            raise ValueError("No bucket selected — call set_active_bucket() first")

        from huggingface_hub import batch_bucket_files
        try:
            batch_bucket_files(bid, add=[(data, remote_path)], token=self._hf_token)
            result = {
                "bucket_id": bid,
                "remote_path": remote_path,
                "uri": f"hf://buckets/{bid}/{remote_path}",
                "size": len(data),
                "uploaded_at": datetime.utcnow().isoformat(),
            }
            logger.info(f"Uploaded {len(data)} bytes → {bid}/{remote_path}")
            return result
        except Exception as e:
            logger.error(f"Failed to upload bytes to bucket: {e}")
            raise

    def download_file(
        self,
        remote_path: str,
        local_path: Optional[str] = None,
        bucket_id: Optional[str] = None,
    ) -> str:
        """Download a file from a bucket.

        Args:
            remote_path: Path in the bucket.
            local_path: Local destination. Defaults to a temp file.
            bucket_id: Override bucket.

        Returns:
            Path to the downloaded file.
        """
        bid = bucket_id or self.active_bucket_id
        if not bid:
            raise ValueError("No bucket selected")

        if local_path is None:
            suffix = os.path.splitext(remote_path)[1] or ".bin"
            fd, local_path = tempfile.mkstemp(suffix=suffix, prefix="hf_download_")
            os.close(fd)

        from huggingface_hub import hf_bucket_download
        try:
            # Use the CLI-style cp via the hf buckets cp path
            # Fall back to HfFileSystem-based download
            import subprocess
            result = subprocess.run(
                ["hf", "buckets", "cp", f"hf://buckets/{bid}/{remote_path}", local_path],
                capture_output=True, text=True, timeout=300,
                env={**os.environ, "HF_TOKEN": self._hf_token or ""},
            )
            if result.returncode != 0:
                # Fallback: use HfFileSystem
                self._download_via_filesystem(bid, remote_path, local_path)
            logger.info(f"Downloaded {bid}/{remote_path} → {local_path}")
            return local_path
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Download timed out for {bid}/{remote_path}")
        except Exception as e:
            # Try HfFileSystem fallback
            try:
                return self._download_via_filesystem(bid, remote_path, local_path)
            except Exception as e2:
                logger.error(f"Failed to download {bid}/{remote_path}: {e2}")
                raise

    def _download_via_filesystem(self, bucket_id: str, remote_path: str, local_path: str) -> str:
        """Download a file using HfFileSystem."""
        try:
            from huggingface_hub import HfFileSystem
            fs = HfFileSystem(token=self._hf_token)
            uri = f"hf://buckets/{bucket_id}/{remote_path}"
            fs.get(uri, local_path)
            return local_path
        except ImportError:
            raise RuntimeError("huggingface_hub not available for filesystem download")
        except Exception as e:
            raise RuntimeError(f"HfFileSystem download failed: {e}")

    def list_files(
        self,
        prefix: Optional[str] = None,
        recursive: bool = True,
        bucket_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List files in a bucket.

        Args:
            prefix: Filter by path prefix.
            recursive: List recursively.
            bucket_id: Override bucket.

        Returns:
            List of dicts with path, size, type.
        """
        bid = bucket_id or self.active_bucket_id
        if not bid:
            raise ValueError("No bucket selected")

        from huggingface_hub import list_bucket_tree
        try:
            items = []
            for item in list_bucket_tree(bid, prefix=prefix, recursive=recursive, token=self._hf_token):
                items.append({
                    "path": item.path,
                    "size": getattr(item, "size", 0),
                    "type": getattr(item, "type", "file"),
                })
            return items
        except Exception as e:
            logger.error(f"Failed to list files in bucket {bid}: {e}")
            raise

    def delete_files(
        self,
        paths: List[str],
        bucket_id: Optional[str] = None,
    ) -> None:
        """Delete files from a bucket.

        Args:
            paths: List of remote paths to delete.
            bucket_id: Override bucket.
        """
        bid = bucket_id or self.active_bucket_id
        if not bid:
            raise ValueError("No bucket selected")

        from huggingface_hub import batch_bucket_files
        try:
            batch_bucket_files(bid, delete=paths, token=self._hf_token)
            logger.info(f"Deleted {len(paths)} files from {bid}")
        except Exception as e:
            logger.error(f"Failed to delete files from bucket: {e}")
            raise

    # ------------------------------------------------------------------
    # Bulk sync
    # ------------------------------------------------------------------

    def sync_directory(
        self,
        local_dir: str,
        remote_prefix: str = "",
        bucket_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Sync a local directory to a bucket (upload new/changed files).

        Uses hf buckets sync via CLI for efficiency.

        Args:
            local_dir: Local directory to sync.
            remote_prefix: Prefix in the bucket.
            bucket_id: Override bucket.

        Returns:
            Dict with sync results.
        """
        bid = bucket_id or self.active_bucket_id
        if not bid:
            raise ValueError("No bucket selected")

        import subprocess
        dest = f"hf://buckets/{bid}/{remote_prefix}".rstrip("/")
        try:
            result = subprocess.run(
                ["hf", "buckets", "sync", local_dir, dest],
                capture_output=True, text=True, timeout=600,
                env={**os.environ, "HF_TOKEN": self._hf_token or ""},
            )
            return {
                "bucket_id": bid,
                "local_dir": local_dir,
                "remote_prefix": remote_prefix,
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Sync timed out for {local_dir} → {bid}/{remote_prefix}")
        except Exception as e:
            logger.error(f"Failed to sync directory: {e}")
            raise

    # ------------------------------------------------------------------
    # Auth / token management
    # ------------------------------------------------------------------

    def update_token(self, token: str) -> None:
        """Update the HF token and reinitialize the API client."""
        self._hf_token = token
        try:
            from huggingface_hub import HfApi
            self._api = HfApi(token=token)
            logger.info("HF token updated successfully")
        except Exception as e:
            self._api = None
            logger.error(f"Failed to initialize HfApi with new token: {e}")
            raise

    def whoami(self) -> Optional[Dict[str, Any]]:
        """Return info about the authenticated HF user."""
        if not self._api:
            return None
        try:
            info = self._api.whoami()
            return {
                "name": info.get("name", ""),
                "fullname": info.get("fullname", ""),
                "is_pro": info.get("isPro", False),
                "organizations": [
                    org.get("name", "") for org in info.get("orgs", [])
                ] if isinstance(info.get("orgs"), list) else [],
            }
        except Exception as e:
            logger.debug(f"whoami failed: {e}")
            return None


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_instance: Optional[HfBucketStorage] = None


def get_hf_bucket_storage() -> HfBucketStorage:
    """Get or create the global HfBucketStorage singleton."""
    global _instance
    if _instance is None:
        _instance = HfBucketStorage()
    return _instance


def reset_hf_bucket_storage(token: Optional[str] = None) -> HfBucketStorage:
    """Reset and reinitialize the global HfBucketStorage."""
    global _instance
    _instance = HfBucketStorage(hf_token=token)
    return _instance
