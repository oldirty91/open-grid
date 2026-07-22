import asyncio, json, math, os, time
from datetime import datetime, timezone
from typing import Any
import httpx
from pymavlink import mavutil

API=os.getenv("OPENGRID_API_URL","http://localhost:8000")
PLUGIN_ID=os.getenv("PLUGIN_ID","opengrid.mavlink.reference")
DEFAULT_CONFIG={
 "connection_type":os.getenv("MAVLINK_CONNECTION_TYPE","tcp"),
 "udp_listen_host":"0.0.0.0","udp_listen_port":14550,
 "udp_remote_host":"host.docker.internal","udp_remote_port":14551,
 "tcp_host":os.getenv("MAVLINK_TCP_HOST","ardupilot-sitl"),
 "tcp_port":int(os.getenv("MAVLINK_TCP_PORT","5760")),
 "serial_device":"/dev/ttyUSB0","serial_baud":115200,"source_system":250,
 "heartbeat_timeout_s":5,"command_timeout_s":12,"default_altitude_m":30,
 "takeoff_altitude_m":20,
}
metrics={"messages_received":0,"vehicles_active":0,"commands_sent":0,"command_errors":0,
 "last_message_time":None,"current_connection":None,"message_types":{},"stream_requests":0}
vehicles:dict[int,dict[str,Any]]={};masters:dict[int,Any]={}

async def api(c,m,p,**kw):r=await c.request(m,f"{API}{p}",**kw);r.raise_for_status();return r
async def register(c):
 await api(c,"POST","/api/v1/plugins/register",json={"plugin_id":PLUGIN_ID,"name":"MAVLink","version":"0.3.0",
 "plugin_type":"VEHICLE_ADAPTER","protocol":"MAVLink","capabilities":["entity.publish","task.consume","mission.upload"],
 "configuration_schema":{"type":"object"},"configuration":DEFAULT_CONFIG})
async def get_plugin(c):return (await api(c,"GET",f"/api/v1/plugins/{PLUGIN_ID}")).json()
async def cfg(c):
 x=dict(DEFAULT_CONFIG);x.update((await get_plugin(c)).get("configuration") or {});return x
async def log(c,l,m,d=None):
 try:await api(c,"POST",f"/api/v1/plugins/{PLUGIN_ID}/logs",json={"level":l,"message":m,"details":d or {}})
 except:pass
async def heartbeat(c):
 while True:
  try:
   p=await get_plugin(c);await api(c,"POST",f"/api/v1/plugins/{PLUGIN_ID}/heartbeat",json={
    "status":"RUNNING" if p.get("enabled",True) else "DISABLED","message":f"MAVLink: {metrics['current_connection']}","metrics":metrics})
  except Exception as e:print("[mavlink heartbeat]",e,flush=True)
  await asyncio.sleep(3)

def connstr(x):
 t=x.get("connection_type","tcp")
 if t=="tcp":return f"tcp:{x['tcp_host']}:{int(x['tcp_port'])}"
 if t=="udp_listen":return f"udpin:{x['udp_listen_host']}:{int(x['udp_listen_port'])}"
 if t=="udp_remote":return f"udpout:{x['udp_remote_host']}:{int(x['udp_remote_port'])}"
 return x["serial_device"]

def platform(v):
 copters={2,3,4,13,14,15,29}
 if v in copters:return("UAV","MULTIROTOR","AIR")
 if v==1:return("UAV","FIXED_WING","AIR")
 if v==10:return("UGV","ROVER","GROUND")
 if v==11:return("USV","SURFACE_VESSEL","MARITIME")
 if v==12:return("AUV","SUBSURFACE_VEHICLE","MARITIME")
 return("ROBOT","MAVLINK_VEHICLE","GROUND")

def operational_state(s):
 age=time.time()-s.get("heartbeat_epoch",0)
 if age>5:return"DISCONNECTED"
 if s.get("failsafe"):return"FAILSAFE"
 mode=str(s.get("flight_mode","")).upper();armed=bool(s.get("armed"));alt=float(s.get("alt_m") or 0)
 if mode=="RTL":return"RTL"
 if mode=="LAND":return"LANDING" if alt>.5 else"LANDED"
 if mode=="AUTO":return"MISSION"
 if not armed:return"READY_DISARMED" if int(s.get("gps_fix_type") or 0)>=3 else"NOT_READY"
 if alt<1:return"ARMED_GROUND"
 return"AIRBORNE"

