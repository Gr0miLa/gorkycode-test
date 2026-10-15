import asyncio
import json
import logging
import time
import uuid
from typing import Any

import httpx

from app.config import Settings
from app.domain.commands import AssistantCommand


logger = logging.getLogger(__name__)

COMMAND_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "action": {
            "type": "string",
            "enum": ["create_task", "create_meeting", "list_events", "search_events", "clarify"],
        },
        "transcript": {"type": "string"},
        "title": {"type": ["string", "null"]},
        "event_type": {"type": ["string", "null"], "enum": ["task", "reminder", "meeting", None]},
        "starts_at": {"type": ["string", "null"], "format": "date-time"},
        "ends_at": {"type": ["string", "null"], "format": "date-time"},
        "due_at": {"type": ["string", "null"], "format": "date-time"},
        "due_date": {"type": ["string", "null"], "format": "date"},
        "date_from": {"type": ["string", "null"], "format": "date-time"},
        "date_to": {"type": ["string", "null"], "format": "date-time"},
        "query": {"type": ["string", "null"]},
        "missing_fields": {"type": "array", "items": {"type": "string"}},
        "clarification_question": {"type": ["string", "null"]},
    },
    "required": [
        "action", "transcript", "title", "event_type", "starts_at", "ends_at",
        "due_at", "date_from", "date_to", "query", "missing_fields",
        "clarification_question", "due_date",
    ],
}


class GigaChatError(RuntimeError):
    pass


class GigaChatClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._token: str | None = None
        self._token_expires_at = 0.0

    async def interpret(
        self,
        *,
        text: str,
        now_iso: str,
        pending_action: dict | None = None,
        attachment_id: str | None = None,
    ) -> AssistantCommand:
        system = self._system_prompt(now_iso, pending_action)
        user_message: dict[str, Any] = {"role": "user", "content": text}
        if attachment_id:
            user_message["attachments"] = [attachment_id]
        payload = {
            "model": self.settings.gigachat_model,
            "messages": [
                {"role": "system", "content": system},
                user_message,
            ],
            "temperature": 0.0,
            "response_format": {
                "type": "json_schema",
                "schema": COMMAND_SCHEMA,
                "strict": True,
            },
        }
        data = await self._request("POST", "/chat/completions", json=payload)
        try:
            content = data["choices"][0]["message"]["content"]
            command = AssistantCommand.model_validate(json.loads(content))
            logger.info(
                "gigachat_command action=%s type=%s due_at=%s starts_at=%s "
                "date_from=%s date_to=%s missing=%s",
                command.action.value,
                command.event_type.value if command.event_type else None,
                command.due_at,
                command.starts_at,
                command.date_from,
                command.date_to,
                command.missing_fields,
            )
            return command
        except (KeyError, IndexError, TypeError, json.JSONDecodeError, ValueError) as exc:
            raise GigaChatError("GigaChat вернул ответ в неожиданном формате") from exc

    async def upload_audio(self, filename: str, content: bytes, content_type: str) -> str:
        data = await self._request(
            "POST",
            "/files",
            data={"purpose": "general"},
            files={"file": (filename, content, content_type)},
        )
        try:
            return str(data["id"])
        except KeyError as exc:
            raise GigaChatError("GigaChat не вернул идентификатор аудиофайла") from exc

    async def delete_file(self, file_id: str) -> None:
        try:
            await self._request("POST", f"/files/{file_id}/delete")
        except GigaChatError:
            # Cleanup failure must not hide a successfully processed command.
            return

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        if not self.settings.gigachat_auth_key:
            raise GigaChatError("GIGACHAT_AUTH_KEY не настроен")
        token = await self._access_token()
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {token}"
        url = f"{self.settings.gigachat_api_url.rstrip('/')}{path}"
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                async with httpx.AsyncClient(
                    timeout=45.0, verify=self.settings.gigachat_verify_ssl
                ) as client:
                    response = await client.request(method, url, headers=headers, **kwargs)
                response.raise_for_status()
                return response.json()
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                if attempt == 0:
                    await asyncio.sleep(0.25)
        detail = self._http_error_detail(last_error)
        raise GigaChatError(f"Не удалось выполнить запрос к GigaChat{detail}") from last_error

    async def _access_token(self) -> str:
        if self._token and time.monotonic() < self._token_expires_at:
            return self._token
        headers = {
            "Authorization": f"Basic {self.settings.gigachat_auth_key}",
            "RqUID": str(uuid.uuid4()),
            "Content-Type": "application/x-www-form-urlencoded",
        }
        try:
            async with httpx.AsyncClient(
                timeout=20.0, verify=self.settings.gigachat_verify_ssl
            ) as client:
                response = await client.post(
                    self.settings.gigachat_oauth_url,
                    headers=headers,
                    data={"scope": self.settings.gigachat_scope},
                )
            response.raise_for_status()
            payload = response.json()
            self._token = str(payload["access_token"])
            self._token_expires_at = time.monotonic() + 25 * 60
            return self._token
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            detail = self._http_error_detail(exc)
            raise GigaChatError(f"Не удалось авторизоваться в GigaChat{detail}") from exc

    @staticmethod
    def _http_error_detail(error: Exception | None) -> str:
        if not isinstance(error, httpx.HTTPStatusError):
            return ""
        response = error.response
        try:
            message = response.json().get("message")
        except (ValueError, AttributeError):
            message = None
        suffix = f": {response.status_code}"
        return f"{suffix} {message}" if message else suffix

    def _system_prompt(self, now_iso: str, pending_action: dict | None) -> str:
        pending = json.dumps(pending_action, ensure_ascii=False) if pending_action else "нет"
        return f"""
Ты преобразуешь русские запросы к календарю в одну строгую JSON-команду.
Текущее время: {now_iso}. Часовой пояс: {self.settings.default_timezone}.
Неделя начинается в понедельник. Названный день недели означает ближайшее его
наступление после текущей даты; для «на этой неделе» используй понедельник—воскресенье
текущей календарной недели. Не добавляй необязательные поля в missing_fields: для
задачи достаточно title, а для встречи обязательны только title и время начала.
Незавершенная команда текущего диалога: {pending}.

Разрешенные действия: create_task, create_meeting, list_events, search_events.
Если текущая фраза отвечает на уточнение, объедини ее с незавершенной командой.
Для встречи обязательны title и starts_at. Для задачи обязательны title и дата;
если дата не указана, перечисли due_date в missing_fields и задай вопрос о дате.
Если у задачи есть только дата, заполни due_date и оставь due_at равным null.
Не выдумывай обязательные данные: перечисли их в
missing_fields и сформулируй один короткий clarification_question. В таком
случае сохрани исходное целевое action, а не меняй его на clarify.
Для запросов списка укажи date_from/date_to. Для поиска укажи query.
Все даты верни в ISO-8601 с часовым поясом. transcript должен содержать точный
распознанный текст пользователя; для аудио сначала транскрибируй запись.
Верни только объект, соответствующий переданной JSON Schema.
""".strip()
