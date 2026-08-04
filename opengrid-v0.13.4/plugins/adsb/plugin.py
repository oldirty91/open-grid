import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator

import httpx
from opengrid_sdk import OpenGridClient
import websockets

API=os.getenv("OPENGRID_API_URL","http://localhost:8000")
PLUGIN_ID=os.getenv("PLUGIN_ID","opengrid.adsb.reference")
REPLAY_FILE=os.getenv("ADSB_REPLAY_FILE","/data/sample_adsb.jsonl")

DEFAULT_CONFIG={
 "input_mode":os.getenv("ADSB_INPUT_MODE","replay").lower(),
 "poll_interval_s":2.0,
 "replay_interval_s":1.5,
 "readsb_json_url":"http://host.docker.internal:8080/data/aircraft.json",
 "sbs_host":"host.docker.internal",
 "sbs_port":30003,
 "adsb_lol_base_url":"https://api.adsb.lol/v2/point",
 "center_latitude":41.49,
 "center_longitude":-71.31,
 "radius_nm":100,
 "opensky_url":"https://opensky-network.org/api/states/all",
 "bbox":{"lamin":40.5,"lomin":-72.5,"lamax":42.5,"lomax":-70.0},
 "websocket_url":"",
 "websocket_subscription_json":{},
}
metrics={"messages_received":0,"entities_active":0,"parse_errors":0,"reconnects":0,"last_message_time":None,"current_mode":DEFAULT_CONFIG["input_mode"]}
active:set[str]=set(); sbs_cache:dict[str,dict[str,Any]]={}

sdk_client=OpenGridClient(API)
async def call(c,m,path,**kw):
 return await sdk_client.request(m,path,**kw)
async def register(c):
 await call(c,"POST","/api/v1/plugins/register",json={
  "plugin_id":PLUGIN_ID,"name":"ADS-B","version":"0.1.0","plugin_type":"DATA_SOURCE","protocol":"ADS-B",
  "capabilities":["entity.publish","entity.patch"],
  "configuration_schema":{"type":"object","properties":{
   "input_mode":{"type":"string","enum":["replay","readsb_json","sbs_tcp","adsb_lol_rest","opensky_rest","websocket"]},
   "poll_interval_s":{"type":"number"},"readsb_json_url":{"type":"string"},"sbs_host":{"type":"string"},"sbs_port":{"type":"integer"},
   "adsb_lol_base_url":{"type":"string"},"center_latitude":{"type":"number"},"center_longitude":{"type":"number"},"radius_nm":{"type":"number"},
   "opensky_url":{"type":"string"},"bbox":{"type":"object"},"websocket_url":{"type":"string"},"websocket_subscription_json":{"type":"object"}
  }},"configuration":DEFAULT_CONFIG})
async def get_plugin(c):return (await call(c,"GET",f"/api/v1/plugins/{PLUGIN_ID}")).json()
async def get_config(c):
 p=await get_plugin(c);x=dict(DEFAULT_CONFIG);x.update(p.get("configuration") or {});return x
async def log(c,level,message,details=None):
 try:await call(c,"POST",f"/api/v1/plugins/{PLUGIN_ID}/logs",json={"level":level,"message":message,"details":details or {}})
 except Exception:pass
async def heartbeat(c):
 while True:
  try:
   p=await get_plugin(c);await call(c,"POST",f"/api/v1/plugins/{PLUGIN_ID}/heartbeat",json={"status":"RUNNING" if p.get("enabled",True) else "DISABLED","message":f"ADS-B input mode: {metrics['current_mode']}","metrics":metrics})
  except Exception as e:print("[adsb] heartbeat",e)
  await asyncio.sleep(5)

def aircraft_type(d):
 cat=str(d.get("category") or d.get("Category") or "").upper();desc=str(d.get("desc") or d.get("type") or "").upper()
 if "HELI" in desc or cat in {"A7","B7"}:return "HELICOPTER"
 if "CARGO" in desc or "FREIGHT" in desc:return "CARGO_PLANE"
 if "UAV" in desc or "DRONE" in desc:return "UAV"
 return "AIRCRAFT"

def normalize(d):
 hexid=str(d.get("hex") or d.get("icao24") or d.get("icao") or d.get("Hex") or "").strip().lower()
 lat=d.get("lat") if d.get("lat") is not None else d.get("latitude")
 lon=d.get("lon") if d.get("lon") is not None else d.get("longitude")
 if not hexid or lat is None or lon is None:return None
 callsign=str(d.get("flight") or d.get("callsign") or d.get("Callsign") or "").strip() or hexid.upper()
 track=float(d.get("track") or d.get("true_track") or d.get("heading") or 0)
 speed=d.get("gs") if d.get("gs") is not None else d.get("velocity")
 speed_mps=float(speed or 0)*(0.514444 if d.get("gs") is not None else 1.0)
 altitude=d.get("alt_baro") if d.get("alt_baro") is not None else d.get("baro_altitude")
 if isinstance(altitude,str):altitude=None
 altitude_m=float(altitude)*0.3048 if altitude is not None and d.get("alt_baro") is not None else altitude
 return {"entity_id":f"adsb-{hexid}","components":{
  "aliases":{"name":callsign,"callsign":callsign},
  "ontology":{"template":"TRACK","domain":"AIR","track_type":"SOURCE","specific_type":aircraft_type(d)},
  "location":{"latitude":float(lat),"longitude":float(lon),"altitude_m":altitude_m,"heading_degrees":track,"course_degrees":track,"speed_mps":speed_mps},
  "adsb":{"icao24":hexid,"registration":d.get("r") or d.get("registration"),"aircraft_type":d.get("t") or d.get("type"),"squawk":d.get("squawk"),"vertical_rate_mps":float(d.get("baro_rate") or d.get("vertical_rate") or 0)*0.00508,"on_ground":bool(d.get("on_ground",False)),"category":d.get("category")},
  "status":{"state":"LIVE","last_observed_time":datetime.now(timezone.utc).isoformat()},
  "provenance":{"source_system":PLUGIN_ID,"source_protocol":"ADS-B","source_id":hexid}},
  "provenance":{"source_system":PLUGIN_ID,"source_protocol":"ADS-B"}}

