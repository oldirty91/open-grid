from __future__ import annotations
import asyncio
from contextlib import suppress
from typing import Any
from .client import OpenGridClient
from .models import AdapterManifest

class OpenGridAdapter:
    def __init__(self, base_url: str, manifest: AdapterManifest, *, heartbeat_interval: float = 5.0):
        self.client=OpenGridClient(base_url)
        self.manifest=manifest
        self.heartbeat_interval=heartbeat_interval
        self.metrics: dict[str, Any]={}
        self._heartbeat_task: asyncio.Task | None=None
        self._stopping=False

    async def start(self) -> None:
        health=await self.client.wait_until_ready()
        await self.client.json("POST", "/api/v1/plugins/register", json={
            "plugin_id":self.manifest.plugin_id,"name":self.manifest.name,"version":self.manifest.version,
            "plugin_type":self.manifest.plugin_type,"protocol":self.manifest.protocol,
            "capabilities":self.manifest.capabilities,"configuration_schema":self.manifest.configuration_schema,
            "configuration":self.manifest.configuration})
        self._heartbeat_task=asyncio.create_task(self._heartbeat_loop(), name=f"{self.manifest.plugin_id}-heartbeat")

    async def stop(self) -> None:
        self._stopping=True
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            with suppress(asyncio.CancelledError): await self._heartbeat_task
        await self.client.close()

    async def _heartbeat_loop(self) -> None:
        while not self._stopping:
            try: await self.heartbeat()
            except Exception as exc: print(f"[{self.manifest.plugin_id}] heartbeat: {exc}")
            await asyncio.sleep(self.heartbeat_interval)

    async def heartbeat(self, *, status: str="RUNNING", message: str | None=None) -> None:
        await self.client.json("POST", f"/api/v1/plugins/{self.manifest.plugin_id}/heartbeat", json={"status":status,"message":message,"metrics":self.metrics})

    async def get_plugin(self) -> dict[str, Any]:
        return await self.client.json("GET", f"/api/v1/plugins/{self.manifest.plugin_id}")

    async def get_configuration(self, defaults: dict[str, Any] | None=None) -> dict[str, Any]:
        plugin=await self.get_plugin(); result=dict(defaults or {}); result.update(plugin.get("configuration") or {}); return result

    async def log(self, level: str, message: str, details: dict[str, Any] | None=None) -> None:
        try: await self.client.json("POST", f"/api/v1/plugins/{self.manifest.plugin_id}/logs", json={"level":level,"message":message,"details":details or {}})
        except Exception: pass

    async def publish_entity(self, entity_id: str, components: dict[str, Any], *, is_live: bool=True, provenance: dict[str, Any] | None=None):
        return await self.client.publish_entity(entity_id, components, is_live=is_live, provenance=provenance)

    async def claim_next_task(self, agent_id: str):
        return await self.client.json("POST", f"/api/v1/tasks/claim-next/{agent_id}", json={"plugin_id":self.manifest.plugin_id})

    async def update_task(self, task_id: str, *, status: str, progress: float=0, message: str | None=None, execution: dict[str, Any] | None=None):
        return await self.client.json("POST", f"/api/v1/tasks/{task_id}/status", json={"status":status,"progress":progress,"message":message,"execution":execution or {},"actor_id":self.manifest.plugin_id})
