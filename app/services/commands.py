import re
from datetime import datetime, time, timedelta

from app.domain.commands import Action, AssistantCommand, EventType
from app.services.text import extract_search_query, normalize_text


WEEKDAY_ALIASES = {
    "понедельник": 0, "понедельника": 0,
    "вторник": 1, "вторника": 1,
    "среда": 2, "среду": 2, "среды": 2,
    "четверг": 3, "четверга": 3,
    "пятница": 4, "пятницу": 4, "пятницы": 4,
    "суббота": 5, "субботу": 5, "субботы": 5,
    "воскресенье": 6, "воскресенья": 6,
}
NUMBER_WORDS = {
    "один": 1,
    "два": 2,
    "три": 3,
    "четыре": 4,
    "пять": 5,
    "шесть": 6,
    "семь": 7,
    "восемь": 8,
    "девять": 9,
    "десять": 10,
}


def normalize_command(command: AssistantCommand, now: datetime | None = None) -> AssistantCommand:
    """Map occasionally inconsistent model fields to application semantics."""
    transcript_text = normalize_text(command.transcript)
    if command.action == Action.CLARIFY and "встреч" in transcript_text:
        command = command.model_copy(update={"action": Action.CREATE_MEETING})
    if (
        command.action == Action.CREATE_MEETING
        and "напом" in transcript_text
        and "встреч" not in transcript_text
    ):
        command = command.model_copy(update={"action": Action.CREATE_TASK})
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
        updates["missing_fields"] = ["title"] if not command.title else []
        if not command.title:
            updates["clarification_question"] = "Что нужно добавить в задачу?"

    if command.action in {Action.CREATE_TASK, Action.CREATE_MEETING} and now:
        updates.update(_relative_event_dates(command, now))

    if command.action == Action.CREATE_MEETING:
        updates["event_type"] = EventType.MEETING
        effective_start = updates.get("starts_at", command.starts_at)
        missing = []
        if not command.title:
            missing.append("title")
        if not effective_start or not _has_explicit_time(command.transcript):
            missing.append("start_time")
        updates["missing_fields"] = missing
        if missing:
            updates["clarification_question"] = (
                "На какое время поставить встречу?" if "start_time" in missing
                else "С кем или о чем будет встреча?"
            )

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

        if command.action == Action.LIST_EVENTS:
            updates.update(_relative_period(command.transcript, now)) if now else None
        else:
            updates["date_from"] = None
            updates["date_to"] = None

        if command.action == Action.SEARCH_EVENTS:
            updates["query"] = extract_search_query(command.transcript)

    return command.model_copy(update=updates)


def _relative_event_dates(command: AssistantCommand, now: datetime) -> dict:
    text = normalize_text(command.transcript)
    updates: dict = {}
    event_moment = (
        command.due_at or command.starts_at
        if command.action == Action.CREATE_TASK
        else command.starts_at
    )
    if command.action == Action.CREATE_TASK and not _has_explicit_time(text):
        event_moment = None

    hours = re.search(r"через\s+(\d+|один|два|три|четыре|пять|шесть|семь|восемь|девять|десять)\s+час", text)
    if hours:
        amount = int(hours.group(1)) if hours.group(1).isdigit() else NUMBER_WORDS[hours.group(1)]
        moment = now + timedelta(hours=amount)
        return {"due_at": moment, "starts_at": None, "ends_at": None} if command.action == Action.CREATE_TASK else {"starts_at": moment}

    if "послезавтра" in text:
        return _move_to_date(command, now.date() + timedelta(days=2), event_moment, timezone=now.tzinfo)
    if "завтра" in text:
        return _move_to_date(command, now.date() + timedelta(days=1), event_moment, timezone=now.tzinfo)
    if "сегодня" in text:
        return _move_to_date(command, now.date(), event_moment, timezone=now.tzinfo)

    for name, weekday in WEEKDAY_ALIASES.items():
        if name in text:
            days_ahead = (weekday - now.weekday()) % 7 or 7
            return _move_to_date(command, now.date() + timedelta(days=days_ahead), event_moment, timezone=now.tzinfo)

    if "до конца недели" in text or "на этой неделе" in text:
        sunday = now.date() + timedelta(days=6 - now.weekday())
        return _move_to_date(command, sunday, event_moment, end_of_day=True, timezone=now.tzinfo)
    # A model must not invent a deadline for a request that contains no date.
    has_explicit_date = bool(
        re.search(
            r"\b\d{1,2}[./-]\d{1,2}|\b\d{1,2}\s+(?:числ|январ|феврал|март|апрел|ма[йя]|июн|июл|август|сентябр|октябр|ноябр|декабр)",
            text,
        )
    )
    has_explicit_time = _has_explicit_time(text)
    if not has_explicit_date and not has_explicit_time:
        return {"due_at": None, "starts_at": None, "ends_at": None}
    return updates


def _has_explicit_time(value: str) -> bool:
    text = value.lower().replace("ё", "е")
    return bool(
        re.search(
            r"\bв\s+\d{1,2}\b|\b\d{1,2}(?::\d{2}|\s+\d{2}|\s*(?:час|часа|часов|утра|вечера|дня))\b|\b(?:[01]\d|2[0-3])[0-5]\d\b|через\s+(?:\d+|один|два|три|четыре|пять|шесть|семь|восемь|девять|десять)\s+час",
            text,
        )
        or re.fullmatch(r"\s*(?:[01]?\d|2[0-3])\s*\s*(?:час|часа|часов|утра|вечера|дня)?\s*", text)
    )


def _relative_period(text_value: str, now: datetime) -> dict:
    text = normalize_text(text_value)
    start_date = end_date = None
    if "сегодня" in text:
        start_date = end_date = now.date()
    elif "послезавтра" in text:
        start_date = end_date = now.date() + timedelta(days=2)
    elif "завтра" in text:
        start_date = end_date = now.date() + timedelta(days=1)
    elif "на следующей неделе" in text or "следующую неделю" in text:
        start_date = now.date() + timedelta(days=7 - now.weekday())
        end_date = start_date + timedelta(days=6)
    elif "на этой неделе" in text or "эту неделю" in text:
        start_date = now.date() - timedelta(days=now.weekday())
        end_date = start_date + timedelta(days=6)
    else:
        for name, weekday in WEEKDAY_ALIASES.items():
            if name in text:
                start_date = now.date() + timedelta(days=(weekday - now.weekday()) % 7 or 7)
                end_date = start_date
                break
    if start_date is None:
        return {"date_from": None, "date_to": None}
    tz = now.tzinfo
    return {
        "date_from": datetime.combine(start_date, time.min, tzinfo=tz),
        "date_to": datetime.combine(end_date, time(23, 59, 59), tzinfo=tz),
    }


def _move_to_date(command: AssistantCommand, date_value, existing: datetime | None, end_of_day: bool = False, timezone=None) -> dict:
    moment_time = (
        existing.timetz().replace(tzinfo=None)
        if existing and not end_of_day
        else time(23, 59, 59)
        if end_of_day or command.action == Action.CREATE_TASK
        else time(9, 0)
    )
    moment = datetime.combine(date_value, moment_time)
    moment = moment.replace(tzinfo=existing.tzinfo if existing and existing.tzinfo else timezone)
    if command.action == Action.CREATE_TASK:
        return {"due_at": moment, "starts_at": None, "ends_at": None}
    return {"starts_at": moment}
