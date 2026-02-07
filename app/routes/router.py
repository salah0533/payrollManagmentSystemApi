from app.routes.routes.attendence import router as att_router
from app.routes.routes.employee import router as emp_router
from app.routes.routes.payment import router as pay_router
from app.routes.routes.stat import router as stat_router
from app.routes.routes.vacation import router as vac_router
from fastapi import APIRouter


routers = APIRouter()

routers.include_router(att_router,prefix="/attendance",tags=["attendance"])
routers.include_router(emp_router,prefix="/employee",tags=["employee"])
routers.include_router(pay_router,prefix="/payment",tags=["payment"])
routers.include_router(stat_router,prefix="/stat",tags=["stat"])
routers.include_router(vac_router,prefix="/vacation",tags=["vacation"])
