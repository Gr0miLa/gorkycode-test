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


def test_nearest_weekday_is_calculated_from_application_clock():
    command = AssistantCommand(
        action=Action.CREATE_TASK,
        transcript="В пятницу нужно отправить отчет",
        title="Отправить отчет",
        event_type=EventType.TASK,
    )

    result = normalize_command(command, datetime.fromisoformat("2026-10-14T22:04:00+03:00"))

    assert result.due_at == datetime.fromisoformat("2026-10-16T23:59:59+03:00")


def test_task_without_date_does_not_get_model_invented_deadline():
    command = AssistantCommand(
        action=Action.CREATE_TASK,
        transcript="Нужно подготовить презентацию",
        title="Подготовить презентацию",
        event_type=EventType.TASK,
        due_at=datetime.fromisoformat("2026-11-30T23:59:59+03:00"),
    )

    result = normalize_command(command, datetime.fromisoformat("2026-10-14T22:04:00+03:00"))

    assert result.due_at is None


def test_current_week_is_monday_through_sunday():
    command = AssistantCommand(
        action=Action.LIST_EVENTS,
        transcript="Что запланировано на эту неделю?",
    )

    result = normalize_command(command, datetime.fromisoformat("2026-10-14T22:04:00+03:00"))

    assert result.date_from == datetime.fromisoformat("2026-10-12T00:00:00+03:00")
    assert result.date_to == datetime.fromisoformat("2026-10-18T23:59:59+03:00")


def test_reminder_misclassified_as_meeting_is_corrected():
    command = AssistantCommand(
        action=Action.CREATE_MEETING,
        transcript="Напомни мне завтра в 10 утра позвонить Ивану",
        title="Позвонить Ивану",
        event_type=EventType.MEETING,
        starts_at=datetime.fromisoformat("2026-10-15T10:00:00+03:00"),
    )

    result = normalize_command(command, datetime.fromisoformat("2026-10-14T22:53:00+03:00"))

    assert result.action == Action.CREATE_TASK
    assert result.event_type == EventType.REMINDER
    assert result.due_at == datetime.fromisoformat("2026-10-15T10:00:00+03:00")


def test_clock_times_are_not_treated_as_missing():
    command = AssistantCommand(
        action=Action.CREATE_MEETING,
        transcript="Добавь встречу с командой завтра в 15:00",
        title="Встреча с командой",
        event_type=EventType.MEETING,
        starts_at=datetime.fromisoformat("2026-10-15T15:00:00+03:00"),
    )

    result = normalize_command(command, datetime.fromisoformat("2026-10-14T22:53:00+03:00"))

    assert result.missing_fields == []
    assert result.starts_at == datetime.fromisoformat("2026-10-15T15:00:00+03:00")


def test_relative_hours_with_russian_number_are_calculated():
    command = AssistantCommand(
        action=Action.CREATE_MEETING,
        transcript="Запланируй встречу с клиентом через два часа",
        title="Встреча с клиентом",
        event_type=EventType.MEETING,
        missing_fields=["start_time"],
    )

    result = normalize_command(command, datetime.fromisoformat("2026-10-14T22:57:00+03:00"))

    assert result.starts_at == datetime.fromisoformat("2026-10-15T00:57:00+03:00")
    assert result.missing_fields == []


def test_absolute_date_with_minutes_is_not_cleared():
    command = AssistantCommand(
        action=Action.CREATE_MEETING,
        transcript="Добавь встречу с друзьями 20 октября в 18:30",
        title="Встреча с друзьями",
        event_type=EventType.MEETING,
        starts_at=datetime.fromisoformat("2026-10-20T18:30:00+03:00"),
    )

    result = normalize_command(command, datetime.fromisoformat("2026-10-14T22:57:00+03:00"))

    assert result.starts_at == datetime.fromisoformat("2026-10-20T18:30:00+03:00")
    assert result.missing_fields == []


def test_natural_event_list_is_not_misclassified_as_search():
    command = AssistantCommand(
        action=Action.SEARCH_EVENTS,
        transcript="Какие встречи были вчера?",
        query="вчера",
    )

    result = normalize_command(command, datetime.fromisoformat("2026-10-14T22:57:00+03:00"))

    assert result.action == Action.LIST_EVENTS
    assert result.date_from == datetime.fromisoformat("2026-10-13T00:00:00+03:00")
    assert result.date_to == datetime.fromisoformat("2026-10-13T23:59:59+03:00")


def test_yesterday_is_preserved_when_creating_meeting():
    command = AssistantCommand(
        action=Action.CREATE_MEETING,
        transcript="Добавь встречу с Жекой вчера",
        title="Встреча с Жекой",
        event_type=EventType.MEETING,
        missing_fields=["start_time"],
    )

    result = normalize_command(command, datetime.fromisoformat("2026-10-14T22:57:00+03:00"))

    assert result.starts_at == datetime.fromisoformat("2026-10-13T09:00:00+03:00")
    assert result.missing_fields == ["start_time"]