def capabilities(s):
 modes=set(s.get("modes") or [])
 tasks=["Arm","Disarm","ReturnToLaunch"]
 if "GUIDED" in modes:tasks+=["Takeoff","Navigate","LaunchAndNavigate","Loiter"]
 if "LAND" in modes:tasks+=["Land"]
 if "AUTO" in modes:tasks+=["ExecuteMission","PauseMission","ResumeMission","StopMission"]
 return list(dict.fromkeys(tasks))

def request_streams(m,sysid,comp,s):
 if time.time()-s.get("stream_request",0)<10:return
 s["stream_request"]=time.time()
 m.mav.request_data_stream_send(sysid,comp or 1,mavutil.mavlink.MAV_DATA_STREAM_ALL,5,1)
 for mid,us in {33:200000,30:200000,1:1000000,24:1000000,147:1000000,245:500000,148:5000000}.items():
  m.mav.command_long_send(sysid,comp or 1,mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL,0,mid,us,0,0,0,0,0)
 metrics["stream_requests"]+=1

async def publish(c,sysid,s):
 if s.get("lat") is None:return
 pt,sp,domain=platform(s.get("vehicle_type",0));eid=f"mavlink-reference-{sysid}"
 caps=capabilities(s);fresh=max(0,time.time()-s.get("heartbeat_epoch",0))
 components={
  "aliases":{"name":f"MAV {sysid}","callsign":f"MAV-{sysid}"},
  "ontology":{"template":"ASSET","domain":domain,"platform_type":pt,"specific_type":sp},
  "location":{"latitude":s["lat"],"longitude":s["lon"],"altitude_m":s.get("alt_m"),"heading_degrees":s.get("heading",0),"speed_mps":s.get("speed_mps",0)},
  "attitude":{"roll_rad":s.get("roll"),"pitch_rad":s.get("pitch"),"yaw_rad":s.get("yaw")},
  "power":{"battery_percent":s.get("battery_remaining"),"voltage_v":s.get("voltage_v"),"current_a":s.get("current_a")},
  "health":{"connection":"ONLINE" if fresh<5 else"STALE","overall":"FAILSAFE" if s.get("failsafe") else"NOMINAL","heartbeat_age_s":fresh,"last_statustext":s.get("last_statustext")},
  "navigation":{"operational_state":operational_state(s),"armed":s.get("armed",False),"flight_mode":s.get("flight_mode"),"gps_fix_type":s.get("gps_fix_type"),"landed_state":s.get("landed_state"),"mission_current":s.get("mission_current"),"mission_count":s.get("mission_count")},
  "capabilities":{"available":[{"name":x} for x in caps],"mavlink_protocol_capabilities":s.get("protocol_capabilities",0)},
  "task_catalog":{"definitions":[{"type":f"opengrid.tasks.v1.{x}","version":"1.0.0"} for x in caps]},
  "mavlink":{"system_id":sysid,"component_id":s.get("component_id"),"vehicle_type":s.get("vehicle_type"),"autopilot":s.get("autopilot"),"flight_sw_version":s.get("flight_sw_version")},
  "provenance":{"source_system":PLUGIN_ID,"source_protocol":"MAVLink","source_id":str(sysid)}}
 await api(c,"PUT",f"/api/v1/entities/{eid}",json={"entity_id":eid,"components":components,"provenance":{"source_system":PLUGIN_ID}})
 s["entity_id"]=eid

async def status(c,t,st,p,msg,execution=None):
 await api(c,"POST",f"/api/v1/tasks/{t['task_id']}/status",json={"status":st,"progress":p,"message":msg,"execution":execution or {},"actor_id":PLUGIN_ID})
async def canceled(c,t):
 rows=(await api(c,"GET","/api/v1/tasks")).json();x=next((z for z in rows if z["task_id"]==t["task_id"]),None)
 return bool(x and x["status"]=="STATUS_CANCELED")
async def wait(pred,timeout,msg):
 end=time.time()+timeout
 while time.time()<end:
  if pred():return
  await asyncio.sleep(.2)
 raise RuntimeError(msg)
async def mode(m,s,name):
 mp=m.mode_mapping() or {}
 if name not in mp:raise RuntimeError(f"{name} mode unsupported")
 m.mav.set_mode_send(m.target_system,mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,mp[name])
 await wait(lambda:str(s.get("flight_mode","")).upper()==name,10,f"Did not enter {name}")
