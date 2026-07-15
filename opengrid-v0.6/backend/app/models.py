from datetime import datetime
from enum import StrEnum
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field

class EntityUpsert(BaseModel):
    model_config = ConfigDict(extra="allow")
    entity_id: str = Field(min_length=1, max_length=200)
    is_live: bool = True
    expiry_time: datetime | None = None
    components: dict[str, Any]
    provenance: dict[str, Any] = {}

class ComponentPatch(BaseModel):
    value: Any
    provenance: dict[str, Any] = {}
    source_time: datetime | None = None

class TaskStatus(StrEnum):
    SENT = "STATUS_SENT"
    IN_PROGRESS = "STATUS_IN_PROGRESS"
    DONE_OK = "STATUS_DONE_OK"
    DONE_NOT_OK = "STATUS_DONE_NOT_OK"
    CANCELED = "STATUS_CANCELED"

class TaskSpecification(BaseModel):
    type: str
    objective: dict[str, Any]
    parameters: dict[str, Any] = {}

class TaskCreate(BaseModel):
    description: str = ""
    specification: TaskSpecification
    assigned_agent_id: str
    created_by: str | None = None

class TaskStatusUpdate(BaseModel):
    status: TaskStatus
    progress: float = Field(default=0, ge=0, le=1)
    message: str | None = None
    actor_id: str | None = None

class TaskClaim(BaseModel):
    plugin_id: str

class TaskDefinition(BaseModel):
    type: str
    display_name: str
    objective_types: list[str]
    parameter_schema: dict[str, Any]


class TaskCancel(BaseModel):
    reason: str = "Canceled by operator"
    actor_id: str | None = None

class PluginRegister(BaseModel):
    plugin_id: str
    name: str
    version: str
    plugin_type: str
    protocol: str | None = None
    capabilities: list[str] = []
    configuration_schema: dict[str, Any] = {}
    configuration: dict[str, Any] = {}

class PluginHeartbeat(BaseModel):
    status: str = "RUNNING"
    message: str | None = None
    metrics: dict[str, Any] = {}

class PluginConfigurationPatch(BaseModel):
    configuration: dict[str, Any]

class PluginLogCreate(BaseModel):
    level: str = "INFO"
    message: str
    details: dict[str, Any] = {}

class ArtifactCreateText(BaseModel):
    name: str
    artifact_type: str = "TEXT"
    content_type: str = "text/plain"
    content: str
    related_entity_ids: list[str] = []
    related_task_ids: list[str] = []
    related_plugin_id: str | None = None
    metadata: dict[str, Any] = {}
