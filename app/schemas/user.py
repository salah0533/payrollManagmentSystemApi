from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.core.localization import LanguageCode


class EmployeeStatus(str, Enum):
    active = "active"
    inactive = "inactive"
    suspended = "suspended"


class PermissionRead(BaseModel):
    id: int
    code: str
    name: str
    description: Optional[str] = None
    module: Optional[str] = None


class RoleRead(BaseModel):
    id: int
    code: str
    name: str
    description: Optional[str] = None
    is_system_role: bool
    permissions: list[PermissionRead] = []


class EmployeeReferenceCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return " ".join(value.strip().split())


class DepartmentRead(BaseModel):
    id: int
    name: str
    is_active: bool


class PositionRead(BaseModel):
    id: int
    name: str
    is_active: bool


class UserRead(BaseModel):
    id: int
    employee_id: int | None
    username: str
    email: Optional[EmailStr] = None
    language: LanguageCode
    is_active: bool
    must_change_password: bool
    last_login_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    roles: list[RoleRead] = []


class UserCreateRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: Optional[EmailStr] = None
    password: str = Field(..., min_length=8, max_length=255)
    employee_id: int | None = None
    language: LanguageCode = LanguageCode.en
    role_ids: list[int] = Field(default_factory=list)
    is_active: bool = True
    must_change_password: bool = True

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        return value.strip()


class UserUpdateRequest(BaseModel):
    username: Optional[str] = Field(None, min_length=3, max_length=50)
    email: Optional[EmailStr] = None
    employee_id: int | None = None
    language: Optional[LanguageCode] = None
    is_active: Optional[bool] = None
    must_change_password: Optional[bool] = None

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: Optional[str]) -> Optional[str]:
        return value.strip() if value else value


class UserRoleAssignRequest(BaseModel):
    role_ids: list[int] = Field(..., min_length=1)


class UserResetPasswordRequest(BaseModel):
    new_password: str = Field(..., min_length=8, max_length=255)
    must_change_password: bool = True


class EmployeeBasePayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    first_name: str = Field(..., min_length=1, max_length=50)
    last_name: str = Field(..., min_length=1, max_length=50)
    email: Optional[EmailStr] = None
    phone: str = Field(..., min_length=3, max_length=20)
    department_id: Optional[int] = None
    position_id: Optional[int] = None
    position: Optional[str] = Field(None, max_length=100)
    status: EmployeeStatus = EmployeeStatus.active
    hire_date: Optional[date] = None
    dues: Decimal = Decimal("0.00")
    extra_hours_price: Decimal = Decimal("0.00")
    vacation_days: int = 0
    hour_price: Decimal = Decimal("0.00")
    day_price: Decimal = Decimal("0.00")
    monthly_price: Decimal = Field(Decimal("0.00"), alias="month_price")
    salary_type: int = 0
    joined: Optional[date] = None

    @model_validator(mode="after")
    def sync_dates(self):
        if self.hire_date is None and self.joined is not None:
            self.hire_date = self.joined
        if self.joined is None and self.hire_date is not None:
            self.joined = self.hire_date
        return self


class EmployeeCreateRequest(EmployeeBasePayload):
    create_user_account: bool = False
    username: Optional[str] = None
    password: Optional[str] = None
    user_email: Optional[EmailStr] = None
    role_ids: list[int] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_optional_account(self):
        if self.create_user_account:
            if not self.username or not self.password:
                raise ValueError("username and password are required when create_user_account is true")
        return self


class EmployeeUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    department_id: Optional[int] = None
    position_id: Optional[int] = None
    position: Optional[str] = None
    status: Optional[EmployeeStatus] = None
    hire_date: Optional[date] = None
    dues: Optional[Decimal] = None
    extra_hours_price: Optional[Decimal] = None
    vacation_days: Optional[int] = None
    hour_price: Optional[Decimal] = None
    day_price: Optional[Decimal] = None
    monthly_price: Optional[Decimal] = Field(None, alias="month_price")
    salary_type: Optional[int] = None
    joined: Optional[date] = None


class EmployeeRead(BaseModel):
    id: int
    first_name: str
    last_name: str
    full_name: str
    email: Optional[EmailStr] = None
    phone: str
    department_id: Optional[int] = None
    position_id: Optional[int] = None
    position: Optional[str] = None
    status: str
    hire_date: Optional[date] = None
    dues: Decimal
    salary_type: int
    monthly_price: Decimal
    day_price: Decimal
    hour_price: Decimal
    extra_hours_price: Decimal
    vacation_days: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    user_id: Optional[int] = None


class SelfAttendanceActionRequest(BaseModel):
    event_time: Optional[datetime] = None
    note: Optional[str] = None


class SelfVacationRequestCreate(BaseModel):
    start_date: date
    end_date: date
    vacation_type: int
    is_paid: bool

    @model_validator(mode="after")
    def validate_dates(self):
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self
