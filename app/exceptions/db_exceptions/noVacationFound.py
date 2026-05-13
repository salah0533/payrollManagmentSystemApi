from app.exceptions.base_exception import ResourceNotFoundException


class NoVacationFound(ResourceNotFoundException):
    def __init__(self, message: str | None = None):
        super().__init__("Vacation", message=message or "Vacation not found")
