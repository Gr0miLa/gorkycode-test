from datetime import datetime

from app.domain.commands import Action, AssistantCommand, EventType
from app.services.commands import normalize_command


def test_task_moves_starts_at_to_due_at():
    moment = datetime.fromisoformat("2026-10-11T10:00:00+03:00")
    command = AssistantCommand(
        action=Action.CREATE_TASK,
        transcript="Напомни завтра в 10 позвонить Ивану",
        title="Позвонить Ивану",
        event_type=EventType.TASK,
        starts_at=moment,
    )

    result = normalize_command(command)

    assert result.event_type == EventType.REMINDER
    assert result.due_at == moment
    assert result.starts_at is None


def test_generic_list_removes_invented_event_type():
    command = AssistantCommand(
        action=Action.LIST_EVENTS,
        transcript="Что запланировано на завтра?",
        title="Список событий",
        event_type=EventType.MEETING,
        date_from=datetime.fromisoformat("2026-10-11T00:00:00+03:00"),
        date_to=datetime.fromisoformat("2026-10-11T23:59:59+03:00"),
    )

    result = normalize_command(command)

    assert result.event_type is None


def test_explicit_meeting_list_keeps_meeting_filter():
    command = AssistantCommand(
        action=Action.LIST_EVENTS,
        transcript="Какие встречи у меня завтра?",
        event_type=None,
    )
    assert normalize_command(command).event_type == EventType.MEETING
