# routes/github_routes.py
"""FastAPI routes for GitHub OAuth and repository management.

Provides REST endpoints for:
- GitHub OAuth2 authorization flow (login, callback, disconnect)
- Repository listing, creation, deletion, and updates
- File push/pull/list operations in repositories
- Authenticated user info and organization listing
- Repository forking and branch management
- API rate limit status
"""

import os
import asyncio
import logging
from typing import Optional, List
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)


# ── Request/Response models ────────────────────────────────────────────────

class CreateRepoRequest(BaseModel):
    name: str
    description: str = ""
    private: bool = True
    owner: Optional[str] = None
    auto_init: bool = True
    gitignore_template: Optional[str] = None
    license_template: Optional[str] = None

class UpdateRepoRequest(BaseModel):
    description: Optional[str] = None
    private: Optional[bool] = None
    default_branch: Optional[str] = None
    homepage: Optional[str] = None
    has_issues: Optional[bool] = None
    has_wiki: Optional[bool] = None

class DeleteRepoRequest(BaseModel):
    owner: str
    repo: str
    confirm_name: str  # Must match "owner/repo" as safety check

class PushFileRequest(BaseModel):
    owner: str
    repo: str
    path: str
    content: str
    message: str
    branch: str = "main"
    sha: Optional[str] = None

class DeleteFileRequest(BaseModel):
    owner: str
    repo: str
    path: str
    message: str
    sha: str
    branch: str = "main"

class ForkRepoRequest(BaseModel):
    owner: str
    repo: str
    organization: Optional[str] = None


# ── Route setup ────────────────────────────────────────────────────────────

