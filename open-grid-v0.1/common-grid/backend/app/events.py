import json,nats
from app.config import settings
class EventBus:
    def __init__(self): self.nc=None; self.js=None
    async def connect(self):
        self.nc=await nats.connect(settings.nats_url); self.js=self.nc.jetstream()
        try: await self.js.add_stream(name='COMMONGRID',subjects=['entities.>','tasks.>','fusion.>'])
        except Exception: pass
    async def close(self):
        if self.nc: await self.nc.drain()
    async def publish(self,subject,payload):
        if self.js: await self.js.publish(subject,json.dumps(payload,default=str).encode())
event_bus=EventBus()
