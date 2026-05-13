from fastapi import FastAPI
from app.routes.router import routers
from fastapi.middleware.cors import CORSMiddleware
from app.core.logging import configure_logging
from app.core.responses import api_success
from app.exceptions.handlers import register_exception_handlers
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

@app.get("/")
def root():
    return api_success()
