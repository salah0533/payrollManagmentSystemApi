from app.exceptions.base_exception import NotFoundException


class NoEntryTimeFound(NotFoundException):
    def __init__(self, message: str | None = None):
        super().__init__(message or "Entry time not found", code="entry_time_not_found")
