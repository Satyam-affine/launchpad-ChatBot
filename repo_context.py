"""Fetch context for Builder Chat from the session's published GitHub repository."""

from __future__ import annotations

import asyncio
import base64
import logging
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlparse

import httpx

from cursor_codegen.store import get_job_or_none

logger = logging.getLogger(__name__)

_GITHUB_API = "https://api.github.com"
_MAX_TREE_PATHS = 400
_MAX_FILES = 12
_MAX_FILE_CHARS = 3_500
_MAX_TOTAL_FILE_CHARS = 36_000

_BINARY_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".pdf",
    ".zip",
    ".tar",
    ".gz",
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".mp4",
    ".mp3",
    ".bin",
    ".pyc",
    ".pyo",
}

# Prefer these when present (always try to include).
_PRIORITY_NAMES = (
    "readme.md",
    "readme",
    "requirements.txt",
    "pyproject.toml",
    "package.json",
    "dockerfile",
    "main.py",
    "run_workflow.py",
    "workflow.json",
    "app.py",
    "index.ts",
    "index.js",
)


@dataclass(frozen=True)
class PublishedRepo:
    owner: str
    repo: str
    ref: str
    repo_url: str
    pr_url: str | None = None


class RepoContextError(Exception):
    def __init__(self, message: str, *, code: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def resolve_published_repo(session_id: str) -> PublishedRepo:
    """Return the GitHub repo published by codegen for this session, or raise."""
    job = get_job_or_none(session_id)
    if job is None or not (job.repo_url or "").strip():
        raise RepoContextError(
            "No GitHub repository has been published for this session yet. "
            "Generate and publish code first, then ask about the repository.",
            code="repo_not_published",
            status_code=422,
        )

    owner = (job.github_owner or "").strip()
    repo = (job.github_repo or "").strip()
    if not owner or not repo:
        parsed = _parse_owner_repo(job.repo_url or "")
        if not parsed:
            raise RepoContextError(
                "Published repository metadata is incomplete. Re-run code generation.",
                code="repo_not_published",
                status_code=422,
            )
        owner, repo = parsed

    ref = (job.repo_branch or "").strip() or "main"
    return PublishedRepo(
        owner=owner,
        repo=repo,
        ref=ref,
        repo_url=str(job.repo_url).strip(),
        pr_url=(job.pr_url or None),
    )


def _parse_owner_repo(repo_url: str) -> tuple[str, str] | None:
    raw = (repo_url or "").strip()
    if not raw:
        return None
    path = urlparse(raw).path.strip("/")
    if path.endswith(".git"):
        path = path[:-4]
    parts = [p for p in path.split("/") if p]
    if len(parts) < 2:
        return None
    return parts[0], parts[1]


def resolve_github_token(session_id: str) -> str:
    """Sync wrapper around existing GitHub auth helpers."""
    return asyncio.run(_resolve_github_token_async(session_id))


async def _resolve_github_token_async(session_id: str) -> str:
    from github_integration import (
        get_installation,
        get_installation_token,
        resolve_user_access_token,
    )

    user_token = await resolve_user_access_token(session_id)
    if user_token:
        return user_token

    installation = get_installation(session_id)
    if not installation:
        raise RepoContextError(
            "GitHub is not connected for this session. Connect GitHub, then try again.",
            code="github_not_connected",
            status_code=401,
        )

    try:
        return await get_installation_token(int(installation["installationId"]))
    except Exception as exc:
        raise RepoContextError(
            "Could not obtain a GitHub access token for this session.",
            code="github_not_connected",
            status_code=401,
        ) from exc


def _github_headers(token: str) -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "Agentic-LaunchPad-BuilderChat",
    }


