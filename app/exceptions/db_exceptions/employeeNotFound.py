from app.exceptions.base_exception import ResourceNotFoundException


class EmployeeNotFound(ResourceNotFoundException):
    def __init__(self, message: str | None = None):
        super().__init__("Employee", message=message or "Employee not found")
