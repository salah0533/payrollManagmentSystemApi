from sqlalchemy.orm import DeclarativeBase
from app.models.employees import Employees
from app.models.attendence import Attendence
from app.models.attendence_types import AttendenceTypes
from app.models.payment_types import PaymentTypes
from app.models.payments import Payments
from app.models.salaryType import SalaryType
from app.models.settings import Settings
from app.models.vacation import Vacation
from app.models.vacation_types import VacationTypes
from app.models.vacation_status import VacationStatus


class Base(DeclarativeBase):
    pass