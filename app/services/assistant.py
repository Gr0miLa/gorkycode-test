import logging
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.config import Settings
from app.domain.commands import Action, AssistantCommand, AssistantResponse, EventResponse
from app.integrations.gigachat import GigaChatClient
from app.services.commands import normalize_command
from app.services.events import DialogueService, EventService


logger = logging.getLogger(__name__)


class AssistantService:
    def __init__(self, db: Session, settings: Settings, client: GigaChatClient) -> None:
        self.settings = settings
        self.client = client
        self.events = EventService(db, settings.default_timezone)
        self.dialogue = DialogueService(db)

    async def handle_text(self, session_id: str, text: str) -> AssistantResponse:
        pending = self.dialogue.get_pending(session_id)
        command = await self.client.interpret(
            text=text,
            now_iso=self._now_iso(),
            pending_action=pending,
        )
        command = self._normalize_and_log(command, pending)
        return self.execute(session_id, command, "user_text")

    async def handle_audio(
        self, session_id: str, filename: str, content: bytes, content_type: str
    ) -> AssistantResponse:
        pending = self.dialogue.get_pending(session_id)
        file_id = await self.client.upload_audio(filename, content, content_type)
        try:
            command = await self.client.interpret(
                text="Транскрибируй аудио и выполни содержащуюся в нем команду.",
                now_iso=self._now_iso(),
                pending_action=pending,
                attachment_id=file_id,
            )
            command = self._normalize_and_log(command, pending)
            return self.execute(session_id, command, "user_audio")
        finally:
            await self.client.delete_file(file_id)

    def execute(
        self, session_id: str, command: AssistantCommand, source: str
    ) -> AssistantResponse:
        if command.missing_fields or command.action == Action.CLARIFY:
            if command.action != Action.CLARIFY:
                self.dialogue.set_pending(session_id, command)
            question = command.clarification_question or "Уточните, пожалуйста, детали."
            return AssistantResponse(
                reply=question,
                action=command.action.value,
                transcript=command.transcript,
                needs_clarification=True,
            )

        self.dialogue.clear_pending(session_id)
        if command.action == Action.CREATE_TASK:
            event = self.events.create_task(session_id, command, source)
            return AssistantResponse(
                reply=f"Задача «{event.title}» добавлена.",
                action=command.action.value,
                transcript=command.transcript,
                created_event=EventResponse.model_validate(event),
            )
        if command.action == Action.CREATE_MEETING:
            event = self.events.create_meeting(session_id, command, source)
            return AssistantResponse(
                reply=f"Встреча «{event.title}» добавлена на {event.starts_at}.",
                action=command.action.value,
                transcript=command.transcript,
                created_event=EventResponse.model_validate(event),
            )
        if command.action == Action.LIST_EVENTS:
            events = self.events.list_events(
                session_id, command.date_from, command.date_to, command.event_type
            )
            reply = f"Найдено событий: {len(events)}." if events else "Событий не найдено."
            return AssistantResponse(
                reply=reply,
                action=command.action.value,
                transcript=command.transcript,
                events=[EventResponse.model_validate(event) for event in events],
            )
        if command.action == Action.SEARCH_EVENTS:
            events = self.events.search_events(
                session_id,
                command.query or "",
                command.date_from,
                command.date_to,
                command.event_type,
            )
            reply = f"Найдено совпадений: {len(events)}." if events else "Совпадений не найдено."
            return AssistantResponse(
                reply=reply,
                action=command.action.value,
                transcript=command.transcript,
                events=[EventResponse.model_validate(event) for event in events],
            )
        raise ValueError(f"Unsupported action: {command.action}")

    def _now_iso(self) -> str:
        return datetime.now(ZoneInfo(self.settings.default_timezone)).isoformat()

    def _normalize_and_log(self, command: AssistantCommand, pending: dict | None = None) -> AssistantCommand:
        normalized = normalize_command(
            command, datetime.now(ZoneInfo(self.settings.default_timezone))
        )
        if pending and normalized.action in {Action.CREATE_TASK, Action.CREATE_MEETING}:
            pending_command = AssistantCommand.model_validate(pending)
            normalized = normalized.model_copy(update={
                "title": pending_command.title or normalized.title,
                "event_type": pending_command.event_type or normalized.event_type,
                "due_at": normalized.due_at or pending_command.due_at,
                "starts_at": normalized.starts_at or pending_command.starts_at,
                "ends_at": normalized.ends_at or pending_command.ends_at,
                "transcript": normalized.transcript,
            })
            if normalized.action == Action.CREATE_MEETING and pending_command.starts_at:
                match = re.search(
                    r"(?:^|\s)(\d{1,2})(?:(?::|\s)(\d{2})|(\d{2}))?\s*(?:час(?:а|ов)?|утра|вечера|дня)?(?:\s|$)",
                    normalized.transcript.lower(),
                )
                if match:
                    hour = int(match.group(1))
                    if "вечера" in normalized.transcript.lower() or "дня" in normalized.transcript.lower():
                        hour = hour + 12 if hour < 12 else hour
                    normalized = normalized.model_copy(update={
                        "starts_at": pending_command.starts_at.replace(
                            hour=hour,
                            minute=int(match.group(2) or match.group(3) or 0),
                            second=0,
                            microsecond=0,
                        )
                    })
            missing = []
            if normalized.action == Action.CREATE_MEETING:
                if not normalized.title:
                    missing.append("title")
                if not normalized.starts_at:
                    missing.append("start_time")
            elif not normalized.title:
                missing.append("title")
            normalized = normalized.model_copy(update={"missing_fields": missing})
        logger.info(
            "assistant_command action=%s type=%s title=%r due_at=%s starts_at=%s "
            "date_from=%s date_to=%s missing=%s",
            normalized.action.value,
            normalized.event_type.value if normalized.event_type else None,
            normalized.title,
            normalized.due_at,
            normalized.starts_at,
            normalized.date_from,
            normalized.date_to,
            normalized.missing_fields,
        )
        return normalized
