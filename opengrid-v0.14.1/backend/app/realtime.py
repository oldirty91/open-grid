import asyncio
import json
from typing import Any
from fastapi import WebSocket

class RealtimeHub:
    def __init__(self):
        self.clients: set[WebSocket] = set()
        self.lock = asyncio.Lock()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        async with self.lock:
            self.clients.add(ws)

    async def disconnect(self, ws: WebSocket):
        async with self.lock:
            self.clients.discard(ws)

    async def broadcast(self, message: dict[str, Any]):
        data = json.dumps(message, default=str)
        stale: list[WebSocket] = []
        async with self.lock:
            clients = list(self.clients)
        for ws in clients:
            try:
                await ws.send_text(data)
            except Exception:
                stale.append(ws)
        if stale:
            async with self.lock:
                for ws in stale:
                    self.clients.discard(ws)

hub = RealtimeHub()
