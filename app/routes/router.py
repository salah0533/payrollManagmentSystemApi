from app.routes.routes.attendence import router as att_router
from app.routes.routes.employee import router as emp_router
from app.routes.routes.payment import router as pay_router
from app.routes.routes.stat import router as stat_router
from app.routes.routes.vacation import router as vac_router
from app.routes.routes.attendence_types import router as att_types_router
from app.routes.routes.payment_types import router as payment_types_router
from app.routes.routes.salary_types import router as salary_types_router
from app.routes.routes.vacation_statuses import router as vac_statuses_router
from app.routes.routes.vacation_types import router as vac_types_router
from fastapi import APIRouter


routers = APIRouter()

routers.include_router(att_router,prefix="/attendance",tags=["attendance"])
routers.include_router(emp_router,prefix="/employee",tags=["employee"])
routers.include_router(pay_router,prefix="/payment",tags=["payment"])
routers.include_router(stat_router,prefix="/stat",tags=["stat"])
routers.include_router(vac_router,prefix="/vacation",tags=["vacation"])
routers.include_router(att_types_router,prefix="/att_types",tags=["attendance types"])
routers.include_router(payment_types_router,prefix="/payment_types",tags=["payment types"])
routers.include_router(salary_types_router,prefix="/salary_types",tags=["salary types"])
routers.include_router(vac_statuses_router,prefix="/vacation_status",tags=["vacation status"])
routers.include_router(vac_types_router,prefix="/vacation_types",tags=["vacation types"])