async def command(m,s,cid,params,timeout=12):
 s["acks"].pop(cid,None);m.mav.command_long_send(m.target_system,m.target_component,cid,0,*params);metrics["commands_sent"]+=1
 end=time.time()+timeout
 while time.time()<end:
  a=s["acks"].get(cid)
  if a:
   if a["result"] in {0,5}:return
   raise RuntimeError(f"Command rejected ({a['result']}): {s.get('last_statustext','')}")
  await asyncio.sleep(.1)
 raise RuntimeError(f"No COMMAND_ACK for {cid}")
async def arm(m,s):
 if s.get("armed"):return
 if int(s.get("gps_fix_type") or 0)<3:raise RuntimeError("GPS not ready")
 await mode(m,s,"GUIDED");await command(m,s,400,[1,0,0,0,0,0,0]);await wait(lambda:s.get("armed"),12,"Arm state not confirmed")
async def takeoff(m,s,alt):
 await command(m,s,22,[0,0,0,0,0,0,alt]);await wait(lambda:float(s.get("alt_m") or 0)>=alt-1,60,"Takeoff altitude not reached")
def target(m,lat,lon,alt):
 m.mav.set_position_target_global_int_send(int(time.time()*1000)&0xffffffff,m.target_system,m.target_component,6,0b0000111111111000,int(lat*1e7),int(lon*1e7),alt,0,0,0,0,0,0,0,0)
def dist(a,b,c,d):
 r=6371000;p1=math.radians(a);p2=math.radians(c);x=math.sin(math.radians(c-a)/2)**2+math.cos(p1)*math.cos(p2)*math.sin(math.radians(d-b)/2)**2
 return 2*r*math.atan2(math.sqrt(x),math.sqrt(1-x))

async def upload_mission(c,m,s,artifact_id,t):
 meta=(await api(c,"GET",f"/api/v1/artifacts/{artifact_id}")).json()
 if meta.get("artifact_type")!="MAVLINK_MISSION":raise RuntimeError("Artifact is not MAVLINK_MISSION")
 mission=(await api(c,"GET",f"/api/v1/artifacts/{artifact_id}/content")).json()
 items=mission.get("items") or []
 if not items:raise RuntimeError("Mission has no items")
 s["mission_requests"]=asyncio.Queue();s["mission_ack"]=None
 m.mav.mission_clear_all_send(m.target_system,m.target_component)
 await asyncio.sleep(.5);m.mav.mission_count_send(m.target_system,m.target_component,len(items),0)
 sent=set();end=time.time()+30
 while len(sent)<len(items) and time.time()<end:
  try:seq=await asyncio.wait_for(s["mission_requests"].get(),2)
  except asyncio.TimeoutError:
   m.mav.mission_count_send(m.target_system,m.target_component,len(items),0);continue
  if seq>=len(items):continue
  i=items[seq];cmd=int(i.get("command",16));frame=int(i.get("frame",3))
  m.mav.mission_item_int_send(m.target_system,m.target_component,seq,frame,cmd,0,1,
   float(i.get("param1",0)),float(i.get("param2",0)),float(i.get("param3",0)),float(i.get("param4",0)),
   int(float(i.get("latitude",0))*1e7),int(float(i.get("longitude",0))*1e7),float(i.get("altitude_m",0)),0)
  sent.add(seq);await status(c,t,"STATUS_IN_PROGRESS",.05+.35*len(sent)/len(items),f"Uploading mission item {len(sent)} of {len(items)}",{"phase":"UPLOADING","current_item":len(sent),"total_items":len(items)})
 await wait(lambda:s.get("mission_ack") in {0},10,"Mission upload not acknowledged")
 s["mission_count"]=len(items);return len(items)

