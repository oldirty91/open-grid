import asyncio, json, os, tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
import httpx
from opengrid_sdk import OpenGridAdapter, AdapterManifest

API=os.getenv("OPENGRID_API_URL","http://api:8000")
PLUGIN=os.getenv("PLUGIN_ID","opengrid.camera.reference")
PUBLIC_TEST_STREAM="https://interactive-examples.mdn.mozilla.net/media/cc0-videos/flower.mp4"
DEFAULT_CAMERAS=[{
 "id":"camera-demo-1","name":"Apple HLS Test Camera","enabled":True,
 "latitude":41.4302,"longitude":-71.4669,"altitude_m":8,
 "direction_deg":135,"horizontal_fov_deg":65,"vertical_fov_deg":35,"range_m":500,
 "snapshot_url":"","stream_url":PUBLIC_TEST_STREAM,"stream_type":"MP4"
}]
SCHEMA={"type":"object","properties":{"cameras":{"type":"array","items":{"type":"object","required":["id","name","latitude","longitude"],"properties":{
 "id":{"type":"string"},"name":{"type":"string"},"enabled":{"type":"boolean"},
 "latitude":{"type":"number"},"longitude":{"type":"number"},"altitude_m":{"type":"number"},
 "direction_deg":{"type":"number"},"horizontal_fov_deg":{"type":"number"},"vertical_fov_deg":{"type":"number"},"range_m":{"type":"number"},
 "snapshot_url":{"type":"string"},"stream_url":{"type":"string"},"stream_type":{"type":"string","enum":["HLS","MP4","MJPEG","IMAGE"]}
}}}}}

adapter=OpenGridAdapter(API,AdapterManifest(
 plugin_id=PLUGIN,name="Fixed Camera Adapter",version="0.3.0",plugin_type="SENSOR_ADAPTER",protocol="CAMERA",
 capabilities=["entity.publish","task.consume","task.status","artifact.publish"],
 configuration_schema=SCHEMA,configuration={"cameras":DEFAULT_CAMERAS},minimum_server_version="0.11.4"))

