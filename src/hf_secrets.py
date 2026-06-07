# src/hf_secrets.py
"""Hugging Face Spaces Secrets management for Odysseus.

In HF Spaces, the container filesystem is ephemeral — .env files are wiped on
every rebuild.  Instead, HF Spaces provides a built-in Secrets mechanism:
secrets are set via the Space Settings UI (or the huggingface_hub API) and
injected as environment variables at runtime.

This module provides:
- Runtime detection of whether we're running inside HF Spaces
- Listing of required/optional secrets and their current status
- CRUD operations on Space secrets via the huggingface_hub API
  (add_space_secret / delete_space_secret / get_space_variables)
- A "secret status" endpoint that shows which secrets are set / missing

Reference: https://huggingface.co/docs/hub/spaces-overview#managing-secrets
"""

import os
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Secret definitions — every configurable key the app cares about
# ---------------------------------------------------------------------------

@dataclass
class SecretDef:
    """Definition of a secret/environment variable the app uses."""
    key: str
    label: str
    category: str  # "required", "recommended", "optional"
    description: str
    default: str = ""
    is_secret: bool = True  # True = sensitive (masked in UI), False = variable
    hf_spaces_only: bool = False  # Only relevant in HF Spaces


# All secrets/variables the app recognizes, in display order
SECRET_DEFINITIONS: List[SecretDef] = [
    # ── Required ─────────────────────────────────────────────────────────
    SecretDef(
        key="HF_TOKEN",
        label="HF API Token",
        category="required",
        description="Hugging Face API token with read+write permissions. Required for Storage Bucket access, model downloads, and Space secret management.",
        is_secret=True,
    ),
    # ── Recommended ──────────────────────────────────────────────────────
    SecretDef(
        key="GITHUB_CLIENT_ID",
        label="GitHub OAuth Client ID",
        category="recommended",
        description="GitHub OAuth App client ID for the GitHub integration (Settings → GitHub). Create an OAuth App at github.com/settings/developers.",
        is_secret=False,
    ),
    SecretDef(
        key="GITHUB_CLIENT_SECRET",
        label="GitHub OAuth Client Secret",
        category="recommended",
        description="GitHub OAuth App client secret. Keep this confidential — never commit it to source control.",
        is_secret=True,
    ),
    SecretDef(
        key="OAUTH_REDIRECT_BASE_URL",
        label="OAuth Redirect Base URL",
        category="recommended",
        description="Public URL of your Odysseus instance. Used to build the OAuth callback URL. For HF Spaces: https://{user}-{space}.hf.space",
        is_secret=False,
        default="",
    ),
    # ── Optional ─────────────────────────────────────────────────────────
    SecretDef(
        key="ODYSSEUS_HF_BUCKET",
        label="HF Bucket ID",
        category="optional",
        description="Pre-select an HF Storage Bucket (e.g. username/my-bucket). If not set, use the Buckets UI to create/select one.",
        is_secret=False,
    ),
    SecretDef(
        key="ODYSSEUS_AUTO_BUCKET",
        label="Auto-Create Bucket",
        category="optional",
        description="Set to '1' to auto-create an HF Storage Bucket on first startup. Requires HF_TOKEN.",
        is_secret=False,
        default="0",
    ),
    SecretDef(
        key="ODYSSEUS_BUCKET_REGION",
        label="Bucket Region",
        category="optional",
        description="Storage region for auto-created buckets (default: us).",
        is_secret=False,
        default="us",
    ),
    SecretDef(
        key="OPENAI_API_KEY",
        label="OpenAI API Key",
        category="optional",
        description="OpenAI API key for using OpenAI models (GPT-4, etc.).",
        is_secret=True,
    ),
    SecretDef(
        key="LLM_HOST",
        label="LLM Host",
        category="optional",
        description="Primary LLM host address (default: localhost).",
        is_secret=False,
        default="localhost",
    ),
    SecretDef(
        key="SEARXNG_INSTANCE",
        label="SearXNG Instance URL",
        category="optional",
        description="URL for your SearXNG search instance (default: http://localhost:8080).",
        is_secret=False,
        default="http://localhost:8080",
    ),
    SecretDef(
        key="CHROMADB_HOST",
        label="ChromaDB Host",
        category="optional",
        description="ChromaDB server host (default: localhost). In HF Spaces, an embedded instance runs locally.",
        is_secret=False,
        default="localhost",
    ),
    SecretDef(
        key="CHROMADB_PORT",
        label="ChromaDB Port",
        category="optional",
        description="ChromaDB server port (default: 8100).",
        is_secret=False,
        default="8100",
    ),
    SecretDef(
        key="EMBEDDING_URL",
        label="Embedding API URL",
        category="optional",
        description="OpenAI-compatible /v1/embeddings endpoint for vector embeddings.",
        is_secret=False,
    ),
    SecretDef(
        key="EMBEDDING_API_KEY",
        label="Embedding API Key",
        category="optional",
        description="API key for the embedding endpoint (if required).",
        is_secret=True,
    ),
    SecretDef(
        key="EMBEDDING_MODEL",
        label="Embedding Model",
        category="optional",
        description="Embedding model name (e.g. all-minilm:l6-v2).",
        is_secret=False,
    ),
    SecretDef(
        key="BRAVE_API_KEY",
        label="Brave Search API Key",
        category="optional",
        description="API key for Brave Search provider.",
        is_secret=True,
    ),
    SecretDef(
        key="GOOGLE_PSE_KEY",
        label="Google PSE API Key",
        category="optional",
        description="API key for Google Programmable Search Engine.",
        is_secret=True,
    ),
    SecretDef(
        key="GOOGLE_PSE_CX",
        label="Google PSE CX ID",
        category="optional",
        description="Custom Search Engine ID for Google PSE.",
        is_secret=False,
    ),
    SecretDef(
        key="TAVILY_API_KEY",
        label="Tavily API Key",
        category="optional",
        description="API key for Tavily search provider.",
        is_secret=True,
    ),
    SecretDef(
        key="SERPER_API_KEY",
        label="Serper.dev API Key",
        category="optional",
        description="API key for Serper.dev (Google SERP API).",
        is_secret=True,
    ),
    SecretDef(
        key="ODYSSEUS_ADMIN_PASSWORD",
        label="Admin Password",
        category="optional",
        description="Pre-seed the first admin password during setup. Not needed in HF Spaces (auth disabled).",
        is_secret=True,
        hf_spaces_only=True,
    ),
]


