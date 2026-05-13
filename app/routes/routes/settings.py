from fastapi import APIRouter,Depends
from app.services.settings import update_settings,add_new_settings,get_settings as get_settings_svc
from app.schemas.settingBaseModel import SettingsBaseModel
from sqlalchemy.orm import Session
from app.db.session import get_db

router = APIRouter()

@router.get("/")
def get_settings(db:Session=Depends(get_db)):
    res = get_settings_svc(db)
    return {"message":"","data":res,"status":True}
    
# @router.put("/")
# def add_new(set:SettingsBaseModel,db:Session=Depends(get_db)):
#     add_new_settings(set,db)
#     return {"message":"","data":None,"status":True}

@router.post("/")
def get_salary_types(set:SettingsBaseModel,db:Session=Depends(get_db)):
    update_settings(set,db)
    return {"message":"","data":None,"status":True}

