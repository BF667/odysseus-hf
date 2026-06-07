# src/github_oauth.py
"""GitHub OAuth integration and repository management for Odysseus.

Provides:
- GitHub OAuth2 Authorization Code flow (login with GitHub)
- Repository listing, creation, and deletion
- File push/pull to/from GitHub repositories
- Repository visibility and settings management

OAuth flow reference:
  https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps

GitHub REST API reference:
  https://docs.github.com/en/rest?apiVersion=2022-11-28
"""

import os
import json
import logging
import secrets
import tempfile
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from pathlib import Path
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Settings persistence
# ---------------------------------------------------------------------------

GITHUB_SETTINGS_FILE = os.path.join("data", "github_oauth_settings.json")

# OAuth state store: {state_token: {"created_at": iso, "redirect": url}}
_PENDING_STATES: Dict[str, Dict[str, Any]] = {}


def _load_github_settings() -> Dict[str, Any]:
    """Load GitHub OAuth settings from disk."""
    if not os.path.exists(GITHUB_SETTINGS_FILE):
        return {}
    try:
        with open(GITHUB_SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning(f"Failed to load GitHub settings: {e}")
        return {}


def _save_github_settings(settings: Dict[str, Any]) -> None:
    """Persist GitHub OAuth settings to disk atomically."""
    os.makedirs(os.path.dirname(GITHUB_SETTINGS_FILE), exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=os.path.dirname(GITHUB_SETTINGS_FILE),
        prefix=".github_settings-",
        suffix=".tmp",
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, GITHUB_SETTINGS_FILE)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# GitHubOAuth — main interface
# ---------------------------------------------------------------------------

class GitHubOAuth:
    """Manages GitHub OAuth2 authentication and repository operations.

    Features:
    - Generate OAuth authorization URLs for user login
    - Exchange authorization codes for access tokens
    - List, create, delete repositories
    - Push files to repositories
    - Manage repository settings (visibility, description, etc.)
    - List user organizations and authenticated user info
    """

    GITHUB_AUTH_URL = "https://github.com/login/oauth/authorize"
    GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
    GITHUB_API_URL = "https://api.github.com"

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
    ):
        self._client_id = client_id or os.getenv("GITHUB_CLIENT_ID", "")
        self._client_secret = client_secret or os.getenv("GITHUB_CLIENT_SECRET", "")
        self._settings = _load_github_settings()
        self._access_token = self._settings.get("access_token", "")
        self._token_expires_at = self._settings.get("token_expires_at", "")
        self._refresh_token = self._settings.get("refresh_token", "")

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_configured(self) -> bool:
        """True when both client ID/secret and an access token are available."""
        return bool(self._client_id and self._client_secret and self._access_token)

    @property
    def has_oauth_app(self) -> bool:
        """True when GitHub OAuth App credentials are configured."""
        return bool(self._client_id and self._client_secret)

    @property
    def is_authenticated(self) -> bool:
        """True when we have a valid access token."""
        return bool(self._access_token)

    @property
    def client_id(self) -> str:
        return self._client_id

    @property
    def access_token(self) -> str:
        return self._access_token

    @property
    def settings(self) -> Dict[str, Any]:
        s = dict(self._settings)
        # Don't expose the full access token
        if self._access_token:
            s["has_access_token"] = True
            s["access_token_preview"] = self._access_token[:8] + "..." if len(self._access_token) > 8 else "***"
        else:
            s["has_access_token"] = False
            s["access_token_preview"] = ""
        # Remove the actual tokens from the settings view
        s.pop("access_token", None)
        s.pop("refresh_token", None)
        return s

    # ------------------------------------------------------------------
    # OAuth2 Flow
    # ------------------------------------------------------------------

    def get_authorization_url(
        self,
        redirect_uri: str,
        scope: str = "repo,user,read:org",
        state: Optional[str] = None,
    ) -> Dict[str, str]:
        """Generate the GitHub OAuth authorization URL.

        Args:
            redirect_uri: The URL GitHub redirects to after authorization.
            scope: OAuth scopes requested.
            state: Optional CSRF state token. Generated if not provided.

        Returns:
            Dict with 'url', 'state' keys.
        """
        if not self.has_oauth_app:
            raise RuntimeError("GitHub OAuth App not configured — set GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET")

        if not state:
            state = secrets.token_urlsafe(32)

        # Store the state for validation in the callback
        _PENDING_STATES[state] = {
            "created_at": datetime.utcnow().isoformat(),
            "redirect": redirect_uri,
        }

        params = {
            "client_id": self._client_id,
            "redirect_uri": redirect_uri,
            "scope": scope,
            "state": state,
        }

        url = f"{self.GITHUB_AUTH_URL}?{urlencode(params)}"
        return {"url": url, "state": state}

    async def exchange_code(
        self,
        code: str,
        state: str,
        redirect_uri: str,
    ) -> Dict[str, Any]:
        """Exchange an authorization code for an access token.

        Args:
            code: The authorization code from GitHub.
            state: The CSRF state token (validated against pending states).
            redirect_uri: Must match the redirect_uri used in authorization.

        Returns:
            Dict with token info.
        """
        # Validate state
        pending = _PENDING_STATES.pop(state, None)
        if not pending:
            raise ValueError("Invalid or expired OAuth state token")

        # Check state age (max 10 minutes)
        created = datetime.fromisoformat(pending["created_at"])
        if datetime.utcnow() - created > timedelta(minutes=10):
            raise ValueError("OAuth state token expired")

        import httpx

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                self.GITHUB_TOKEN_URL,
                json={
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
                headers={"Accept": "application/json"},
            )

        if response.status_code != 200:
            raise RuntimeError(f"GitHub token exchange failed: {response.status_code} {response.text}")

        data = response.json()

        if "error" in data:
            raise RuntimeError(f"GitHub OAuth error: {data.get('error_description', data['error'])}")

        access_token = data.get("access_token", "")
        token_type = data.get("token_type", "bearer")
        scope = data.get("scope", "")
        refresh_token = data.get("refresh_token", "")
        expires_in = data.get("expires_in")

        # Store the token
        self._access_token = access_token
        self._refresh_token = refresh_token
        if expires_in:
            self._token_expires_at = (datetime.utcnow() + timedelta(seconds=expires_in)).isoformat()
        else:
            self._token_expires_at = ""

        self._settings["access_token"] = access_token
        self._settings["refresh_token"] = refresh_token
        self._settings["token_expires_at"] = self._token_expires_at
        self._settings["token_scope"] = scope
        self._settings["authenticated_at"] = datetime.utcnow().isoformat()
        _save_github_settings(self._settings)

        logger.info("GitHub OAuth token obtained successfully")

        return {
            "success": True,
            "token_type": token_type,
            "scope": scope,
            "has_refresh_token": bool(refresh_token),
        }

    def disconnect(self) -> None:
        """Remove the stored GitHub access token."""
        self._access_token = ""
        self._refresh_token = ""
        self._token_expires_at = ""
        self._settings.pop("access_token", None)
        self._settings.pop("refresh_token", None)
        self._settings.pop("token_expires_at", None)
        self._settings.pop("token_scope", None)
        self._settings.pop("authenticated_at", None)
        self._settings.pop("user_info", None)
        _save_github_settings(self._settings)
        logger.info("GitHub OAuth disconnected")

    # ------------------------------------------------------------------
    # GitHub API helpers
    # ------------------------------------------------------------------

    def _get_headers(self) -> Dict[str, str]:
        """Return authorization headers for GitHub API calls."""
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def _api_get(self, path: str, params: Optional[Dict] = None) -> Any:
        """Make an authenticated GET request to the GitHub API."""
        import httpx
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self.GITHUB_API_URL}{path}",
                headers=self._get_headers(),
                params=params or {},
            )
        if response.status_code == 401:
            raise RuntimeError("GitHub token expired or invalid — re-authenticate")
        if response.status_code == 403:
            raise RuntimeError("GitHub API rate limit exceeded or insufficient permissions")
        if response.status_code == 404:
            raise RuntimeError("GitHub resource not found")
        if response.status_code not in (200, 201, 204):
            raise RuntimeError(f"GitHub API error: {response.status_code} {response.text}")
        if response.status_code == 204:
            return {}
        return response.json()

    async def _api_post(self, path: str, data: Optional[Dict] = None) -> Any:
        """Make an authenticated POST request to the GitHub API."""
        import httpx
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.GITHUB_API_URL}{path}",
                headers=self._get_headers(),
                json=data or {},
            )
        if response.status_code == 401:
            raise RuntimeError("GitHub token expired or invalid — re-authenticate")
        if response.status_code == 403:
            raise RuntimeError("GitHub API rate limit exceeded or insufficient permissions")
        if response.status_code == 404:
            raise RuntimeError("GitHub resource not found")
        if response.status_code not in (200, 201, 204):
            raise RuntimeError(f"GitHub API error: {response.status_code} {response.text}")
        if response.status_code == 204:
            return {}
        return response.json()

    async def _api_patch(self, path: str, data: Optional[Dict] = None) -> Any:
        """Make an authenticated PATCH request to the GitHub API."""
        import httpx
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.patch(
                f"{self.GITHUB_API_URL}{path}",
                headers=self._get_headers(),
                json=data or {},
            )
        if response.status_code == 401:
            raise RuntimeError("GitHub token expired or invalid — re-authenticate")
        if response.status_code not in (200, 201, 204):
            raise RuntimeError(f"GitHub API error: {response.status_code} {response.text}")
        if response.status_code == 204:
            return {}
        return response.json()

    async def _api_delete(self, path: str) -> None:
        """Make an authenticated DELETE request to the GitHub API."""
        import httpx
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.delete(
                f"{self.GITHUB_API_URL}{path}",
                headers=self._get_headers(),
            )
        if response.status_code == 401:
            raise RuntimeError("GitHub token expired or invalid — re-authenticate")
        if response.status_code == 403:
            raise RuntimeError("GitHub API rate limit exceeded or insufficient permissions")
        if response.status_code == 404:
            raise RuntimeError("GitHub resource not found")
        if response.status_code not in (204, 200):
            raise RuntimeError(f"GitHub API error: {response.status_code} {response.text}")

    # ------------------------------------------------------------------
    # User info
    # ------------------------------------------------------------------

    async def get_authenticated_user(self) -> Dict[str, Any]:
        """Get info about the authenticated GitHub user."""
        data = await self._api_get("/user")
        result = {
            "login": data.get("login", ""),
            "name": data.get("name", ""),
            "avatar_url": data.get("avatar_url", ""),
            "html_url": data.get("html_url", ""),
            "email": data.get("email", ""),
            "public_repos": data.get("public_repos", 0),
            "private_repos": data.get("total_private_repos", 0),
            "plan": data.get("plan", {}).get("name", ""),
        }
        # Cache user info in settings
        self._settings["user_info"] = result
        _save_github_settings(self._settings)
        return result

    async def get_user_orgs(self) -> List[Dict[str, Any]]:
        """List organizations the authenticated user belongs to."""
        data = await self._api_get("/user/orgs")
        return [
            {
                "login": org.get("login", ""),
                "avatar_url": org.get("avatar_url", ""),
                "description": org.get("description", ""),
            }
            for org in data
        ]

    # ------------------------------------------------------------------
    # Repository CRUD
    # ------------------------------------------------------------------

    async def list_repos(
        self,
        owner: Optional[str] = None,
        repo_type: str = "all",
        sort: str = "updated",
        per_page: int = 30,
        page: int = 1,
    ) -> List[Dict[str, Any]]:
        """List repositories for the authenticated user or an org.

        Args:
            owner: Username or org. If None, lists the authenticated user's repos.
            repo_type: One of 'all', 'owner', 'public', 'private', 'member'.
            sort: One of 'created', 'updated', 'pushed', 'full_name'.
            per_page: Results per page (max 100).
            page: Page number.
        """
        if owner:
            # Check if it's an org
            path = f"/orgs/{owner}/repos"
        else:
            path = "/user/repos"

        data = await self._api_get(path, params={
            "type": repo_type,
            "sort": sort,
            "per_page": per_page,
            "page": page,
        })

        return [
            {
                "id": repo.get("id"),
                "name": repo.get("name", ""),
                "full_name": repo.get("full_name", ""),
                "description": repo.get("description", "") or "",
                "private": repo.get("private", False),
                "html_url": repo.get("html_url", ""),
                "clone_url": repo.get("clone_url", ""),
                "ssh_url": repo.get("ssh_url", ""),
                "language": repo.get("language", ""),
                "stargazers_count": repo.get("stargazers_count", 0),
                "forks_count": repo.get("forks_count", 0),
                "created_at": repo.get("created_at", ""),
                "updated_at": repo.get("updated_at", ""),
                "pushed_at": repo.get("pushed_at", ""),
                "default_branch": repo.get("default_branch", "main"),
                "size": repo.get("size", 0),
            }
            for repo in data
        ]

    async def get_repo(self, owner: str, repo: str) -> Dict[str, Any]:
        """Get details for a specific repository."""
        data = await self._api_get(f"/repos/{owner}/{repo}")
        return {
            "id": data.get("id"),
            "name": data.get("name", ""),
            "full_name": data.get("full_name", ""),
            "description": data.get("description", "") or "",
            "private": data.get("private", False),
            "html_url": data.get("html_url", ""),
            "clone_url": data.get("clone_url", ""),
            "ssh_url": data.get("ssh_url", ""),
            "language": data.get("language", ""),
            "stargazers_count": data.get("stargazers_count", 0),
            "forks_count": data.get("forks_count", 0),
            "open_issues_count": data.get("open_issues_count", 0),
            "default_branch": data.get("default_branch", "main"),
            "size": data.get("size", 0),
            "permissions": data.get("permissions", {}),
            "created_at": data.get("created_at", ""),
            "updated_at": data.get("updated_at", ""),
            "pushed_at": data.get("pushed_at", ""),
        }

    async def create_repo(
        self,
        name: str,
        description: str = "",
        private: bool = True,
        owner: Optional[str] = None,
        auto_init: bool = True,
        gitignore_template: Optional[str] = None,
        license_template: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a new repository.

        Args:
            name: Repository name.
            description: Repository description.
            private: Whether the repo should be private.
            owner: Organization to create under (if None, creates under authenticated user).
            auto_init: Initialize with a README.
            gitignore_template: Gitignore template (e.g. "Python").
            license_template: License template (e.g. "mit").
        """
        payload = {
            "name": name,
            "description": description,
            "private": private,
            "auto_init": auto_init,
        }
        if gitignore_template:
            payload["gitignore_template"] = gitignore_template
        if license_template:
            payload["license_template"] = license_template

        if owner:
            path = f"/orgs/{owner}/repos"
        else:
            path = "/user/repos"

        data = await self._api_post(path, data=payload)

        logger.info(f"Created repository: {data.get('full_name', name)}")
        return {
            "id": data.get("id"),
            "name": data.get("name", ""),
            "full_name": data.get("full_name", ""),
            "description": data.get("description", "") or "",
            "private": data.get("private", True),
            "html_url": data.get("html_url", ""),
            "clone_url": data.get("clone_url", ""),
            "default_branch": data.get("default_branch", "main"),
        }

    async def delete_repo(self, owner: str, repo: str) -> None:
        """Delete a repository (irreversible!).

        Requires the `delete_repo` scope.
        """
        await self._api_delete(f"/repos/{owner}/{repo}")
        logger.info(f"Deleted repository: {owner}/{repo}")

    async def update_repo(
        self,
        owner: str,
        repo: str,
        description: Optional[str] = None,
        private: Optional[bool] = None,
        default_branch: Optional[str] = None,
        homepage: Optional[str] = None,
        has_issues: Optional[bool] = None,
        has_wiki: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Update repository settings."""
        payload = {}
        if description is not None:
            payload["description"] = description
        if private is not None:
            payload["private"] = private
        if default_branch is not None:
            payload["default_branch"] = default_branch
        if homepage is not None:
            payload["homepage"] = homepage
        if has_issues is not None:
            payload["has_issues"] = has_issues
        if has_wiki is not None:
            payload["has_wiki"] = has_wiki

        data = await self._api_patch(f"/repos/{owner}/{repo}", data=payload)
        return {
            "id": data.get("id"),
            "name": data.get("name", ""),
            "full_name": data.get("full_name", ""),
            "description": data.get("description", "") or "",
            "private": data.get("private", False),
            "html_url": data.get("html_url", ""),
        }

    # ------------------------------------------------------------------
    # File operations
    # ------------------------------------------------------------------

    async def push_file(
        self,
        owner: str,
        repo: str,
        path: str,
        content: str,
        message: str,
        branch: str = "main",
        sha: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create or update a file in a repository.

        Args:
            owner: Repository owner.
            repo: Repository name.
            path: File path in the repo.
            content: File content (will be base64 encoded).
            message: Commit message.
            branch: Target branch.
            sha: Required for updating existing files (the blob SHA of the existing file).
        """
        import base64

        payload = {
            "message": message,
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            "branch": branch,
        }
        if sha:
            payload["sha"] = sha

        data = await self._api_put(f"/repos/{owner}/{repo}/contents/{path}", data=payload)
        return {
            "commit": {
                "sha": data.get("commit", {}).get("sha", ""),
                "html_url": data.get("commit", {}).get("html_url", ""),
            },
            "content": {
                "path": data.get("content", {}).get("path", path),
                "sha": data.get("content", {}).get("sha", ""),
            },
        }

    async def get_file(
        self,
        owner: str,
        repo: str,
        path: str,
        branch: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get a file's content and metadata from a repository."""
        import base64

        params = {}
        if branch:
            params["ref"] = branch

        data = await self._api_get(f"/repos/{owner}/{repo}/contents/{path}", params=params)

        content_b64 = data.get("content", "")
        encoding = data.get("encoding", "base64")
        file_content = ""
        if encoding == "base64" and content_b64:
            try:
                file_content = base64.b64decode(content_b64).decode("utf-8", errors="replace")
            except Exception:
                file_content = "[binary file]"

        return {
            "name": data.get("name", ""),
            "path": data.get("path", path),
            "sha": data.get("sha", ""),
            "size": data.get("size", 0),
            "type": data.get("type", "file"),
            "content": file_content,
            "html_url": data.get("html_url", ""),
            "download_url": data.get("download_url", ""),
        }

    async def delete_file(
        self,
        owner: str,
        repo: str,
        path: str,
        message: str,
        sha: str,
        branch: str = "main",
    ) -> Dict[str, Any]:
        """Delete a file from a repository."""
        payload = {
            "message": message,
            "sha": sha,
            "branch": branch,
        }
        data = await self._api_delete_with_body(
            f"/repos/{owner}/{repo}/contents/{path}", body=payload
        )
        return {
            "commit": {
                "sha": data.get("commit", {}).get("sha", ""),
                "html_url": data.get("commit", {}).get("html_url", ""),
            },
        }

    async def list_repo_contents(
        self,
        owner: str,
        repo: str,
        path: str = "",
        branch: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List contents of a directory in a repository."""
        params = {}
        if branch:
            params["ref"] = branch

        endpoint = f"/repos/{owner}/{repo}/contents"
        if path:
            endpoint = f"{endpoint}/{path}"

        data = await self._api_get(endpoint, params=params)

        # Can be a single file (dict) or directory listing (list)
        if isinstance(data, dict):
            data = [data]

        return [
            {
                "name": item.get("name", ""),
                "path": item.get("path", ""),
                "type": item.get("type", ""),
                "size": item.get("size", 0),
                "sha": item.get("sha", ""),
                "html_url": item.get("html_url", ""),
                "download_url": item.get("download_url", ""),
            }
            for item in data
        ]

    # ------------------------------------------------------------------
    # Additional API helpers
    # ------------------------------------------------------------------

    async def _api_put(self, path: str, data: Optional[Dict] = None) -> Any:
        """Make an authenticated PUT request to the GitHub API."""
        import httpx
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.put(
                f"{self.GITHUB_API_URL}{path}",
                headers=self._get_headers(),
                json=data or {},
            )
        if response.status_code == 401:
            raise RuntimeError("GitHub token expired or invalid — re-authenticate")
        if response.status_code == 403:
            raise RuntimeError("GitHub API rate limit exceeded or insufficient permissions")
        if response.status_code not in (200, 201, 204):
            raise RuntimeError(f"GitHub API error: {response.status_code} {response.text}")
        if response.status_code == 204:
            return {}
        return response.json()

    async def _api_delete_with_body(self, path: str, body: Optional[Dict] = None) -> Any:
        """Make an authenticated DELETE request with a JSON body."""
        import httpx
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(
                "DELETE",
                f"{self.GITHUB_API_URL}{path}",
                headers=self._get_headers(),
                json=body or {},
            )
        if response.status_code == 401:
            raise RuntimeError("GitHub token expired or invalid — re-authenticate")
        if response.status_code == 403:
            raise RuntimeError("GitHub API rate limit exceeded or insufficient permissions")
        if response.status_code not in (200, 204):
            raise RuntimeError(f"GitHub API error: {response.status_code} {response.text}")
        if response.status_code == 204:
            return {}
        return response.json()

    async def get_repo_branches(self, owner: str, repo: str) -> List[Dict[str, Any]]:
        """List branches in a repository."""
        data = await self._api_get(f"/repos/{owner}/{repo}/branches")
        return [
            {
                "name": b.get("name", ""),
                "protected": b.get("protected", False),
                "sha": b.get("commit", {}).get("sha", ""),
            }
            for b in data
        ]

    async def fork_repo(
        self,
        owner: str,
        repo: str,
        organization: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Fork a repository."""
        payload = {}
        if organization:
            payload["organization"] = organization

        data = await self._api_post(f"/repos/{owner}/{repo}/forks", data=payload)
        return {
            "id": data.get("id"),
            "name": data.get("name", ""),
            "full_name": data.get("full_name", ""),
            "html_url": data.get("html_url", ""),
            "clone_url": data.get("clone_url", ""),
        }

    async def get_rate_limit(self) -> Dict[str, Any]:
        """Get the current API rate limit status."""
        data = await self._api_get("/rate_limit")
        core = data.get("resources", {}).get("core", {})
        return {
            "limit": core.get("limit", 0),
            "remaining": core.get("remaining", 0),
            "reset": core.get("reset", 0),
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_instance: Optional[GitHubOAuth] = None


def get_github_oauth() -> GitHubOAuth:
    """Get or create the global GitHubOAuth singleton."""
    global _instance
    if _instance is None:
        _instance = GitHubOAuth()
    return _instance


def reset_github_oauth(
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None,
) -> GitHubOAuth:
    """Reset and reinitialize the global GitHubOAuth."""
    global _instance
    _instance = GitHubOAuth(client_id=client_id, client_secret=client_secret)
    return _instance
