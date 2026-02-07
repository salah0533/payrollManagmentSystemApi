from fastapi import FastAPI
from app.routes.router import routers
from fastapi.middleware.cors import CORSMiddleware
from sqladmin import Admin, ModelView
from app.db.session import engine
import app.models  

from app.models.employees import Employees

app = FastAPI()
admin = Admin(app, engine)


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

@app.get("/")
def root():
    return {"message":"","data":None,"status":True}


class EmployeesAdmin(ModelView, model=Employees):
    column_list = [Employees.id, Employees.fullname]


admin.add_view(EmployeesAdmin)