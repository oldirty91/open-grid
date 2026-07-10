import asyncio,math,os,httpx
API=os.getenv('API_URL','http://localhost:8000')
async def pub(c,eid,t,lat,lon,src,name,hdg=0,spd=0):
 b={'entity_id':eid,'is_live':True,'components':{'aliases':{'name':name},'ontology':{'template':t},'location':{'latitude':lat,'longitude':lon,'heading_degrees':hdg,'speed_mps':spd},'provenance':{'source_system':src},'mil_view':{'disposition':'FRIENDLY' if t=='ASSET' else 'UNKNOWN'},'health':{'connection':'ONLINE','overall':'NOMINAL'},'task_catalog':{'definitions':['navigate','investigate','follow','loiter']} if t=='ASSET' else {}}}
 r=await c.put(f'{API}/api/v1/entities/{eid}',json=b); r.raise_for_status()
async def main():
 async with httpx.AsyncClient(timeout=10) as c:
  while True:
   try:
    if (await c.get(f'{API}/health')).status_code==200: break
   except Exception: pass
   await asyncio.sleep(2)
  t=0
  while True:
   await pub(c,'asset-alpha','ASSET',41.490+.002*math.sin(t/25),-71.315+.003*math.cos(t/25),'sim-agent','ALPHA',(t*2)%360,3.2)
   await pub(c,'asset-bravo','ASSET',41.505+.002*math.sin(t/30),-71.295+.003*math.cos(t/30),'sim-agent','BRAVO',(180+t*1.5)%360,2.5)
   lat=41.498+.004*math.sin(t/18); lon=-71.305+.005*math.cos(t/18)
   await pub(c,'radar-track-77','TRACK',lat+.00020,lon-.00015,'radar-a','RADAR 77',65,4.1)
   await pub(c,'ais-track-123456789','TRACK',lat-.00015,lon+.00012,'ais-b','MMSI 123456789',64,4.0)
   t+=1; await asyncio.sleep(2)
asyncio.run(main())