async def execute(c,sysid,s,m,t,x):
 typ=t["specification"]["type"].split(".")[-1];par=t["specification"].get("parameters") or {};obj=t["specification"].get("objective") or {}
 try:
  if typ=="Arm":await status(c,t,"STATUS_IN_PROGRESS",.2,"Arming",{"phase":"ARMING"});await arm(m,s);await status(c,t,"STATUS_DONE_OK",1,"Armed",{"phase":"COMPLETE"});return
  if typ=="Disarm":
   if float(s.get("alt_m") or 0)>1:raise RuntimeError("Refusing disarm while airborne")
   await command(m,s,400,[0,0,0,0,0,0,0]);await status(c,t,"STATUS_DONE_OK",1,"Disarmed");return
  if typ=="Takeoff":
   alt=float(par.get("altitude_m",20));await mode(m,s,"GUIDED")
   if not s.get("armed"):await arm(m,s)
   await status(c,t,"STATUS_IN_PROGRESS",.2,f"Taking off to {alt} m",{"phase":"TAKING_OFF","target_altitude_m":alt})
   await takeoff(m,s,alt);await status(c,t,"STATUS_DONE_OK",1,"Takeoff complete");return
  if typ=="Land":await mode(m,s,"LAND");await status(c,t,"STATUS_IN_PROGRESS",.2,"Landing",{"phase":"LANDING"});await wait(lambda:float(s.get("alt_m") or 0)<.5,120,"Landing timeout");await status(c,t,"STATUS_DONE_OK",1,"Landed");return
  if typ=="ReturnToLaunch":await command(m,s,20,[0,0,0,0,0,0,0]);await status(c,t,"STATUS_DONE_OK",1,"RTL accepted");return
  if typ=="PauseMission":m.mav.command_long_send(m.target_system,m.target_component,193,0,0,0,0,0,0,0,0);await status(c,t,"STATUS_DONE_OK",1,"Mission paused");return
  if typ=="ResumeMission":m.mav.command_long_send(m.target_system,m.target_component,193,0,1,0,0,0,0,0,0);await status(c,t,"STATUS_DONE_OK",1,"Mission resumed");return
  if typ=="StopMission":await mode(m,s,"LOITER");await status(c,t,"STATUS_DONE_OK",1,"Mission stopped in LOITER");return
  if typ=="ExecuteMission":
   aid=obj.get("artifact_id");count=await upload_mission(c,m,s,aid,t)
   if par.get("auto_arm",True) and not s.get("armed"):await status(c,t,"STATUS_IN_PROGRESS",.45,"Arming for mission",{"phase":"ARMING"});await arm(m,s)
   await mode(m,s,"AUTO");await command(m,s,300,[0,0,0,0,0,0,0])
   start=time.time()
   while True:
    if await canceled(c,t):await mode(m,s,"LOITER");return
    cur=int(s.get("mission_current") or 0);progress=.5+.49*(cur/max(count,1))
    await status(c,t,"STATUS_IN_PROGRESS",min(.99,progress),f"Mission item {cur+1} of {count}",{"phase":"EXECUTING","current_item":cur+1,"total_items":count,"elapsed_seconds":int(time.time()-start)})
    if s.get("mission_reached") is not None and int(s["mission_reached"])>=count-1:break
    await asyncio.sleep(1)
   await status(c,t,"STATUS_DONE_OK",1,"Mission complete",{"phase":"COMPLETE","total_items":count});return
  if obj.get("type")!="POINT":raise RuntimeError("Point objective required")
  p=obj["position"];lat=float(p["latitude"]);lon=float(p["longitude"]);alt=float(par.get("takeoff_altitude_m") or par.get("altitude_m") or 30)
  if typ=="LaunchAndNavigate":
   if not s.get("armed"):await arm(m,s)
   if float(s.get("alt_m") or 0)<alt-1:await takeoff(m,s,alt)
  elif not s.get("armed") or float(s.get("alt_m") or 0)<1:raise RuntimeError("Vehicle must be armed and airborne")
  await mode(m,s,"GUIDED");initial=max(dist(s["lat"],s["lon"],lat,lon),1);arr=float(par.get("arrival_radius_m",par.get("radius_m",10)))
  while True:
   if await canceled(c,t):await mode(m,s,"LOITER");return
   target(m,lat,lon,alt);rem=dist(s["lat"],s["lon"],lat,lon);spd=float(s.get("speed_mps") or 0);eta=round(rem/spd) if spd>.2 else None
   await status(c,t,"STATUS_IN_PROGRESS",max(0,min(.99,1-rem/initial)),f"{rem:.0f} m remaining",{"phase":"EN_ROUTE","distance_remaining_m":round(rem,1),"ground_speed_mps":round(spd,1),"eta_seconds":eta,"target_altitude_m":alt})
   if rem<=arr:break
   await asyncio.sleep(1)
  if typ=="Loiter":await mode(m,s,"LOITER")
  await status(c,t,"STATUS_DONE_OK",1,"Objective reached",{"phase":"COMPLETE"})
 except Exception as e:
  metrics["command_errors"]+=1;await status(c,t,"STATUS_DONE_NOT_OK",t.get("progress",0),str(e),{"phase":"FAILED"});await log(c,"ERROR","Task failed",{"error":str(e)})

