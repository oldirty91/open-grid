import asyncio, os
from opengrid_sdk import AdapterManifest, OpenGridAdapter
async def main():
    adapter=OpenGridAdapter(os.getenv("OPENGRID_API_URL","http://localhost:8000"), AdapterManifest(plugin_id="opengrid.example",name="Example",version="0.1.0",plugin_type="SENSOR_ADAPTER",capabilities=["entity.publish"]))
    await adapter.start()
    await adapter.publish_entity("example-sensor", {"aliases":{"name":"Example Sensor"},"ontology":{"template":"SENSOR","specific_type":"FIXED_SENSOR"},"location":{"latitude":41.49,"longitude":-71.31},"status":{"state":"LIVE"}})
    await asyncio.Event().wait()
asyncio.run(main())
