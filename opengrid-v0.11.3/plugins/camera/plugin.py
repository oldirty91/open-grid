import asyncio, json, os
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse
import httpx
from opengrid_sdk import OpenGridAdapter, AdapterManifest

API=os.getenv("OPENGRID_API_URL","http://api:8000")
PLUGIN=os.getenv("PLUGIN_ID","opengrid.camera.reference")
DEFAULT_CAMERAS=[{
 "id":"camera-demo-1","name":"Example Fixed Camera","latitude":41.4302,"longitude":-71.4669,
 "altitude_m":8,"direction_deg":135,"horizontal_fov_deg":65,"range_m":500,
 "snapshot_url":"","stream_url":"","stream_type":"IMAGE"
}]

def cameras():
 raw=os.getenv("CAMERAS_JSON","").strip()
 if not raw:return DEFAULT_CAMERAS
 value=json.loads(raw)
 if not isinstance(value,list):raise ValueError("CAMERAS_JSON must be a JSON array")
 return value

adapter=OpenGridAdapter(API,AdapterManifest(
 plugin_id=PLUGIN,name="Fixed Camera Adapter",version="0.2.0",plugin_type="SENSOR_ADAPTER",protocol="HTTP_VIDEO",
 capabilities=["entity.publish","task.consume","task.status","artifact.publish"],
 configuration={"camera_count":len(cameras()),"configuration":"CAMERAS_JSON"},minimum_server_version="0.11.3"))

async def fetch_bytes(url:str)->tuple[bytes,str]:
 if not url: raise RuntimeError("Camera has no snapshot_url configured")
 async with httpx.AsyncClient(timeout=30,follow_redirects=True) as client:
  r=await client.get(url);r.raise_for_status();return r.content,r.headers.get("content-type","image/jpeg").split(";")[0]

async def snapshot(cam,task_id=None):
 data,ctype=await fetch_bytes(cam.get("snapshot_url", ""))
 ext={"image/jpeg":"jpg","image/png":"png","image/webp":"webp"}.get(ctype,"bin")
 now=datetime.now(timezone.utc)
 return await adapter.client.create_binary_artifact(
  name=f"{cam['id']}-{now.strftime('%Y%m%dT%H%M%SZ')}.{ext}",artifact_type="CAMERA_SNAPSHOT",
  content_type=ctype,content=data,related_entity_ids=[cam["id"]],related_task_ids=[task_id] if task_id else [],
  related_plugin_id=PLUGIN,metadata={"source_entity_id":cam["id"],"captured_at":now.isoformat(),"source_url":cam.get("snapshot_url")})

async def recording_reference(cam,task_id,duration):
 # Generic cameras expose many incompatible stream formats. Until a recorder backend is configured,
 # preserve the operator command and stream reference honestly rather than fabricating video bytes.
 now=datetime.now(timezone.utc)
 return await adapter.client.create_text_artifact(
  name=f"{cam['id']}-recording-{now.strftime('%Y%m%dT%H%M%SZ')}.json",artifact_type="CAMERA_RECORDING_REFERENCE",
  content_type="application/json",content=json.dumps({"camera_id":cam["id"],"stream_url":cam.get("stream_url"),"requested_duration_seconds":duration,"requested_at":now.isoformat()},indent=2),
  related_entity_ids=[cam["id"]],related_task_ids=[task_id],related_plugin_id=PLUGIN,
  metadata={"source_entity_id":cam["id"],"stream_url":cam.get("stream_url"),"duration_seconds":duration,"recording_mode":"REFERENCE_ONLY"})

async def publish(cam):
 now=datetime.now(timezone.utc); expiry=(now+timedelta(minutes=2)).isoformat()
 await adapter.publish_entity(cam["id"],{
  "aliases":{"name":cam.get("name",cam["id"])},
  "ontology":{"template":"SENSOR","domain":cam.get("domain","GROUND"),"platform_type":"FIXED_CAMERA","specific_type":"FIXED_CAMERA"},
  "location":{"latitude":float(cam["latitude"]),"longitude":float(cam["longitude"]),"altitude_m":float(cam.get("altitude_m",0)),"heading_degrees":float(cam.get("direction_deg",0)),"speed_mps":0},
  "status":{"state":"ONLINE"},
  "sensor":{"type":"VIDEO_CAMERA","stationary":True,"horizontal_fov_deg":float(cam.get("horizontal_fov_deg",60)),"range_m":float(cam.get("range_m",500)),"direction_deg":float(cam.get("direction_deg",0))},
  "video":{"snapshot_url":cam.get("snapshot_url",""),"stream_url":cam.get("stream_url",""),"stream_type":cam.get("stream_type","IMAGE"),"live_available":bool(cam.get("snapshot_url") or cam.get("stream_url"))},
  "capabilities":{"available":[{"name":"CaptureSnapshot"},{"name":"RecordForDuration"}]},
  "task_catalog":{"definitions":[{"type":"opengrid.tasks.v1.CaptureSnapshot","version":"1.0.0"},{"type":"opengrid.tasks.v1.RecordForDuration","version":"1.0.0"}]},
  "provenance":{"source_system":PLUGIN}
 },provenance={"source_system":PLUGIN},expiry_time=expiry)

async def main():
 cams=cameras(); by_id={c["id"]:c for c in cams}; await adapter.start()
 for c in cams: await publish(c)
 adapter.metrics={"entities":len(cams),"configured_live_sources":sum(bool(c.get("snapshot_url") or c.get("stream_url")) for c in cams)}
 last_publish=0
 while True:
  try:
   if asyncio.get_running_loop().time()-last_publish>30:
    for c in cams: await publish(c)
    last_publish=asyncio.get_running_loop().time()
   for eid,cam in by_id.items():
    t=await adapter.claim_next_task(eid)
    if not t: continue
    tid=str(t["task_id"]); typ=t["specification"]["type"].split(".")[-1]
    await adapter.update_task(tid,status="STATUS_IN_PROGRESS",progress=.1,message=f"Executing {typ}")
    if typ=="CaptureSnapshot": await snapshot(cam,tid)
    elif typ=="RecordForDuration":
     duration=min(3600,int(t["specification"].get("parameters",{}).get("duration_seconds",30)))
     await recording_reference(cam,tid,duration)
    else: raise RuntimeError(f"Unsupported camera task {typ}")
    await adapter.update_task(tid,status="STATUS_DONE_OK",progress=1,message="Artifact published")
  except Exception as e: await adapter.log("ERROR","camera loop error",{"error":str(e)})
  await asyncio.sleep(1)
if __name__=="__main__": asyncio.run(main())
