import asyncio
import json

import pytest

from app.config import Settings
from app.domain.commands import Action
from app.integrations.gigachat import GigaChatClient, GigaChatError


def test_interpret_uses_json_schema_and_parses_command():
    client = GigaChatClient(Settings())
    captured = {}

    async def fake_request(method, path, **kwargs):
        captured.update({"method": method, "path": path, **kwargs})
        command = {
            "action": "create_task",
            "transcript": "Подготовить отчет",
            "title": "Подготовить отчет",
            "event_type": "task",
            "starts_at": None,
            "ends_at": None,
            "due_at": None,
            "due_date": None,
            "date_from": None,
            "date_to": None,
            "query": None,
            "missing_fields": [],
            "clarification_question": None,
        }
        return {"choices": [{"message": {"content": json.dumps(command)}}]}

    client._request = fake_request
    result = asyncio.run(
        client.interpret(text="Подготовить отчет", now_iso="2026-10-10T12:00:00+03:00")
    )

    assert result.action == Action.CREATE_TASK
    assert captured["path"] == "/chat/completions"
    assert captured["json"]["response_format"]["type"] == "json_schema"


def test_invalid_provider_response_for_greeting_returns_safe_clarification():
    client = GigaChatClient(Settings())

    async def fake_request(*_args, **_kwargs):
        return {"choices": [{"message": {"content": "Привет! Чем могу помочь?"}}]}

    client._request = fake_request
    result = asyncio.run(
        client.interpret(text="Здарова", now_iso="2026-10-15T12:00:00+03:00")
    )

    assert result.action == Action.CLARIFY
    assert "создавать задачи" in result.clarification_question


def test_invalid_provider_response_for_event_command_remains_an_error():
    client = GigaChatClient(Settings())

    async def fake_request(*_args, **_kwargs):
        return {"choices": [{"message": {"content": "Не JSON"}}]}

    client._request = fake_request

    with pytest.raises(GigaChatError, match="неожиданном формате"):
        asyncio.run(
            client.interpret(
                text="Добавь задачу завтра",
                now_iso="2026-10-15T12:00:00+03:00",
            )
        )


def test_invalid_provider_response_during_pending_dialogue_preserves_context():
    client = GigaChatClient(Settings())
    pending = {
        "action": "create_task",
        "transcript": "Нужно сходить в магазин",
        "title": "Сходить в магазин",
        "event_type": "task",
        "starts_at": None,
        "ends_at": None,
        "due_at": None,
        "due_date": None,
        "date_from": None,
        "date_to": None,
        "query": None,
        "missing_fields": ["due_date"],
        "clarification_question": "На какую дату поставить задачу?",
    }

    async def fake_request(*_args, **_kwargs):
        return {"choices": [{"message": {"content": "Сегодня"}}]}

    client._request = fake_request
    result = asyncio.run(
        client.interpret(
            text="На сегодня",
            now_iso="2026-10-15T12:00:00+03:00",
            pending_action=pending,
        )
    )

    assert result.action == Action.CREATE_TASK
    assert result.title == "Сходить в магазин"
    assert result.transcript == "На сегодня"
