import logging
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
        command = await self.client.interpret(
            text=text,
            now_iso=self._now_iso(),
            pending_action=self.dialogue.get_pending(session_id),
        )
        command = self._normalize_and_log(command)
        return self.execute(session_id, command, "user_text")

    async def handle_audio(
        self, session_id: str, filename: str, content: bytes, content_type: str
    ) -> AssistantResponse:
        file_id = await self.client.upload_audio(filename, content, content_type)
        try:
            command = await self.client.interpret(
                text="Транскрибируй аудио и выполни содержащуюся в нем команду.",
                now_iso=self._now_iso(),
                pending_action=self.dialogue.get_pending(session_id),
                attachment_id=file_id,
            )
            command = self._normalize_and_log(command)
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

    @staticmethod
    def _normalize_and_log(command: AssistantCommand) -> AssistantCommand:
        normalized = normalize_command(command)
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