def setup_github_routes() -> APIRouter:
    router = APIRouter(prefix="/api/github", tags=["github"])

    def _get_github(request: Request):
        """Get GitHubOAuth from app state."""
        gh = getattr(request.app.state, "github_oauth", None)
        if not gh:
            raise HTTPException(503, "GitHub OAuth not initialized")
        return gh

    def _build_redirect_uri(request: Request) -> str:
        """Build the OAuth callback URL from the request."""
        # Try to use the configured base URL first
        base = os.getenv("OAUTH_REDIRECT_BASE_URL") or os.getenv("APP_PUBLIC_URL")
        if base:
            return f"{base.rstrip('/')}/api/github/oauth/callback"
        # Fallback: derive from the request
        scheme = request.url.scheme
        host = request.headers.get("host", request.url.netloc)
        return f"{scheme}://{host}/api/github/oauth/callback"

    # ── OAuth Flow ────────────────────────────────────────────────────

    @router.get("/oauth/authorize")
    async def github_authorize(request: Request):
        """Start the GitHub OAuth2 authorization flow.

        Generates an authorization URL and redirects the user to GitHub.
        """
        gh = _get_github(request)
        if not gh.has_oauth_app:
            raise HTTPException(400, "GitHub OAuth App not configured. Set GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET.")

        redirect_uri = _build_redirect_uri(request)

        try:
            result = gh.get_authorization_url(redirect_uri=redirect_uri)
            return {"url": result["url"], "state": result["state"]}
        except Exception as e:
            raise HTTPException(500, f"Failed to generate authorization URL: {e}")

    @router.get("/oauth/callback")
    async def github_callback(request: Request, code: str, state: str):
        """Handle the GitHub OAuth2 callback.

        GitHub redirects here after the user authorizes the app.
        This endpoint exchanges the code for an access token, fetches the
        GitHub user info, auto-provisions a local Odysseus account, creates
        a session, and sets the session cookie — so "Login with GitHub"
        actually logs the user in.
        """
        gh = _get_github(request)
        redirect_uri = _build_redirect_uri(request)
        auth_manager = getattr(request.app.state, "auth_manager", None)

        try:
            result = await gh.exchange_code(
                code=code,
                state=state,
                redirect_uri=redirect_uri,
            )

            # Fetch GitHub user info to use as the local username
            gh_user = None
            username = ""
            try:
                gh_user = await gh.get_authenticated_user()
                username = (gh_user.get("login") or "").strip().lower()
            except Exception as e:
                logger.warning(f"Failed to fetch GitHub user info after OAuth: {e}")

            if not username:
                return RedirectResponse(
                    url="/login?github_auth=error&msg=no_user_info",
                    status_code=302,
                )

            # Auto-provision local account if it doesn't exist
            if auth_manager:
                username = await asyncio.to_thread(auth_manager.ensure_user, username, "github")
                if not username:
                    return RedirectResponse(
                        url="/login?github_auth=error&msg=account_creation_failed",
                        status_code=302,
                    )

                # Create a session (passwordless — GitHub already authenticated them)
                session_token = await asyncio.to_thread(auth_manager.create_session_for_user, username)
                if not session_token:
                    return RedirectResponse(
                        url="/login?github_auth=error&msg=session_failed",
                        status_code=302,
                    )

                # Build the redirect response with session cookie
                response = RedirectResponse(url="/?github_auth=success", status_code=302)
                cookie_kwargs = dict(
                    key="odysseus_session",
                    value=session_token,
                    httponly=True,
                    samesite="lax",
                    secure=os.getenv("SECURE_COOKIES", "false").lower() == "true",
                    path="/",
                    max_age=60 * 60 * 24 * 7,  # 7 days
                )
                response.set_cookie(**cookie_kwargs)
                logger.info(f"GitHub OAuth login successful for user '{username}'")
                return response
            else:
                # No auth manager — just redirect (legacy behavior)
                return RedirectResponse(url="/?github_auth=success", status_code=302)

        except ValueError as e:
            logger.warning(f"GitHub OAuth callback validation failed: {e}")
            return RedirectResponse(
                url="/login?github_auth=error&msg=invalid_state",
                status_code=302,
            )
        except Exception as e:
            logger.error(f"GitHub OAuth callback failed: {e}")
            return RedirectResponse(
                url=f"/login?github_auth=error&msg={str(e)[:100]}",
                status_code=302,
            )

    @router.post("/oauth/disconnect")
    async def github_disconnect(request: Request):
        """Disconnect the GitHub account (remove stored token)."""
        gh = _get_github(request)
        gh.disconnect()
        return {"success": True}

    # ── Status & Settings ──────────────────────────────────────────────

    @router.get("/status")
    async def github_status(request: Request):
        """Get the current GitHub integration status.

        Safe to call unauthenticated — used by the login page to decide
        whether to show the "Login with GitHub" button.
        """
        gh = getattr(request.app.state, "github_oauth", None)
        if not gh:
            # GitHubOAuth not initialized — report as unconfigured
            return {
                "configured": False,
                "authenticated": False,
                "has_client_id": False,
                "user": None,
                "settings": {},
            }
        user_info = None
        if gh.is_authenticated:
            try:
                user_info = await gh.get_authenticated_user()
            except Exception:
                user_info = gh.settings.get("user_info")

        return {
            "configured": gh.has_oauth_app,
            "authenticated": gh.is_authenticated,
            "has_client_id": bool(gh.client_id),
            "user": user_info,
            "settings": gh.settings,
        }

    # ── User Info ──────────────────────────────────────────────────────

    @router.get("/user")
    async def get_user(request: Request):
        """Get info about the authenticated GitHub user."""
        gh = _get_github(request)
        if not gh.is_authenticated:
            raise HTTPException(401, "Not authenticated with GitHub")
        try:
            return await gh.get_authenticated_user()
        except Exception as e:
            raise HTTPException(500, f"Failed to get user info: {e}")

    @router.get("/orgs")
    async def list_orgs(request: Request):
        """List organizations the authenticated user belongs to."""
        gh = _get_github(request)
        if not gh.is_authenticated:
            raise HTTPException(401, "Not authenticated with GitHub")
        try:
            return {"orgs": await gh.get_user_orgs()}
        except Exception as e:
            raise HTTPException(500, f"Failed to list orgs: {e}")

    # ── Repository CRUD ────────────────────────────────────────────────

    @router.get("/repos")
    async def list_repos(
        request: Request,
        owner: Optional[str] = None,
        repo_type: str = "all",
        sort: str = "updated",
        per_page: int = 30,
        page: int = 1,
    ):
        """List repositories for the authenticated user or an org."""
        gh = _get_github(request)
        if not gh.is_authenticated:
            raise HTTPException(401, "Not authenticated with GitHub")
        try:
            repos = await gh.list_repos(
                owner=owner,
                repo_type=repo_type,
                sort=sort,
                per_page=min(per_page, 100),
                page=page,
            )
            return {"repos": repos}
        except Exception as e:
            raise HTTPException(500, f"Failed to list repos: {e}")

    @router.get("/repos/{owner}/{repo}")
    async def get_repo(request: Request, owner: str, repo: str):
        """Get details for a specific repository."""
        gh = _get_github(request)
        if not gh.is_authenticated:
            raise HTTPException(401, "Not authenticated with GitHub")
        try:
            return await gh.get_repo(owner, repo)
        except RuntimeError as e:
            if "not found" in str(e).lower():
                raise HTTPException(404, f"Repository {owner}/{repo} not found")
            raise HTTPException(500, str(e))
        except Exception as e:
            raise HTTPException(500, f"Failed to get repo: {e}")

    @router.post("/repos")
    async def create_repo(request: Request, body: CreateRepoRequest):
        """Create a new repository."""
        gh = _get_github(request)
        if not gh.is_authenticated:
            raise HTTPException(401, "Not authenticated with GitHub")
        try:
            result = await gh.create_repo(
                name=body.name,
                description=body.description,
                private=body.private,
                owner=body.owner,
                auto_init=body.auto_init,
                gitignore_template=body.gitignore_template,
                license_template=body.license_template,
            )
            return {"success": True, "repo": result}
        except Exception as e:
            raise HTTPException(500, f"Failed to create repo: {e}")

    @router.patch("/repos/{owner}/{repo}")
    async def update_repo(
        request: Request,
        owner: str,
        repo: str,
        body: UpdateRepoRequest,
    ):
        """Update repository settings."""
        gh = _get_github(request)
        if not gh.is_authenticated:
            raise HTTPException(401, "Not authenticated with GitHub")
        try:
            result = await gh.update_repo(
                owner=owner,
                repo=repo,
                description=body.description,
                private=body.private,
                default_branch=body.default_branch,
                homepage=body.homepage,
                has_issues=body.has_issues,
                has_wiki=body.has_wiki,
            )
            return {"success": True, "repo": result}
        except Exception as e:
            raise HTTPException(500, f"Failed to update repo: {e}")

    @router.delete("/repos/{owner}/{repo}")
    async def delete_repo(
        request: Request,
        owner: str,
        repo: str,
        confirm: str = "",
    ):
        """Delete a repository (irreversible!).

        The `confirm` query parameter must match "owner/repo" exactly
        as a safety check against accidental deletion.
        """
        gh = _get_github(request)
        if not gh.is_authenticated:
            raise HTTPException(401, "Not authenticated with GitHub")

        expected_confirm = f"{owner}/{repo}"
        if confirm != expected_confirm:
            raise HTTPException(
                400,
                f"Safety check failed: confirm parameter must be '{expected_confirm}'",
            )

        try:
            await gh.delete_repo(owner, repo)
            return {"success": True, "deleted": expected_confirm}
        except Exception as e:
            raise HTTPException(500, f"Failed to delete repo: {e}")

    # ── Repository Fork ────────────────────────────────────────────────

    @router.post("/repos/fork")
    async def fork_repo(request: Request, body: ForkRepoRequest):
        """Fork a repository."""
        gh = _get_github(request)
        if not gh.is_authenticated:
            raise HTTPException(401, "Not authenticated with GitHub")
        try:
            result = await gh.fork_repo(
                owner=body.owner,
                repo=body.repo,
                organization=body.organization,
            )
            return {"success": True, "repo": result}
        except Exception as e:
            raise HTTPException(500, f"Failed to fork repo: {e}")

    # ── Repository Branches ────────────────────────────────────────────

    @router.get("/repos/{owner}/{repo}/branches")
    async def list_branches(request: Request, owner: str, repo: str):
        """List branches in a repository."""
        gh = _get_github(request)
        if not gh.is_authenticated:
            raise HTTPException(401, "Not authenticated with GitHub")
        try:
            branches = await gh.get_repo_branches(owner, repo)
            return {"branches": branches}
        except Exception as e:
            raise HTTPException(500, f"Failed to list branches: {e}")

    # ── File Operations ────────────────────────────────────────────────

    @router.post("/files/push")
    async def push_file(request: Request, body: PushFileRequest):
        """Create or update a file in a repository."""
        gh = _get_github(request)
        if not gh.is_authenticated:
            raise HTTPException(401, "Not authenticated with GitHub")
        try:
            result = await gh.push_file(
                owner=body.owner,
                repo=body.repo,
                path=body.path,
                content=body.content,
                message=body.message,
                branch=body.branch,
                sha=body.sha,
            )
            return {"success": True, "result": result}
        except Exception as e:
            raise HTTPException(500, f"Failed to push file: {e}")

    @router.get("/files/{owner}/{repo}")
    async def list_repo_contents(
        request: Request,
        owner: str,
        repo: str,
        path: str = "",
        branch: Optional[str] = None,
    ):
        """List contents of a directory in a repository."""
        gh = _get_github(request)
        if not gh.is_authenticated:
            raise HTTPException(401, "Not authenticated with GitHub")
        try:
            contents = await gh.list_repo_contents(
                owner=owner,
                repo=repo,
                path=path,
                branch=branch,
            )
            return {"contents": contents}
        except Exception as e:
            raise HTTPException(500, f"Failed to list contents: {e}")

    @router.get("/files/{owner}/{repo}/{path:path}")
    async def get_file(
        request: Request,
        owner: str,
        repo: str,
        path: str,
        branch: Optional[str] = None,
    ):
        """Get a file's content from a repository."""
        gh = _get_github(request)
        if not gh.is_authenticated:
            raise HTTPException(401, "Not authenticated with GitHub")
        try:
            return await gh.get_file(owner=owner, repo=repo, path=path, branch=branch)
        except Exception as e:
            raise HTTPException(500, f"Failed to get file: {e}")

    @router.post("/files/delete")
    async def delete_file(request: Request, body: DeleteFileRequest):
        """Delete a file from a repository."""
        gh = _get_github(request)
        if not gh.is_authenticated:
            raise HTTPException(401, "Not authenticated with GitHub")
        try:
            result = await gh.delete_file(
                owner=body.owner,
                repo=body.repo,
                path=body.path,
                message=body.message,
                sha=body.sha,
                branch=body.branch,
            )
            return {"success": True, "result": result}
        except Exception as e:
            raise HTTPException(500, f"Failed to delete file: {e}")

    # ── Rate Limit ─────────────────────────────────────────────────────

    @router.get("/rate-limit")
    async def get_rate_limit(request: Request):
        """Get the current GitHub API rate limit status."""
        gh = _get_github(request)
        if not gh.is_authenticated:
            raise HTTPException(401, "Not authenticated with GitHub")
        try:
            return await gh.get_rate_limit()
        except Exception as e:
            raise HTTPException(500, f"Failed to get rate limit: {e}")

    return router
