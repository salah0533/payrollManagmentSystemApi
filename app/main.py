import asyncio

from fastapi import FastAPI, Request
from app.routes.router import routers
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from app.core.logging import configure_logging
from app.core.localization import reset_current_language, resolve_request_language, set_current_language
from app.core.responses import api_success
from app.db.session import SessionLocal
from app.exceptions.handlers import register_exception_handlers
from app.services.auto_attendance_service import ensure_employee_auto_attendance_schema, run_auto_attendance_loop
from app.services.notification_service import ensure_notification_localization_schema
from app.services.user_service import ensure_user_language_schema
import app.models  

configure_logging()
app = FastAPI()


origins = [
"*"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(routers)
register_exception_handlers(app)


@app.middleware("http")
async def bind_request_language(request: Request, call_next) -> Response:
    token = set_current_language(resolve_request_language(accept_language=request.headers.get("Accept-Language")))
    try:
        return await call_next(request)
    finally:
        reset_current_language(token)


@app.on_event("startup")
def ensure_runtime_schema():
    db = SessionLocal()
    try:
        ensure_user_language_schema(db)
        ensure_employee_auto_attendance_schema(db)
        ensure_notification_localization_schema(db)
        db.commit()
    finally:
        db.close()


@app.on_event("startup")
async def start_auto_attendance_runner():
    app.state.auto_attendance_task = asyncio.create_task(
        run_auto_attendance_loop(),
        name="auto-attendance-runner",
    )


@app.on_event("shutdown")
async def stop_auto_attendance_runner():
    task = getattr(app.state, "auto_attendance_task", None)
    if task is None:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

@app.get("/")
def root():
    return api_success()
