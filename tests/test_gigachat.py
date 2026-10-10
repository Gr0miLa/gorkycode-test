import asyncio
import json

from app.config import Settings
from app.domain.commands import Action
from app.integrations.gigachat import GigaChatClient


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

