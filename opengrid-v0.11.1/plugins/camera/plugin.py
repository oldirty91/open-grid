import asyncio,io,os,time
from datetime import datetime,timezone
from PIL import Image,ImageDraw
from opengrid_sdk import OpenGridAdapter,AdapterManifest
API=os.getenv("OPENGRID_API_URL","http://api:8000"); ENTITY=os.getenv("CAMERA_ENTITY_ID","sensor-ridot-south-pier"); PLUGIN=os.getenv("PLUGIN_ID","opengrid.camera.ridot")
adapter=OpenGridAdapter(API,AdapterManifest(plugin_id=PLUGIN,name="RIDOT Fixed Camera",version="0.1.0",plugin_type="SENSOR_ADAPTER",protocol="HTTP_IMAGE",capabilities=["entity.publish","task.consume","task.status","artifact.publish"],configuration={"mode":"demo","source_page":"https://www.dot.ri.gov/travel/cameras_scounty.php"},minimum_server_version="0.11.0"))
def frame():
 im=Image.new("RGB",(960,540),(22,29,36));d=ImageDraw.Draw(im);now=datetime.now().astimezone();d.rectangle((0,0,960,62),fill=(8,14,20));d.text((24,20),"RIDOT SOUTH PIER ROAD — DEMO CAMERA ADAPTER",fill=(210,235,245));d.text((24,90),"Configure CAMERA_SOURCE_URL for a native MJPEG/JPEG source.",fill=(180,200,214));d.text((24,130),now.strftime("%Y-%m-%d %H:%M:%S %Z"),fill=(120,235,170));d.polygon([(0,540),(380,270),(580,270),(960,540)],fill=(47,54,59));d.line((480,300,480,540),fill=(240,210,70),width=5);d.line((360,400,600,400),fill=(225,225,225),width=4);b=io.BytesIO();im.save(b,"JPEG",quality=85);return b.getvalue()
async def artifact(task=None,kind="CAMERA_SNAPSHOT"):
 data=frame();name=f"south-pier-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.jpg";return await adapter.client.create_binary_artifact(name=name,artifact_type=kind,content_type="image/jpeg",content=data,related_entity_ids=[ENTITY],related_task_ids=[task] if task else [],related_plugin_id=PLUGIN,metadata={"source_entity_id":ENTITY,"captured_at":datetime.now(timezone.utc).isoformat(),"source_page":"https://www.dot.ri.gov/travel/cameras_scounty.php","demo_frame":True})
async def main():
 await adapter.start();await adapter.publish_entity(ENTITY,{"aliases":{"name":"RIDOT South Pier Road Camera"},"ontology":{"template":"SENSOR","domain":"GROUND","platform_type":"FIXED_CAMERA","specific_type":"FIXED_CAMERA"},"location":{"latitude":41.4302,"longitude":-71.4669,"speed_mps":0,"heading_degrees":0},"status":{"state":"ONLINE"},"sensor":{"type":"VIDEO_CAMERA","stationary":True},"video":{"mode":"DEMO","source_page":"https://www.dot.ri.gov/travel/cameras_scounty.php"},"capabilities":{"available":[{"name":"CaptureSnapshot"},{"name":"RecordForDuration"}]},"task_catalog":{"definitions":[{"type":"opengrid.tasks.v1.CaptureSnapshot","version":"1.0.0"},{"type":"opengrid.tasks.v1.RecordForDuration","version":"1.0.0"}]},"provenance":{"source_system":PLUGIN}},provenance={"source_system":PLUGIN});adapter.metrics={"entities":1,"mode":"demo"}
 while True:
  try:
   t=await adapter.claim_next_task(ENTITY)
   if t:
    tid=str(t["task_id"]);typ=t["specification"]["type"].split(".")[-1];await adapter.update_task(tid,status="STATUS_IN_PROGRESS",progress=.1,message="Capturing camera data")
    if typ=="CaptureSnapshot": await artifact(tid)
    elif typ=="RecordForDuration":
     duration=min(60,int(t["specification"].get("parameters",{}).get("duration_seconds",10)));await asyncio.sleep(duration);await artifact(tid,"VIDEO_RECORDING_DEMO")
    else: raise RuntimeError(f"Unsupported camera task {typ}")
    await adapter.update_task(tid,status="STATUS_DONE_OK",progress=1,message="Artifact published")
  except Exception as e: await adapter.log("ERROR","camera loop error",{"error":str(e)})
  await asyncio.sleep(1)
if __name__=="__main__": asyncio.run(main())
