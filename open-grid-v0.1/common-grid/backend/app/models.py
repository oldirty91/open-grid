from enum import StrEnum
from datetime import datetime
from typing import Any
from pydantic import BaseModel,Field
class EntityUpsert(BaseModel):
    entity_id:str=Field(min_length=1,max_length=200)
    is_live:bool=True
    expiry_time:datetime|None=None
    components:dict[str,Any]
class TaskState(StrEnum):
    DRAFT='DRAFT'; PENDING_APPROVAL='PENDING_APPROVAL'; SENT='SENT'; ACKNOWLEDGED='ACKNOWLEDGED'; ACCEPTED='ACCEPTED'; EXECUTING='EXECUTING'; PAUSED='PAUSED'; SUCCEEDED='SUCCEEDED'; FAILED='FAILED'; CANCELED='CANCELED'; REJECTED='REJECTED'; EXPIRED='EXPIRED'
class TaskCreate(BaseModel):
    task_type:str; description:str=''; assigned_agents:list[str]=[]; objective_entity_id:str|None=None; parameters:dict[str,Any]={}; created_by:str|None=None
class TaskStatusUpdate(BaseModel):
    state:TaskState; progress:float=Field(default=0,ge=0,le=1); message:str|None=None
