from pathlib import Path

from scripts.import_seed import infer_type


def test_seed_file_has_expected_rows():
    path = Path("voice_assistant_events_1000.csv")
    assert path.exists()
    assert sum(1 for _ in path.open(encoding="utf-8-sig")) == 1001


def test_infer_type():
    assert infer_type("Встреча с командой") == "meeting"
    assert infer_type("Напомнить Ивану про CRM") == "reminder"
    assert infer_type("Подготовить отчет") == "task"