# ---------------------------------------------------------------------------
# Runtime helpers
# ---------------------------------------------------------------------------

def is_hf_spaces() -> bool:
    """True when running inside a Hugging Face Space."""
    return os.getenv("ODYSSEUS_HF_SPACES", "0") == "1"


def get_space_id() -> Optional[str]:
    """Return the Space ID (e.g. 'username/my-space') if running in HF Spaces."""
    # HF Spaces sets this automatically
    return os.getenv("SPACE_ID") or os.getenv("HF_SPACE_ID")


def get_space_host() -> Optional[str]:
    """Return the Space host URL (e.g. 'https://username-space-name.hf.space')."""
    return os.getenv("SPACE_HOST")


# ---------------------------------------------------------------------------
# Secret status
# ---------------------------------------------------------------------------

def get_secrets_status() -> Dict[str, Any]:
    """Get the current status of all known secrets/environment variables.

    Returns a dict with:
    - secrets: list of {key, label, category, description, is_set, is_secret, value_preview, default, hf_spaces_only}
    - summary: {total, set, missing_required, missing_recommended}
    - is_hf_spaces: bool
    - space_id: str or None
    """
    secrets_list = []
    missing_required = 0
    missing_recommended = 0
    total_set = 0

    for sdef in SECRET_DEFINITIONS:
        # Skip HF-Spaces-only secrets when not in HF Spaces
        if sdef.hf_spaces_only and not is_hf_spaces():
            continue

        value = os.getenv(sdef.key, "")
        is_set = bool(value)
        if is_set:
            total_set += 1
        elif sdef.category == "required":
            missing_required += 1
        elif sdef.category == "recommended":
            missing_recommended += 1

        # Show a preview for non-secret values; mask secrets
        if sdef.is_secret and value:
            value_preview = value[:4] + "..." + value[-2:] if len(value) > 8 else "***"
        elif value:
            value_preview = value if len(value) <= 60 else value[:57] + "..."
        else:
            value_preview = ""

        secrets_list.append({
            "key": sdef.key,
            "label": sdef.label,
            "category": sdef.category,
            "description": sdef.description,
            "is_set": is_set,
            "is_secret": sdef.is_secret,
            "value_preview": value_preview,
            "default": sdef.default,
            "hf_spaces_only": sdef.hf_spaces_only,
        })

    return {
        "secrets": secrets_list,
        "summary": {
            "total": len(secrets_list),
            "set": total_set,
            "missing_required": missing_required,
            "missing_recommended": missing_recommended,
        },
        "is_hf_spaces": is_hf_spaces(),
        "space_id": get_space_id(),
        "space_host": get_space_host(),
    }


# ---------------------------------------------------------------------------
# Space secret management via huggingface_hub API
# ---------------------------------------------------------------------------

