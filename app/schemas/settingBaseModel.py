from pydantic import BaseModel
from typing import Optional
from datetime import time

class SettingsBaseModel(BaseModel):
    entryTime:Optional[time]=None
    exitTime:Optional[time]=None

    