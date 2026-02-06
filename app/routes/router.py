from app.routes.routes.attendence import att_router
from app.routes.routes.employee import emp_router
from app.routes.routes.payment import pay_router
from app.routes.routes.stat import stat_router
from app.routes.routes.vacation import vac_router
from fastapi import APIRouter


routers = APIRouter()

routers.include_router(att_router,"/attendance",tags=["attendance"])
routers.include_router(emp_router,"/employee",tags=["employee"])
routers.include_router(pay_router,"/payment",tags=["payment"])
routers.include_router(stat_router,"/stat",tags=["stat"])
routers.include_router(vac_router,"/vacation",tags=["vacation"])
