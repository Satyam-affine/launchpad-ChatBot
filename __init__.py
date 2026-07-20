"""Builder Chat — public package surface for LaunchPad integration.

Host apps should import only from ``builder_chat`` (this package), not from
internal modules.
"""

from __future__ import annotations

from builder_chat.routes import builder_chat_router
from builder_chat.service import (
    BuilderChatError,
    build_builder_chat_context,
    chat_llm_configured,
    handle_builder_chat,
)
from builder_chat.session import (
    resolve_session_for_builder_chat,
    workflow_plan_node_count,
)

__all__ = [
    "BuilderChatError",
    "build_builder_chat_context",
    "builder_chat_router",
    "chat_llm_configured",
    "handle_builder_chat",
    "resolve_session_for_builder_chat",
    "workflow_plan_node_count",
]
