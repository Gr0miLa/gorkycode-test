from app.domain.commands import Action, AssistantCommand, EventType
from app.services.text import normalize_text


def normalize_command(command: AssistantCommand) -> AssistantCommand:
    """Map occasionally inconsistent model fields to application semantics."""
    updates: dict = {}

    if command.action == Action.CREATE_TASK:
        updates["event_type"] = (
            EventType.REMINDER
            if "напом" in normalize_text(command.transcript)
            else EventType.TASK
        )
        if command.due_at is None and command.starts_at is not None:
            updates["due_at"] = command.starts_at
            updates["starts_at"] = None
            updates["ends_at"] = None

    if command.action == Action.CREATE_MEETING:
        updates["event_type"] = EventType.MEETING

    if command.action in {Action.LIST_EVENTS, Action.SEARCH_EVENTS}:
        text = normalize_text(command.transcript)
        if "встреч" in text:
            updates["event_type"] = EventType.MEETING
        elif "задач" in text:
            updates["event_type"] = EventType.TASK
        elif "напомин" in text:
            updates["event_type"] = EventType.REMINDER
        else:
            updates["event_type"] = None
        updates["starts_at"] = None
        updates["ends_at"] = None
        updates["due_at"] = None

    return command.model_copy(update=updates)

