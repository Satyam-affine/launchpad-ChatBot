"""Builder Chat — codebase assistant for the session's published GitHub repository."""

from __future__ import annotations

import json
import logging
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openai import APIError, APITimeoutError, AzureOpenAI, RateLimitError

from builder_chat.config import (
    chat_llm_settings_configured,
    load_settings,
    missing_chat_llm_vars,
)
from builder_chat.repo_context import (
    RepoContextError,
    build_github_repo_context,
)
from config import Settings
from services.llm import make_client

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
_MAX_CONTEXT_CHARS = 48_000
_MAX_HISTORY_TURNS = 10
_LLM_BACKOFF = (2, 4, 8)
_LLM_MAX_RETRIES = 3


class BuilderChatError(Exception):
    """Raised when builder chat cannot run."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 500,
        code: str = "builder_chat_error",
    ):
        super().__init__(message)
        self.status_code = status_code
        self.code = code


def chat_llm_configured(settings: Settings | None = None) -> bool:
    return chat_llm_settings_configured(settings)


def _load_system_prompt() -> str:
    return (_PROMPTS_DIR / "builder_chat_system.txt").read_text(encoding="utf-8")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_message_id() -> str:
    return f"bcm_{secrets.token_hex(8)}"


def _truncate_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _truncate_json(payload: Any, max_chars: int) -> str:
    text = json.dumps(payload, indent=2, default=str)
    if len(text) <= max_chars:
        return text
    return _truncate_text(text, max_chars)


def build_builder_chat_context(
    session_id: str,
    question: str,
) -> tuple[str, list[str]]:
    """Assemble repo-only JSON context for the published GitHub repository."""
    try:
        payload, sources = build_github_repo_context(session_id, question)
    except RepoContextError as exc:
        raise BuilderChatError(
            str(exc),
            status_code=exc.status_code,
            code=exc.code,
        ) from exc
    return _truncate_json(payload, _MAX_CONTEXT_CHARS), sources


def _call_llm_conversation(
    client: AzureOpenAI,
    settings: Settings,
    system_prompt: str,
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.2,
) -> str:
    last_error: Exception | None = None
    for attempt in range(_LLM_MAX_RETRIES):
        try:
            response = client.chat.completions.create(
                model=settings.azure_openai_chat_deployment,
                messages=[{"role": "system", "content": system_prompt}, *messages],
                temperature=temperature,
            )
            content = response.choices[0].message.content
            if not content:
                raise ValueError("Empty response from chat completion")
            return content.strip()
        except (RateLimitError, APITimeoutError, APIError) as exc:
            last_error = exc
            wait = _LLM_BACKOFF[min(attempt, len(_LLM_BACKOFF) - 1)]
            logger.warning(
                "builder_chat LLM error (attempt %d/%d): %s — retrying in %ds",
                attempt + 1,
                _LLM_MAX_RETRIES,
                exc,
                wait,
            )
            time.sleep(wait)
    raise last_error or RuntimeError("LLM call failed after retries")


def _normalize_history(history: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in history or []:
        role = str(item.get("role") or "").strip().lower()
        content = str(item.get("content") or "").strip()
        if role not in {"user", "assistant"} or not content:
            continue
        rows.append({"role": role, "content": content})
    return rows[-(_MAX_HISTORY_TURNS * 2) :]


def _normalize_stored_messages(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        content = str(item.get("content") or "").strip()
        if role not in {"user", "assistant"} or not content:
            continue
        rows.append(
            {
                "id": str(item.get("id") or _new_message_id()),
                "role": role,
                "content": content,
                "timestamp": item.get("timestamp") or _utc_now_iso(),
            }
        )
    return rows


def handle_builder_chat(
    session_id: str,
    *,
    message: str,
    history: list[dict[str, Any]] | None,
    session: dict[str, Any],
    workflow: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run one builder Q&A turn grounded only in the published GitHub repo."""
    del workflow  # retained for call-site compatibility; unused
    user_text = message.strip()
    if not user_text:
        raise BuilderChatError("Message is required", status_code=400, code="invalid_message")

    settings = load_settings()
    if not chat_llm_configured(settings):
        missing = ", ".join(missing_chat_llm_vars(settings))
        raise BuilderChatError(
            "Azure OpenAI chat is not configured. Set "
            f"{missing} in .env before using the codebase assistant.",
            status_code=503,
            code="llm_not_configured",
        )

    context_text, sources = build_builder_chat_context(session_id, user_text)
    system_prompt = (
        _load_system_prompt()
        + "\n\n## Repository contents\n\n```json\n"
        + context_text
        + "\n```"
    )

    prior = _normalize_history(history)
    llm_messages = [*prior, {"role": "user", "content": user_text}]
    client = make_client(settings)
    try:
        reply = _call_llm_conversation(client, settings, system_prompt, llm_messages)
    except Exception as exc:
        logger.exception("builder_chat LLM call failed for session %s", session_id)
        raise BuilderChatError(
            "The AI service failed to generate a reply. Try again in a moment.",
            status_code=502,
            code="llm_failed",
        ) from exc

    stored = _normalize_stored_messages(session.get("builder_chat_messages"))
    now = _utc_now_iso()
    stored.append(
        {
            "id": _new_message_id(),
            "role": "user",
            "content": user_text,
            "timestamp": now,
        }
    )
    stored.append(
        {
            "id": _new_message_id(),
            "role": "assistant",
            "content": reply,
            "timestamp": _utc_now_iso(),
        }
    )

    return {
        "reply": reply,
        "messages": stored,
        "context_sources": sources,
    }
