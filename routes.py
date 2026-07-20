"""HTTP routes owned by the Builder Chat module."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from builder_chat.service import BuilderChatError, handle_builder_chat
from builder_chat.session import (
    resolve_session_for_builder_chat,
    workflow_plan_node_count,
)
from workflow_builder.workflow_builder_standalone import save_session

builder_chat_router = APIRouter(tags=["builder-chat"])


@builder_chat_router.post("/sessions/{session_id}/builder/chat")
def post_builder_chat_api(session_id: str, body: dict[str, Any]):
    sid = session_id.strip()
    if not sid:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "invalid_session_id",
                "message": "A non-empty session id is required.",
            },
        )

    session, workflow = resolve_session_for_builder_chat(sid)
    if session is None and workflow is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "session_not_found",
                "message": (
                    f"No saved session or workflow found for '{sid}'. "
                    "Open the builder from a completed Launchpad session or saved workflow."
                ),
            },
        )

    if workflow_plan_node_count(workflow, session) == 0:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "workflow_empty",
                "message": (
                    "This session exists but has no workflow steps yet. "
                    "Finish the Launchpad interview and generate an architecture plan first."
                ),
            },
        )

    message = str(body.get("message") or "").strip()
    history = body.get("history") if isinstance(body.get("history"), list) else None

    try:
        result = handle_builder_chat(
            sid,
            message=message,
            history=history,
            session=session,
            workflow=workflow,
        )
    except BuilderChatError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc

    session["builder_chat_messages"] = result["messages"]
    save_session(session, sync_workflow=False)
    return result