async def ffmpeg_capture(url:str, duration:int|None=None)->tuple[bytes,str,str]:
 if not url: raise RuntimeError("Camera has no stream or snapshot URL configured")
 suffix=".mp4" if duration else ".jpg"
 with tempfile.TemporaryDirectory() as td:
  out=Path(td)/f"capture{suffix}"
  if duration:
   cmd=["ffmpeg","-y","-loglevel","error","-i",url,"-t",str(duration),"-c:v","libx264","-preset","veryfast","-an","-movflags","+faststart",str(out)]
  else:
   cmd=["ffmpeg","-y","-loglevel","error","-i",url,"-frames:v","1",str(out)]
  proc=await asyncio.create_subprocess_exec(*cmd,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
  _,err=await asyncio.wait_for(proc.communicate(),timeout=max(45,(duration or 0)+30))
  if proc.returncode or not out.exists(): raise RuntimeError(f"ffmpeg capture failed: {err.decode(errors='ignore')[-600:]}")
  return out.read_bytes(),("video/mp4" if duration else "image/jpeg"),suffix[1:]

async def fetch_snapshot(cam)->tuple[bytes,str,str]:
 url=str(cam.get("snapshot_url") or "").strip()
 if url:
  async with httpx.AsyncClient(timeout=30,follow_redirects=True) as client:
   r=await client.get(url);r.raise_for_status();ctype=r.headers.get("content-type","image/jpeg").split(";")[0]
   ext={"image/jpeg":"jpg","image/png":"png","image/webp":"webp"}.get(ctype,"bin")
   return r.content,ctype,ext
 return await ffmpeg_capture(str(cam.get("stream_url") or ""))

async def snapshot(cam,task_id=None):
 data,ctype,ext=await fetch_snapshot(cam); now=datetime.now(timezone.utc)
 return await adapter.client.create_binary_artifact(name=f"{cam['id']}-{now.strftime('%Y%m%dT%H%M%SZ')}.{ext}",artifact_type="CAMERA_SNAPSHOT",content_type=ctype,content=data,related_entity_ids=[cam["id"]],related_task_ids=[task_id] if task_id else [],related_plugin_id=PLUGIN,metadata={"source_entity_id":cam["id"],"captured_at":now.isoformat(),"source_url":cam.get("snapshot_url") or cam.get("stream_url")})

async def record(cam,task_id,duration):
 data,ctype,ext=await ffmpeg_capture(str(cam.get("stream_url") or cam.get("snapshot_url") or ""),duration); now=datetime.now(timezone.utc)
 return await adapter.client.create_binary_artifact(name=f"{cam['id']}-{now.strftime('%Y%m%dT%H%M%SZ')}.{ext}",artifact_type="CAMERA_RECORDING",content_type=ctype,content=data,related_entity_ids=[cam["id"]],related_task_ids=[task_id],related_plugin_id=PLUGIN,metadata={"source_entity_id":cam["id"],"recorded_at":now.isoformat(),"duration_seconds":duration,"source_url":cam.get("stream_url")})

async def publish(cam,is_live=True):
 now=datetime.now(timezone.utc); expiry=(now+timedelta(minutes=2)).isoformat()
 await adapter.publish_entity(cam["id"],{
  "aliases":{"name":cam.get("name",cam["id"])},
  "ontology":{"template":"SENSOR","domain":cam.get("domain","GROUND"),"platform_type":"FIXED_CAMERA","specific_type":"FIXED_CAMERA"},
  "location":{"latitude":float(cam["latitude"]),"longitude":float(cam["longitude"]),"altitude_m":float(cam.get("altitude_m",0)),"heading_degrees":float(cam.get("direction_deg",0)),"speed_mps":0},
  "status":{"state":"ONLINE" if is_live else "DISABLED"},
  "sensor":{"type":"VIDEO_CAMERA","stationary":True,"horizontal_fov_deg":float(cam.get("horizontal_fov_deg",60)),"vertical_fov_deg":float(cam.get("vertical_fov_deg",35)),"range_m":float(cam.get("range_m",500)),"direction_deg":float(cam.get("direction_deg",0))},
  "video":{"snapshot_url":cam.get("snapshot_url",""),"stream_url":cam.get("stream_url",""),"stream_type":str(cam.get("stream_type","HLS")).upper(),"live_available":bool(cam.get("snapshot_url") or cam.get("stream_url"))},
  "capabilities":{"available":[{"name":"CaptureSnapshot"},{"name":"RecordForDuration"}]},
  "task_catalog":{"definitions":[{"type":"opengrid.tasks.v1.CaptureSnapshot","version":"1.0.0"},{"type":"opengrid.tasks.v1.RecordForDuration","version":"1.0.0"}]},
  "provenance":{"source_system":PLUGIN}
 },is_live=is_live,provenance={"source_system":PLUGIN},expiry_time=expiry if is_live else now.isoformat())

async def load_cameras():
 config=await adapter.get_configuration({"cameras":DEFAULT_CAMERAS})
 value=config.get("cameras",DEFAULT_CAMERAS)
 return value if isinstance(value,list) else DEFAULT_CAMERAS

async def main():
 await adapter.start(); cams=[]; signature=""; last_publish=0.0
 while True:
  try:
   fresh=await load_cameras(); new_signature=json.dumps(fresh,sort_keys=True)
   if new_signature!=signature:
    old_ids={c.get("id") for c in cams}; new_ids={c.get("id") for c in fresh}
    for removed in old_ids-new_ids:
     old=next((c for c in cams if c.get("id")==removed),None)
     if old: await publish(old,False)
    cams=fresh; signature=new_signature; await adapter.log("INFO","Camera configuration reloaded",{"camera_count":len(cams)})
   enabled=[c for c in cams if c.get("enabled",True)]
   if asyncio.get_running_loop().time()-last_publish>30:
    for c in enabled: await publish(c)
    last_publish=asyncio.get_running_loop().time()
   adapter.metrics={"entities_active":len(enabled),"configured_cameras":len(cams),"live_sources":sum(bool(c.get("snapshot_url") or c.get("stream_url")) for c in enabled)}
   by_id={c["id"]:c for c in enabled if c.get("id")}
   for eid,cam in by_id.items():
    t=await adapter.claim_next_task(eid)
    if not t: continue
    tid=str(t["task_id"]); typ=t["specification"]["type"].split(".")[-1]
    try:
     await adapter.update_task(tid,status="STATUS_IN_PROGRESS",progress=.1,message=f"Executing {typ}")
     if typ=="CaptureSnapshot": await snapshot(cam,tid)
     elif typ=="RecordForDuration": await record(cam,tid,min(300,max(1,int(t["specification"].get("parameters",{}).get("duration_seconds",30)))))
     else: raise RuntimeError(f"Unsupported task {typ}")
     await adapter.update_task(tid,status="STATUS_DONE_OK",progress=1,message=f"{typ} artifact created")
    except Exception as exc:
     await adapter.log("ERROR",f"{typ} failed",{"camera_id":eid,"error":str(exc)})
     await adapter.update_task(tid,status="STATUS_DONE_NOT_OK",progress=1,message=str(exc))
  except Exception as exc:
   print(f"camera loop: {exc}"); await adapter.log("ERROR","Camera loop error",{"error":str(exc)})
  await asyncio.sleep(2)

if __name__=="__main__": asyncio.run(main())