async def publish(c,e):
 if not e:return
 await call(c,"PUT",f"/api/v1/entities/{e['entity_id']}",json=e);active.add(e['entity_id']);metrics.update(messages_received=metrics['messages_received']+1,entities_active=len(active),last_message_time=datetime.now(timezone.utc).isoformat())

async def replay_source(cfg):
 rows=[json.loads(x) for x in Path(REPLAY_FILE).read_text().splitlines() if x.strip()];i=0
 while True:
  d=dict(rows[i%len(rows)]);loop=i//len(rows);d['lat']=float(d['lat'])+.001*loop;d['lon']=float(d['lon'])+.0015*loop;yield [d];i+=1;await asyncio.sleep(float(cfg.get('replay_interval_s',1.5)))
async def json_poll_source(cfg,url_builder):
 async with httpx.AsyncClient(timeout=20) as h:
  while True:
   r=await h.get(url_builder(cfg));r.raise_for_status();data=r.json();yield data.get('ac') or data.get('aircraft') or [];await asyncio.sleep(float(cfg.get('poll_interval_s',2)))
async def opensky_source(cfg):
 async with httpx.AsyncClient(timeout=20) as h:
  while True:
   b=cfg.get('bbox') or {};r=await h.get(str(cfg.get('opensky_url')),params=b);r.raise_for_status();states=r.json().get('states') or [];items=[]
   for s in states:
    if len(s)<17:continue
    items.append({'icao24':s[0],'callsign':s[1],'longitude':s[5],'latitude':s[6],'baro_altitude':s[7],'on_ground':s[8],'velocity':s[9],'true_track':s[10],'vertical_rate':s[11],'squawk':s[14]})
   yield items;await asyncio.sleep(float(cfg.get('poll_interval_s',10)))
async def sbs_source(cfg):
 reader,writer=await asyncio.open_connection(str(cfg.get('sbs_host')),int(cfg.get('sbs_port',30003)))
 try:
  while line:=await reader.readline():
   parts=line.decode(errors='ignore').strip().split(',')
   if len(parts)<22 or parts[0]!='MSG':continue
   hx=parts[4].lower();d=sbs_cache.setdefault(hx,{'hex':hx})
   mapping=[('flight',10),('alt_baro',11),('gs',12),('track',13),('lat',14),('lon',15),('baro_rate',16),('squawk',17)]
   for key,idx in mapping:
    if parts[idx] not in ('',None):d[key]=parts[idx]
   if d.get('lat') and d.get('lon'):yield [dict(d)]
 finally:writer.close();await writer.wait_closed()
async def websocket_source(cfg):
 url=str(cfg.get('websocket_url') or '')
 if not url:raise RuntimeError('WebSocket URL is required')
 async with websockets.connect(url,ping_interval=20,ping_timeout=20,max_queue=2048) as ws:
  sub=cfg.get('websocket_subscription_json') or {}
  if sub:await ws.send(json.dumps(sub))
  async for raw in ws:
   data=json.loads(raw);yield data.get('ac') or data.get('aircraft') or ([data] if isinstance(data,dict) else data)

def sig(cfg):return json.dumps(cfg,sort_keys=True)
async def run_source(c,cfg):
 mode=str(cfg.get('input_mode','replay'));metrics['current_mode']=mode;await log(c,'INFO','ADS-B source starting',{'mode':mode})
 if mode=='replay':src=replay_source(cfg)
 elif mode=='readsb_json':src=json_poll_source(cfg,lambda x:str(x.get('readsb_json_url')))
 elif mode=='adsb_lol_rest':src=json_poll_source(cfg,lambda x:f"{str(x.get('adsb_lol_base_url')).rstrip('/')}/{x.get('center_latitude')}/{x.get('center_longitude')}/{x.get('radius_nm')}")
 elif mode=='opensky_rest':src=opensky_source(cfg)
 elif mode=='sbs_tcp':src=sbs_source(cfg)
 elif mode=='websocket':src=websocket_source(cfg)
 else:raise RuntimeError(f'Unsupported ADS-B mode: {mode}')
 start=sig(cfg)
 async for items in src:
  p=await get_plugin(c)
  if not p.get('enabled',True):await asyncio.sleep(1);continue
  if sig(await get_config(c))!=start:return
  for d in items:
   try:await publish(c,normalize(d))
   except Exception:metrics['parse_errors']+=1
async def main():
 async with httpx.AsyncClient(timeout=20) as c:
  while True:
   try:
    if (await c.get(f'{API}/health')).is_success:break
   except Exception:pass
   await asyncio.sleep(2)
  while True:
   try:await register(c);break
   except Exception as e:print('[adsb] register',e);await asyncio.sleep(2)
  asyncio.create_task(heartbeat(c))
  while True:
   try:
    p=await get_plugin(c)
    if not p.get('enabled',True):await asyncio.sleep(2);continue
    await run_source(c,await get_config(c))
   except asyncio.CancelledError:raise
   except Exception as e:metrics['parse_errors']+=1;metrics['reconnects']+=1;print('[adsb] source',e);await log(c,'ERROR','ADS-B source failed',{'error':str(e)});await asyncio.sleep(3)
if __name__=='__main__':asyncio.run(main())