class HfSecretsManager:
    """Manage HF Space secrets via the huggingface_hub API.

    This allows adding, deleting, and listing secrets for an HF Space
    directly from the Odysseus UI. Only works when:
    - Running inside an HF Space (or connected to one)
    - An HF_TOKEN with write access is available
    """

    def __init__(self, hf_token: Optional[str] = None, space_id: Optional[str] = None):
        self._hf_token = hf_token or os.getenv("HF_TOKEN") or os.getenv("HUGGING_FACE_HUB_TOKEN")
        self._space_id = space_id or get_space_id()
        self._api = None
        if self._hf_token:
            try:
                from huggingface_hub import HfApi
                self._api = HfApi(token=self._hf_token)
            except ImportError:
                logger.warning("huggingface_hub not installed — Space secret management disabled")
            except Exception as e:
                logger.warning(f"HfSecretsManager: failed to initialize HfApi: {e}")

    @property
    def is_available(self) -> bool:
        """True when we can manage Space secrets (API + space ID + token)."""
        return bool(self._api and self._space_id and self._hf_token)

    @property
    def space_id(self) -> Optional[str]:
        return self._space_id

    def list_space_secrets(self) -> List[Dict[str, Any]]:
        """List all secrets set on the current Space.

        Note: HF API only returns secret *names*, never values.
        Returns list of dicts with keys: key, is_secret
        """
        if not self.is_available:
            raise RuntimeError("Space secret management not available — need HF_TOKEN and SPACE_ID")

        try:
            # get_space_variables returns both secrets and normal variables
            variables = self._api.get_space_variables(self._space_id)
            result = []
            for var in variables:
                result.append({
                    "key": var.key if hasattr(var, "key") else str(var),
                    "is_secret": getattr(var, "is_secret", True),
                })
            return result
        except Exception as e:
            logger.error(f"Failed to list Space secrets: {e}")
            raise RuntimeError(f"Failed to list Space secrets: {e}")

    def add_space_secret(self, key: str, value: str, is_secret: bool = True) -> Dict[str, Any]:
        """Add or update a secret/variable on the Space.

        This triggers a Space restart so the new value is available.

        Args:
            key: Environment variable name
            value: Secret value
            is_secret: True for sensitive values (masked in HF UI), False for plain variables
        """
        if not self.is_available:
            raise RuntimeError("Space secret management not available — need HF_TOKEN and SPACE_ID")

        try:
            if is_secret:
                self._api.add_space_secret(self._space_id, key, value)
            else:
                self._api.add_space_variable(self._space_id, key, value)
            logger.info(f"Added Space {'secret' if is_secret else 'variable'}: {key}")
            return {"success": True, "key": key, "is_secret": is_secret}
        except Exception as e:
            logger.error(f"Failed to add Space secret {key}: {e}")
            raise RuntimeError(f"Failed to add Space secret: {e}")

    def delete_space_secret(self, key: str, is_secret: bool = True) -> Dict[str, Any]:
        """Delete a secret/variable from the Space.

        This triggers a Space restart.
        """
        if not self.is_available:
            raise RuntimeError("Space secret management not available — need HF_TOKEN and SPACE_ID")

        try:
            if is_secret:
                self._api.delete_space_secret(self._space_id, key)
            else:
                self._api.delete_space_variable(self._space_id, key)
            logger.info(f"Deleted Space {'secret' if is_secret else 'variable'}: {key}")
            return {"success": True, "key": key}
        except Exception as e:
            logger.error(f"Failed to delete Space secret {key}: {e}")
            raise RuntimeError(f"Failed to delete Space secret: {e}")

    def get_space_info(self) -> Dict[str, Any]:
        """Get info about the current Space."""
        if not self._api or not self._space_id:
            return {"space_id": None, "available": False}

        try:
            info = self._api.space_info(self._space_id)
            return {
                "space_id": self._space_id,
                "available": True,
                "host": getattr(info, "host", ""),
                "stage": getattr(info, "runtime", {}).get("stage", "unknown") if hasattr(info, "runtime") else "unknown",
            }
        except Exception as e:
            logger.debug(f"Failed to get Space info: {e}")
            return {"space_id": self._space_id, "available": True, "error": str(e)}


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_instance: Optional[HfSecretsManager] = None


def get_hf_secrets_manager() -> HfSecretsManager:
    """Get or create the global HfSecretsManager singleton."""
    global _instance
    if _instance is None:
        _instance = HfSecretsManager()
    return _instance


def reset_hf_secrets_manager(
    hf_token: Optional[str] = None,
    space_id: Optional[str] = None,
) -> HfSecretsManager:
    """Reset and reinitialize the global HfSecretsManager."""
    global _instance
    _instance = HfSecretsManager(hf_token=hf_token, space_id=space_id)
    return _instance