def fetch_repo_tree(owner: str, repo: str, ref: str, token: str) -> list[str]:
    """Return blob paths for the repo at ref (recursive tree)."""
    url = (
        f"{_GITHUB_API}/repos/{quote(owner, safe='')}/{quote(repo, safe='')}"
        f"/git/trees/{quote(ref, safe='')}"
    )
    try:
        response = httpx.get(
            url,
            headers=_github_headers(token),
            params={"recursive": "1"},
            timeout=45.0,
        )
    except httpx.HTTPError as exc:
        raise RepoContextError(
            f"Failed to list files in {owner}/{repo}: {exc}",
            code="repo_fetch_failed",
            status_code=502,
        ) from exc

    if response.status_code == 404:
        raise RepoContextError(
            f"Repository tree not found for {owner}/{repo}@{ref}.",
            code="repo_fetch_failed",
            status_code=404,
        )
    if response.status_code >= 400:
        raise RepoContextError(
            f"GitHub returned {response.status_code} listing {owner}/{repo}.",
            code="repo_fetch_failed",
            status_code=502,
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise RepoContextError(
            "Invalid GitHub tree response.",
            code="repo_fetch_failed",
            status_code=502,
        ) from exc

    paths: list[str] = []
    for item in payload.get("tree") or []:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "blob":
            continue
        path = str(item.get("path") or "").strip()
        if not path or _is_skipped_path(path):
            continue
        paths.append(path)
        if len(paths) >= _MAX_TREE_PATHS:
            break
    return paths


def fetch_file_text(
    owner: str,
    repo: str,
    path: str,
    ref: str,
    token: str,
) -> str | None:
    url = (
        f"{_GITHUB_API}/repos/{quote(owner, safe='')}/{quote(repo, safe='')}"
        f"/contents/{quote(path.replace(chr(92), '/'), safe='/')}"
    )
    try:
        response = httpx.get(
            url,
            headers=_github_headers(token),
            params={"ref": ref},
            timeout=30.0,
        )
    except httpx.HTTPError:
        return None
    if response.status_code != 200:
        return None
    try:
        payload = response.json()
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    if str(payload.get("encoding") or "").lower() != "base64":
        return None
    content = payload.get("content")
    if not isinstance(content, str):
        return None
    try:
        raw = base64.b64decode(content)
    except Exception:
        return None
    if b"\x00" in raw[:1024]:
        return None
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("utf-8", errors="replace")
    if len(text) > _MAX_FILE_CHARS:
        return text[: _MAX_FILE_CHARS - 3].rstrip() + "..."
    return text


def select_paths_for_question(paths: list[str], question: str) -> list[str]:
    """Pick a small set of paths: priority files + keyword matches."""
    tokens = _question_tokens(question)
    priority: list[str] = []
    scored: list[tuple[int, str]] = []

    for path in paths:
        name = path.rsplit("/", 1)[-1].lower()
        if name in _PRIORITY_NAMES or path.lower() in _PRIORITY_NAMES:
            priority.append(path)
            continue
        score = _path_score(path, tokens)
        if score > 0:
            scored.append((score, path))

    scored.sort(key=lambda item: (-item[0], item[1]))
    selected: list[str] = []
    seen: set[str] = set()
    for path in [*priority, *[p for _, p in scored]]:
        if path in seen:
            continue
        seen.add(path)
        selected.append(path)
        if len(selected) >= _MAX_FILES:
            break

    # If nothing matched, still give a few shallow files so basic questions work.
    if not selected:
        shallow = sorted(paths, key=lambda p: (p.count("/"), p))[:_MAX_FILES]
        selected = shallow
    return selected


def build_github_repo_context(
    session_id: str,
    question: str,
) -> tuple[dict[str, Any], list[str]]:
    """
    Build repo-only context for the LLM.

    Returns (payload, source_labels).
    """
    published = resolve_published_repo(session_id)
    token = resolve_github_token(session_id)
    tree = fetch_repo_tree(published.owner, published.repo, published.ref, token)
    if not tree:
        raise RepoContextError(
            f"Repository {published.owner}/{published.repo} has no readable files yet.",
            code="repo_fetch_failed",
            status_code=422,
        )

    selected = select_paths_for_question(tree, question)
    files: dict[str, str] = {}
    total = 0
    for path in selected:
        text = fetch_file_text(
            published.owner,
            published.repo,
            path,
            published.ref,
            token,
        )
        if not text:
            continue
        files[path] = text
        total += len(text)
        if total >= _MAX_TOTAL_FILE_CHARS:
            break

    if not files:
        raise RepoContextError(
            "Could not read any text files from the published repository.",
            code="repo_fetch_failed",
            status_code=502,
        )

    payload: dict[str, Any] = {
        "github_repo": {
            "owner": published.owner,
            "repo": published.repo,
            "ref": published.ref,
            "repo_url": published.repo_url,
            "pr_url": published.pr_url,
            "file_tree": tree[:_MAX_TREE_PATHS],
            "files": files,
        }
    }
    return payload, ["github_repo"]


def _is_skipped_path(path: str) -> bool:
    parts = path.replace("\\", "/").split("/")
    skip_dirs = {".git", "node_modules", "__pycache__", ".venv", ".mypy_cache", ".pytest_cache"}
    if any(part in skip_dirs for part in parts):
        return True
    lower = path.lower()
    return any(lower.endswith(ext) for ext in _BINARY_SUFFIXES)


def _question_tokens(question: str) -> set[str]:
    return {
        t
        for t in re.split(r"[^a-z0-9_]+", question.lower())
        if len(t) >= 3
    }


def _path_score(path: str, tokens: set[str]) -> int:
    if not tokens:
        return 0
    parts = re.split(r"[^a-z0-9]+", path.lower())
    parts = [p for p in parts if len(p) >= 3]
    hay = " ".join(parts)
    score = 0
    for token in tokens:
        if token in hay:
            score += 2
            continue
        for part in parts:
            if token.startswith(part) or part.startswith(token):
                score += 2
                break
    return score
