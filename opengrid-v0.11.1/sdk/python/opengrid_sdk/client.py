from __future__ import annotations
import asyncio, hashlib, json, random, base64
from typing import Any
import httpx
from .exceptions import OpenGridError

class OpenGridClient:
    def __init__(self, base_url: str, *, timeout: float = 20.0, retries: int = 5):
        self.base_url = base_url.rstrip("/")
        self.retries = retries
        self.http = httpx.AsyncClient(timeout=timeout)

    async def close(self) -> None:
        await self.http.aclose()

    async def request(self, method: str, path: str, **kwargs) -> httpx.Response:
        last: Exception | None = None
        for attempt in range(self.retries):
            try:
                response = await self.http.request(method, f"{self.base_url}{path}", **kwargs)
                response.raise_for_status()
                return response
            except (httpx.HTTPError, OSError) as exc:
                last = exc
                if attempt + 1 >= self.retries:
                    break
                await asyncio.sleep(min(10.0, (2 ** attempt) + random.random()))
        raise OpenGridError(f"{method} {path} failed: {last}")

    async def json(self, method: str, path: str, **kwargs) -> Any:
        return (await self.request(method, path, **kwargs)).json()

    async def wait_until_ready(self) -> dict[str, Any]:
        while True:
            try:
                return await self.json("GET", "/health")
            except Exception:
                await asyncio.sleep(2)

    async def publish_entity(self, entity_id: str, components: dict[str, Any], *, is_live: bool = True, provenance: dict[str, Any] | None = None) -> dict[str, Any]:
        payload={"entity_id":entity_id,"is_live":is_live,"components":components,"provenance":provenance or {},"component_times":{k:__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat() for k in components}}
        return await self.json("PUT", f"/api/v1/entities/{entity_id}", json=payload)

    async def patch_component(self, entity_id: str, component_name: str, value: Any, *, provenance: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self.json("PATCH", f"/api/v1/entities/{entity_id}/components/{component_name}", json={"value":value,"provenance":provenance or {}})

    async def create_text_artifact(self, *, name: str, artifact_type: str, content_type: str, content: str, related_entity_ids: list[str] | None = None, related_task_ids: list[str] | None = None, related_plugin_id: str | None = None, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self.json("POST", "/api/v1/artifacts/text", json={"name":name,"artifact_type":artifact_type,"content_type":content_type,"content":content,"related_entity_ids":related_entity_ids or [],"related_task_ids":related_task_ids or [],"related_plugin_id":related_plugin_id,"metadata":metadata or {}})

    async def create_binary_artifact(self, *, name: str, artifact_type: str, content_type: str, content: bytes, related_entity_ids=None, related_task_ids=None, related_plugin_id=None, metadata=None):
        return await self.json("POST", "/api/v1/artifacts/binary", json={"name":name,"artifact_type":artifact_type,"content_type":content_type,"content_base64":base64.b64encode(content).decode(),"related_entity_ids":related_entity_ids or [],"related_task_ids":related_task_ids or [],"related_plugin_id":related_plugin_id,"metadata":metadata or {}})
