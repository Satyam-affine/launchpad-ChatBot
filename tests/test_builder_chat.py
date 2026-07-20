"""Tests for Builder Chat (published GitHub repo assistant)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from builder_chat import (
    BuilderChatError,
    build_builder_chat_context,
    chat_llm_configured,
    handle_builder_chat,
    resolve_session_for_builder_chat,
    workflow_plan_node_count,
)
from builder_chat.repo_context import (
    RepoContextError,
    resolve_published_repo,
    select_paths_for_question,
)


def test_resolve_published_repo_requires_job_repo_url() -> None:
    with patch(
        "builder_chat.repo_context.get_job_or_none",
        return_value=None,
    ):
        with pytest.raises(RepoContextError) as exc:
            resolve_published_repo("sess-missing")
    assert exc.value.code == "repo_not_published"


def test_resolve_published_repo_from_job_fields() -> None:
    job = SimpleNamespace(
        repo_url="https://github.com/acme/kyc-bot",
        github_owner="acme",
        github_repo="kyc-bot",
        repo_branch="main",
        pr_url="https://github.com/acme/kyc-bot/pull/1",
    )
    with patch("builder_chat.repo_context.get_job_or_none", return_value=job):
        published = resolve_published_repo("sess-ok")
    assert published.owner == "acme"
    assert published.repo == "kyc-bot"
    assert published.ref == "main"


def test_select_paths_prefers_readme_and_question_keywords() -> None:
    paths = [
        "README.md",
        "main.py",
        "src/auth/login.py",
        "src/pdf/parser.py",
        "docs/unused.md",
    ]
    selected = select_paths_for_question(paths, "Where is authentication implemented?")
    assert "README.md" in selected
    assert "src/auth/login.py" in selected


def test_build_builder_chat_context_repo_only() -> None:
    payload = {
        "github_repo": {
            "owner": "acme",
            "repo": "kyc-bot",
            "ref": "main",
            "repo_url": "https://github.com/acme/kyc-bot",
            "pr_url": None,
            "file_tree": ["README.md", "main.py"],
            "files": {"README.md": "# KYC bot\n", "main.py": "print('hi')\n"},
        }
    }
    with patch(
        "builder_chat.service.build_github_repo_context",
        return_value=(payload, ["github_repo"]),
    ):
        context_text, sources = build_builder_chat_context(
            "sess-qa",
            "Explain this project.",
        )

    assert sources == ["github_repo"]
    assert "kyc-bot" in context_text
    assert "KYC bot" in context_text
    assert "architecture_plan" not in sources
    assert "scaffold" not in sources


def test_handle_builder_chat_repo_not_published(monkeypatch) -> None:
    from config import Settings

    settings = Settings(
        azure_openai_endpoint="https://x",
        azure_openai_api_key="k",
        azure_openai_api_version="v",
        azure_openai_chat_deployment="chat",
        azure_openai_embedding_deployment="",
        azure_search_endpoint="",
        azure_search_api_key="",
        azure_search_index_name="",
        pdf_path="",
        log_level="INFO",
    )
    monkeypatch.setattr("builder_chat.service.load_settings", lambda: settings)
    monkeypatch.setattr(
        "builder_chat.service.build_builder_chat_context",
        lambda *_a, **_k: (_ for _ in ()).throw(
            BuilderChatError(
                "No GitHub repository has been published for this session yet.",
                status_code=422,
                code="repo_not_published",
            )
        ),
    )

    with pytest.raises(BuilderChatError) as exc:
        handle_builder_chat(
            "sess-chat",
            message="Explain this project.",
            history=[],
            session={"id": "sess-chat", "builder_chat_messages": []},
            workflow=None,
        )
    assert exc.value.code == "repo_not_published"


def test_handle_builder_chat_llm_not_configured_without_crash(monkeypatch) -> None:
    from config import Settings

    empty = Settings(
        azure_openai_endpoint="",
        azure_openai_api_key="",
        azure_openai_api_version="",
        azure_openai_chat_deployment="",
        azure_openai_embedding_deployment="",
        azure_search_endpoint="",
        azure_search_api_key="",
        azure_search_index_name="",
        pdf_path="",
        log_level="INFO",
    )
    monkeypatch.setattr("builder_chat.service.load_settings", lambda: empty)

    with pytest.raises(BuilderChatError) as exc:
        handle_builder_chat(
            "sess-chat",
            message="Explain this project.",
            history=[],
            session={"id": "sess-chat", "builder_chat_messages": []},
            workflow=None,
        )

    assert exc.value.code == "llm_not_configured"
    assert exc.value.status_code == 503


def test_handle_builder_chat_persists_messages() -> None:
    session = {
        "id": "sess-chat",
        "builder_chat_messages": [],
    }

    with patch(
        "builder_chat.service.load_settings",
    ) as mock_settings, patch(
        "builder_chat.service.make_client",
    ), patch(
        "builder_chat.service._call_llm_conversation",
        return_value="This repo has a README and main.py.",
    ), patch(
        "builder_chat.service.build_builder_chat_context",
        return_value=('{"github_repo":{"repo":"kyc-bot"}}', ["github_repo"]),
    ), patch(
        "builder_chat.service._load_system_prompt",
        return_value="system",
    ):
        settings = mock_settings.return_value
        settings.azure_openai_endpoint = "https://example.openai.azure.com"
        settings.azure_openai_api_key = "key"
        settings.azure_openai_api_version = "2024-02-01"
        settings.azure_openai_chat_deployment = "gpt-4o"

        result = handle_builder_chat(
            "sess-chat",
            message="Explain this project.",
            history=[],
            session=session,
            workflow=None,
        )

    assert result["reply"] == "This repo has a README and main.py."
    assert result["context_sources"] == ["github_repo"]
    assert len(result["messages"]) == 2
    assert result["messages"][0]["role"] == "user"
    assert result["messages"][1]["role"] == "assistant"


def test_chat_llm_configured_requires_chat_vars() -> None:
    from config import Settings

    assert chat_llm_configured(
        Settings(
            azure_openai_endpoint="https://x",
            azure_openai_api_key="k",
            azure_openai_api_version="v",
            azure_openai_chat_deployment="chat",
            azure_openai_embedding_deployment="",
            azure_search_endpoint="",
            azure_search_api_key="",
            azure_search_index_name="",
            pdf_path="",
            log_level="INFO",
        )
    )


def test_resolve_session_from_workflow_only(tmp_path: Path, monkeypatch) -> None:
    workflow = {
        "sessionId": "sess-workflow-only",
        "problemStatement": "KYC PDF review",
        "plan": {
            "graph": {
                "nodes": [{"id": "ingest", "label": "PDF Intake Gateway"}],
                "edges": [],
            }
        },
    }
    monkeypatch.setattr(
        "builder_chat.session.load_workflow",
        lambda sid: workflow if sid == "sess-workflow-only" else None,
    )
    monkeypatch.setattr(
        "builder_chat.session.get_session",
        lambda sid: None,
    )

    session, loaded = resolve_session_for_builder_chat("sess-workflow-only")
    assert session is not None
    assert session["id"] == "sess-workflow-only"
    assert session["architecture_plan"]["graph"]["nodes"][0]["label"] == "PDF Intake Gateway"
    assert loaded == workflow
    assert workflow_plan_node_count(loaded, session) == 1


def test_read_json_session_falls_back_to_blob_mirror(tmp_path: Path, monkeypatch) -> None:
    from workflow_builder import launchpad_storage as storage

    mirror_root = tmp_path / "blob_mirror"
    session_id = "mirror-session-1"
    sid = storage.safe_id(session_id)
    mirror_path = mirror_root / "launchpad" / "sessions" / f"{sid}.json"
    mirror_path.parent.mkdir(parents=True)
    payload = {"id": session_id, "spec": {"problem_statement": "from mirror"}}
    mirror_path.write_text(json.dumps(payload), encoding="utf-8")

    monkeypatch.setattr(storage, "LOCAL_MIRROR", mirror_root)
    monkeypatch.setattr(storage, "LOCAL_SESSIONS", tmp_path / "sessions")
    monkeypatch.setattr(storage, "LOCAL_WORKFLOWS", tmp_path / "workflows")
    monkeypatch.setattr(storage, "storage_backend_name", lambda: "local")

    doc = storage.read_json("session", session_id)
    assert doc is not None
    assert doc["spec"]["problem_statement"] == "from mirror"
