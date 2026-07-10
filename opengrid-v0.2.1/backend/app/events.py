import json
from typing import Any
import nats
from app.config import settings

class EventBus:
    def __init__(self):
        self.nc = None
        self.js = None

    async def connect(self):
        self.nc = await nats.connect(settings.nats_url)
        self.js = self.nc.jetstream()
        try:
            await self.js.add_stream(
                name="OPENGRID",
                subjects=["entity.>", "task.>", "fusion.>", "artifact.>"],
            )
        except Exception:
            pass

    async def close(self):
        if self.nc:
            await self.nc.drain()

    async def publish(self, subject: str, payload: dict[str, Any]) -> bool:
        """Best-effort internal publication.

        PostgreSQL is authoritative. A temporary NATS/JetStream failure must not
        turn an already-committed entity or task write into an HTTP 500.
        """
        if not self.js:
            return False
        try:
            await self.js.publish(
                subject,
                json.dumps(payload, default=str).encode(),
            )
            return True
        except Exception as exc:
            print(f"[event-bus] publish failed for {subject}: {exc}")
            return False

event_bus = EventBus()