async def claims(c,x):
 active={}
 while True:
  for sid,s in list(vehicles.items()):
   if not s.get("entity_id") or (sid in active and not active[sid].done()):continue
   try:
    t=(await api(c,"POST",f"/api/v1/tasks/claim-next/{s['entity_id']}",json={"plugin_id":PLUGIN_ID})).json()
    if t:active[sid]=asyncio.create_task(execute(c,sid,s,masters[sid],t,x))
   except:pass
  await asyncio.sleep(1)

async def receive(c,x):
 conn=connstr(x);metrics["current_connection"]=conn;m=mavutil.mavlink_connection(conn,baud=int(x.get("serial_baud",115200)),source_system=250,autoreconnect=True)
 print("[mavlink]",conn,flush=True);asyncio.create_task(claims(c,x))
 while True:
  q=await asyncio.to_thread(m.recv_match,blocking=True,timeout=1)
  if not q:continue
  metrics["messages_received"]+=1;metrics["last_message_time"]=datetime.now(timezone.utc).isoformat();sid=q.get_srcSystem()
  if not sid:continue
  s=vehicles.setdefault(sid,{"acks":{},"last_publish":0});masters[sid]=m;s["component_id"]=q.get_srcComponent();m.target_system=sid;m.target_component=s["component_id"] or 1
  typ=q.get_type();metrics["message_types"][typ]=metrics["message_types"].get(typ,0)+1
  if typ=="HEARTBEAT":s.update(vehicle_type=q.type,autopilot=q.autopilot,armed=bool(q.base_mode&128),flight_mode=mavutil.mode_string_v10(q),heartbeat_epoch=time.time());s["modes"]=list((m.mode_mapping() or {}).keys());request_streams(m,sid,s["component_id"],s)
  elif typ=="GLOBAL_POSITION_INT":s.update(lat=q.lat/1e7,lon=q.lon/1e7,alt_m=q.relative_alt/1000,heading=0 if q.hdg==65535 else q.hdg/100,speed_mps=math.hypot(q.vx,q.vy)/100)
  elif typ=="ATTITUDE":s.update(roll=q.roll,pitch=q.pitch,yaw=q.yaw)
  elif typ=="SYS_STATUS":s.update(battery_remaining=q.battery_remaining,voltage_v=q.voltage_battery/1000,current_a=None if q.current_battery==-1 else q.current_battery/100)
  elif typ=="GPS_RAW_INT":s["gps_fix_type"]=q.fix_type
  elif typ=="EXTENDED_SYS_STATE":s["landed_state"]=q.landed_state
  elif typ=="AUTOPILOT_VERSION":s["protocol_capabilities"]=q.capabilities;s["flight_sw_version"]=q.flight_sw_version
  elif typ=="STATUSTEXT":s["last_statustext"]=q.text;s["failsafe"]="failsafe" in q.text.lower()
  elif typ=="COMMAND_ACK":s["acks"][q.command]={"result":q.result}
  elif typ in {"MISSION_REQUEST","MISSION_REQUEST_INT"}:
   if s.get("mission_requests"):await s["mission_requests"].put(q.seq)
  elif typ=="MISSION_ACK":s["mission_ack"]=q.type
  elif typ=="MISSION_CURRENT":s["mission_current"]=q.seq
  elif typ=="MISSION_ITEM_REACHED":s["mission_reached"]=q.seq
  if s.get("lat") is not None and time.time()-s["last_publish"]>=1:s["last_publish"]=time.time();metrics["vehicles_active"]=len(vehicles);await publish(c,sid,s)

async def main():
 async with httpx.AsyncClient(timeout=20) as c:
  while True:
   try:
    if (await c.get(f"{API}/health")).is_success:break
   except:pass
   await asyncio.sleep(2)
  while True:
   try:await register(c);break
   except Exception as e:print(e,flush=True);await asyncio.sleep(2)
  asyncio.create_task(heartbeat(c))
  while True:
   try:await receive(c,await cfg(c))
   except Exception as e:print("[mavlink reconnect]",e,flush=True);await asyncio.sleep(2)
if __name__=="__main__":asyncio.run(main())
