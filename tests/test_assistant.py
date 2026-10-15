from app.domain.commands import EventType
from app.services.assistant import list_reply


def test_list_reply_uses_requested_event_type():
    assert list_reply(2, EventType.TASK) == "Найдено задач: 2."
    assert list_reply(1, EventType.REMINDER) == "Найдено напоминаний: 1."
    assert list_reply(3, EventType.MEETING) == "Найдено встреч: 3."
    assert list_reply(4, None) == "Найдено событий: 4."


def test_empty_list_reply_uses_requested_event_type():
    assert list_reply(0, EventType.TASK) == "Задач не найдено."
    assert list_reply(0, EventType.MEETING) == "Встреч не найдено."
    assert list_reply(0, None) == "Событий не найдено."
