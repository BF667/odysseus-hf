# routes/secrets_routes.py
"""FastAPI routes for HF Spaces Secrets management.

Provides REST endpoints for:
- Viewing the status of all known secrets/environment variables
- Adding/updating Space secrets via the huggingface_hub API
- Deleting Space secrets
- Listing current Space secrets (names only — values are never exposed)

These routes enable the Odysseus UI to manage HF Space secrets without
requiring .env files, which are ephemeral in HF Spaces.
"""

import os
import logging
from typing import Optional
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)


# ── Request/Response models ────────────────────────────────────────────────

class AddSecretRequest(BaseModel):
    key: str
    value: str
    is_secret: bool = True  # True = sensitive (masked), False = plain variable

class DeleteSecretRequest(BaseModel):
    key: str
    is_secret: bool = True


# ── Route setup ────────────────────────────────────────────────────────────

def setup_secrets_routes() -> APIRouter:
    router = APIRouter(prefix="/api/secrets", tags=["secrets"])

    def _get_secrets_mgr(request: Request):
        """Get HfSecretsManager from app state."""
        mgr = getattr(request.app.state, "hf_secrets_manager", None)
        if not mgr:
            raise HTTPException(503, "HF Secrets manager not initialized")
        return mgr

    # ── Status ────────────────────────────────────────────────────────

    @router.get("/status")
    async def secrets_status(request: Request):
        """Get the current status of all known secrets/environment variables.

        This works everywhere — it reads from os.environ, so it shows what
        the running process actually has access to. In HF Spaces, secrets
        set via the Space Settings UI appear as environment variables.
        """
        from src.hf_secrets import get_secrets_status
        return get_secrets_status()

    # ── Space Secret Management ───────────────────────────────────────

    @router.get("/space")
    async def space_info(request: Request):
        """Get info about the current HF Space and secret management availability."""
        mgr = _get_secrets_mgr(request)
        return {
            "available": mgr.is_available,
            "space_id": mgr.space_id,
            "info": mgr.get_space_info() if mgr.is_available else None,
        }

    @router.get("/space/list")
    async def list_space_secrets(request: Request):
        """List all secrets/variables set on the Space (names only, no values).

        Only available when running in HF Spaces with a valid token.
        """
        mgr = _get_secrets_mgr(request)
        if not mgr.is_available:
            raise HTTPException(
                400,
                "Space secret management not available. "
                "Requires HF_TOKEN and SPACE_ID (running inside HF Spaces)."
            )
        try:
            secrets = mgr.list_space_secrets()
            return {"secrets": secrets}
        except Exception as e:
            raise HTTPException(500, f"Failed to list Space secrets: {e}")

    @router.post("/space/add")
    async def add_space_secret(request: Request, body: AddSecretRequest):
        """Add or update a secret/variable on the Space.

        This triggers a Space restart so the new value becomes available.
        Use is_secret=false for non-sensitive configuration values.
        """
        mgr = _get_secrets_mgr(request)
        if not mgr.is_available:
            raise HTTPException(
                400,
                "Space secret management not available. "
                "Requires HF_TOKEN and SPACE_ID (running inside HF Spaces)."
            )

        # Validate key name
        key = body.key.strip().upper()
        if not key or not key.replace("_", "").isalnum():
            raise HTTPException(400, "Invalid key name. Use UPPER_SNAKE_CASE with alphanumeric characters and underscores.")

        # Validate value
        if not body.value:
            raise HTTPException(400, "Value cannot be empty.")

        try:
            result = mgr.add_space_secret(key, body.value, is_secret=body.is_secret)
            return result
        except Exception as e:
            raise HTTPException(500, f"Failed to add Space secret: {e}")

    @router.post("/space/delete")
    async def delete_space_secret(request: Request, body: DeleteSecretRequest):
        """Delete a secret/variable from the Space.

        This triggers a Space restart. The key will no longer be available
        as an environment variable after restart.
        """
        mgr = _get_secrets_mgr(request)
        if not mgr.is_available:
            raise HTTPException(
                400,
                "Space secret management not available. "
                "Requires HF_TOKEN and SPACE_ID (running inside HF Spaces)."
            )

        key = body.key.strip().upper()
        if not key:
            raise HTTPException(400, "Key cannot be empty.")

        if not confirm_delete(key):
            pass  # We allow the delete

        try:
            result = mgr.delete_space_secret(key, is_secret=body.is_secret)
            return result
        except Exception as e:
            raise HTTPException(500, f"Failed to delete Space secret: {e}")

    def confirm_delete(key: str) -> bool:
        """Safety check — prevent deleting critical secrets."""
        # These are too dangerous to delete remotely
        critical = {"HF_TOKEN"}
        return key in critical

    # ── Local env helpers ─────────────────────────────────────────────

    @router.post("/local/set")
    async def set_local_env(request: Request, body: AddSecretRequest):
        """Set an environment variable in the current process (non-persistent).

        This is useful for testing or for non-HF-Spaces deployments where
        you want to set a variable without editing .env. The value is lost
        when the process restarts.
        """
        key = body.key.strip().upper()
        if not key or not key.replace("_", "").isalnum():
            raise HTTPException(400, "Invalid key name. Use UPPER_SNAKE_CASE.")

        os.environ[key] = body.value
        logger.info(f"Set local env var: {key}")

        # If this is an OAuth-related key, refresh the GitHub OAuth instance
        if key in ("GITHUB_CLIENT_ID", "GITHUB_CLIENT_SECRET"):
            try:
                from src.github_oauth import reset_github_oauth
                reset_github_oauth()
                logger.info("Refreshed GitHub OAuth instance with new credentials")
            except Exception as e:
                logger.warning(f"Failed to refresh GitHub OAuth: {e}")

        # If this is HF_TOKEN, refresh bucket storage
        if key == "HF_TOKEN":
            try:
                from src.hf_bucket_storage import reset_hf_bucket_storage
                reset_hf_bucket_storage(token=body.value)
                logger.info("Refreshed HF bucket storage with new token")
            except Exception as e:
                logger.warning(f"Failed to refresh HF bucket storage: {e}")

        return {"success": True, "key": key, "persistent": False}

    @router.post("/local/unset")
    async def unset_local_env(request: Request, body: DeleteSecretRequest):
        """Remove an environment variable from the current process."""
        key = body.key.strip().upper()
        if key in os.environ:
            del os.environ[key]
            logger.info(f"Unset local env var: {key}")
        return {"success": True, "key": key}

    return router
