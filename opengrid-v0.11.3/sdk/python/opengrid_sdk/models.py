from dataclasses import dataclass, field
from typing import Any

@dataclass(slots=True)
class AdapterManifest:
    plugin_id: str
    name: str
    version: str
    plugin_type: str
    protocol: str | None = None
    capabilities: list[str] = field(default_factory=list)
    configuration_schema: dict[str, Any] = field(default_factory=dict)
    configuration: dict[str, Any] = field(default_factory=dict)
    minimum_server_version: str = "0.11.0"
    sdk_api_version: str = "v1"

@dataclass(slots=True)
class RecordingDescriptor:
    recording_type: str
    entity_id: str | None = None
    task_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
