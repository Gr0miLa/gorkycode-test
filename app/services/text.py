import re


STOP_WORDS = {
    "в", "во", "на", "и", "или", "с", "со", "по", "к", "у", "о", "об",
    "от", "до", "за", "для", "про", "мне", "меня", "мой", "мои", "это",
}


def normalize_text(value: str) -> str:
    value = value.lower().replace("ё", "е")
    value = re.sub(r"[^a-zа-я0-9]+", " ", value)
    return " ".join(value.split())


def extract_tags(value: str) -> list[str]:
    words = normalize_text(value).split()
    return sorted({word for word in words if len(word) >= 3 and word not in STOP_WORDS})

