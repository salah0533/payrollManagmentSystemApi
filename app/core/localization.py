from __future__ import annotations

from enum import Enum


DEFAULT_LANGUAGE = "en"
SUPPORTED_LANGUAGES = ("en", "fr", "ar")


class LanguageCode(str, Enum):
    en = "en"
    fr = "fr"
    ar = "ar"


def normalize_language(value: str | None) -> str:
    if not value:
        return DEFAULT_LANGUAGE

    normalized = value.strip().lower()
    if normalized in SUPPORTED_LANGUAGES:
        return normalized
    return DEFAULT_LANGUAGE
