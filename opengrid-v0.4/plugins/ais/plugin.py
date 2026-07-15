import asyncio,json,os,socket
from datetime import datetime,timezone
from pathlib import Path
import httpx
from pyais import decode
API=os.getenv("OPENGRID_API_URL","http://localhost:8000");PLUGIN_ID=os.getenv("PLUGIN_ID","opengrid.ais.reference");MODE=os.getenv("AIS_INPUT_MODE","replay").lower();REPLAY_FILE=os.getenv("AIS_REPLAY_FILE","/data/sample_ais.jsonl");INTERVAL=float(os.getenv("AIS_REPLAY_INTERVAL_S","1.5"));UDP_HOST=os.getenv("AIS_UDP_HOST","0.0.0.0");UDP_PORT=int(os.getenv("AIS_UDP_PORT","10110"));TCP_HOST=os.getenv("AIS_TCP_HOST","127.0.0.1");TCP_PORT=int(os.getenv("AIS_TCP_PORT","10110"))
metrics={"messages_received":0,"entities_active":0,"parse_errors":0,"last_message_time":None};active=set();SHIP={30:"FISHING_VESSEL",36:"SAILING_VESSEL",37:"PLEASURE_CRAFT",60:"PASSENGER_SHIP",70:"CARGO_SHIP",80:"TANKER"}
async def call(c,m,path,**kw):
 r=await c.request(m,f"{API}{path}",**kw);r.raise_for_status();return r
async def register(c):
 await call(c,"POST","/api/v1/plugins/register",json={"plugin_id":PLUGIN_ID,"name":"Reference AIS","version":"0.1.0","plugin_type":"DATA_SOURCE","protocol":"AIS","capabilities":["entity.publish","entity.patch","artifact.publish"],"configuration_schema":{"type":"object","properties":{"input_mode":{"type":"string","enum":["replay","udp","tcp"]}}},"configuration":{"input_mode":MODE,"udp_host":UDP_HOST,"udp_port":UDP_PORT,"tcp_host":TCP_HOST,"tcp_port":TCP_PORT}})
async def heartbeat(c):
 while True:
  try:
   p=(await call(c,"GET",f"/api/v1/plugins/{PLUGIN_ID}")).json();await call(c,"POST",f"/api/v1/plugins/{PLUGIN_ID}/heartbeat",json={"status":"RUNNING" if p.get("enabled",True) else "DISABLED","message":f"AIS input mode: {MODE}","metrics":metrics})
  except Exception as e: print("heartbeat",e)
  await asyncio.sleep(5)
def normalize(d):
 m=d.get("mmsi");lat=d.get("lat");lon=d.get("lon")
 if not m or lat is None or lon is None:return None
 st=d.get("ship_type");course=float(d.get("course") or d.get("heading") or 0);kn=float(d.get("speed") or 0)
 return {"entity_id":f"ais-{m}","components":{"aliases":{"name":d.get("shipname") or f"MMSI {m}","callsign":d.get("callsign")},"ontology":{"template":"TRACK","domain":"MARITIME","track_type":"SOURCE","specific_type":SHIP.get(st,"VESSEL")},"location":{"latitude":float(lat),"longitude":float(lon),"heading_degrees":course,"course_degrees":course,"speed_mps":kn*0.514444},"ais":{"mmsi":int(m),"ship_type":st,"navigation_status":d.get("status"),"destination":d.get("destination")},"status":{"state":"LIVE","last_observed_time":datetime.now(timezone.utc).isoformat()},"provenance":{"source_system":PLUGIN_ID,"source_protocol":"AIS","source_id":str(m)}},"provenance":{"source_system":PLUGIN_ID,"source_protocol":"AIS"}}
async def publish(c,d):
 e=normalize(d)
 if not e:return
 await call(c,"PUT",f"/api/v1/entities/{e['entity_id']}",json=e);active.add(e['entity_id']);metrics.update(messages_received=metrics['messages_received']+1,entities_active=len(active),last_message_time=datetime.now(timezone.utc).isoformat())
async def replay():
 rows=[json.loads(x) for x in Path(REPLAY_FILE).read_text().splitlines() if x.strip()];i=0
 while True:
  d=dict(rows[i%len(rows)]);loop=i//len(rows);d['lat']=float(d['lat'])+.00015*loop;d['lon']=float(d['lon'])+.00010*loop;yield d;i+=1;await asyncio.sleep(INTERVAL)
async def udp():
 loop=asyncio.get_running_loop();sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);sock.bind((UDP_HOST,UDP_PORT));sock.setblocking(False)
 while True:
  b,_=await loop.sock_recvfrom(sock,8192)
  try:yield decode(b.decode(errors='ignore').strip()).asdict()
  except Exception:metrics['parse_errors']+=1
async def tcp():
 while True:
  try:
   r,_=await asyncio.open_connection(TCP_HOST,TCP_PORT)
   while line:=await r.readline():
    try:yield decode(line.decode(errors='ignore').strip()).asdict()
    except Exception:metrics['parse_errors']+=1
  except Exception:await asyncio.sleep(3)
async def main():
 async with httpx.AsyncClient(timeout=15) as c:
  while True:
   try:
    if (await c.get(f"{API}/health")).is_success:break
   except Exception:pass
   await asyncio.sleep(2)
  await register(c);asyncio.create_task(heartbeat(c));source=replay() if MODE=='replay' else udp() if MODE=='udp' else tcp()
  async for d in source:
   try:
    p=(await call(c,'GET',f"/api/v1/plugins/{PLUGIN_ID}")).json()
    if not p.get('enabled',True):await asyncio.sleep(1);continue
    await publish(c,d)
   except Exception as e:metrics['parse_errors']+=1;print('publish',e)
if __name__=='__main__':asyncio.run(main())
