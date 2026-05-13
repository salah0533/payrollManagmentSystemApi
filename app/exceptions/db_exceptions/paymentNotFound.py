from app.exceptions.base_exception import ResourceNotFoundException


class PaymentNotFound(ResourceNotFoundException):
    def __init__(self, message: str | None = None):
        super().__init__("Payment", message=message or "Payment not found")
