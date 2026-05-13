from app.routes.routes.audit import router as audit_router
from app.routes.routes.auth import router as auth_router
from app.routes.routes.attendence import router as att_router
from app.routes.routes.employee import router as emp_router
from app.routes.routes.me import router as me_router
from app.routes.routes.payment import router as pay_router
from app.routes.routes.payroll import router as payroll_router
from app.routes.routes.stat import router as stat_router
from app.routes.routes.users import router as users_router
from app.routes.routes.vacation import router as vac_router
from app.routes.routes.attendence_types import router as att_types_router
from app.routes.routes.payment_types import router as payment_types_router
from app.routes.routes.salary_types import router as salary_types_router
from app.routes.routes.vacation_statuses import router as vac_statuses_router
from app.routes.routes.vacation_types import router as vac_types_router
from app.routes.routes.annual_vacations import router as ann_vac_router
from app.routes.routes.settings import router as settings_router
from fastapi import APIRouter


routers = APIRouter()

routers.include_router(audit_router,prefix="/audit",tags=["audit"])
routers.include_router(auth_router,prefix="/auth",tags=["auth"])
routers.include_router(users_router,prefix="/users",tags=["users"])
routers.include_router(me_router,prefix="/me",tags=["me"])
routers.include_router(att_router,prefix="/attendance",tags=["attendance"])
routers.include_router(emp_router,prefix="/employee",tags=["employee"])
routers.include_router(pay_router,prefix="/payment",tags=["payment"])
routers.include_router(payroll_router,prefix="/payroll",tags=["payroll"])
routers.include_router(stat_router,prefix="/stat",tags=["stat"])
routers.include_router(vac_router,prefix="/vacation",tags=["vacation"])
routers.include_router(ann_vac_router,prefix="/annual_vacations",tags=["annual vacations"])
routers.include_router(settings_router,prefix="/settings",tags=["settings"])
routers.include_router(att_types_router,prefix="/att_types",tags=["attendance types"])
routers.include_router(payment_types_router,prefix="/payment_types",tags=["payment types"])
routers.include_router(salary_types_router,prefix="/salary_types",tags=["salary types"])
routers.include_router(vac_statuses_router,prefix="/vacation_status",tags=["vacation status"])
routers.include_router(vac_types_router,prefix="/vacation_types",tags=["vacation types"])
