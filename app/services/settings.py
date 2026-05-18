from app.schemas.settingBaseModel import SettingsBaseModel
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.exceptions.base_exception import BadRequestException
from app.models.settings import Settings


def get_settings(db:Session):
    return db.scalar(select(Settings))

def add_new_settings(set:SettingsBaseModel,db:Session):
    new_set = Settings(entry_time=set.entryTime,exit_time=set.exitTime)
    db.add(new_set)
    db.commit()

def update_settings(set:SettingsBaseModel,db:Session):
    setting = db.scalar(select(Settings))

    if not setting:
        raise BadRequestException("Settings row does not exist", code="settings_not_initialized", message_key="errors.settings_not_initialized")
    setting.entry_time = set.entryTime if set.entryTime else setting.entry_time
    setting.exit_time = set.exitTime if set.exitTime else setting.exit_time
    db.commit()
