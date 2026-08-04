from __future__ import annotations
import asyncio, json, os, shutil, sqlite3
from pathlib import Path
from typing import Any
import httpx
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import Response

PLUGIN_ID=os.getenv("PLUGIN_ID","opengrid.map_engine")
API=os.getenv("OPENGRID_API_URL","http://api:8000").rstrip("/")
PUBLIC=os.getenv("PLUGIN_PUBLIC_BASE_URL","http://map-engine-plugin:8091").rstrip("/")
LIBRARY=Path(os.getenv("MAP_LIBRARY_DIR","/data/maps"))
LIBRARY.mkdir(parents=True,exist_ok=True)
app=FastAPI(title="OpenGrid Map Engine",version="0.13.1")
_catalog:dict[str,dict[str,Any]]={}

def safe_id(name:str)->str:
    return "".join(c.lower() if c.isalnum() else "-" for c in name).strip("-")[:120]

def read_metadata(path:Path)->dict[str,str]:
    with sqlite3.connect(path) as db:
        rows=db.execute("SELECT name,value FROM metadata").fetchall()
    return {str(k):str(v) for k,v in rows}

def inspect(path:Path)->dict[str,Any]:
    meta=read_metadata(path)
    fmt=meta.get("format","png").lower()
    if fmt not in {"png","jpg","jpeg","webp","pbf"}: fmt="png"
    layer_id=safe_id(path.stem)
    return {"layer_id":layer_id,"name":meta.get("name",path.stem),"filename":str(path.relative_to(LIBRARY)),"path":str(path),"format":fmt,
            "type":meta.get("type","baselayer"),"minzoom":int(meta.get("minzoom","0") or 0),"maxzoom":int(meta.get("maxzoom","22") or 22),
            "bounds":meta.get("bounds"),"description":meta.get("description","")}

async def api(method:str,path:str,**kwargs):
    async with httpx.AsyncClient(timeout=30) as client:
        r=await client.request(method,API+path,**kwargs);r.raise_for_status();return r.json() if r.content else None

async def register():
    await api("POST","/api/v1/plugins/register",json={"plugin_id":PLUGIN_ID,"name":"Map Engine","version":"0.13.1","plugin_type":"GIS_DATA_SOURCE","protocol":"MBTiles","capabilities":["gis.layer_provider","gis.offline","gis.mbtiles","gis.tile_server"],"configuration_schema":{"type":"object","properties":{}},"configuration":{}})
    layers=[]
    for item in _catalog.values():
        if item["format"]=="pbf":
            continue
        layers.append({"layer_id":item["layer_id"],"name":item["name"],"description":item["description"],"geometry_type":"raster_tile","service_url":f"{PUBLIC}/tiles/{item['layer_id']}/{{z}}/{{x}}/{{y}}","default_visible":False,"min_zoom":item["minzoom"],"max_zoom":item["maxzoom"]+1,"style":{"raster_opacity":1},"metadata":{"source":"MBTiles","offline":True,"format":item["format"],"filename":item["filename"],"bounds":item["bounds"],"display_mode":"BASEMAP" if item["type"]=="baselayer" else "OVERLAY"}})
    await api("PUT",f"/api/v1/plugins/{PLUGIN_ID}/gis-layers",json={"layers":layers})

async def rescan():
    global _catalog
    fresh={}
    for path in sorted(LIBRARY.rglob("*.mbtiles")):
        try:
            item=inspect(path);fresh[item["layer_id"]]=item
        except Exception as exc:
            print(f"[map-engine] skipped {path.name}: {exc}")
    changed=json.dumps(fresh,sort_keys=True,default=str)!=json.dumps(_catalog,sort_keys=True,default=str)
    _catalog=fresh
    try:
        (LIBRARY / ".opengrid-map-registry.json").write_text(json.dumps(list(_catalog.values()), indent=2, default=str))
    except Exception as exc:
        print(f"[map-engine] registry snapshot failed: {exc}")
    if changed:
        await register()

@app.on_event("startup")
async def startup():
    async def loop():
        while True:
            try: await rescan(); await api("POST",f"/api/v1/plugins/{PLUGIN_ID}/heartbeat",json={"status":"RUNNING","message":f"{len(_catalog)} offline maps ready","metrics":{"maps":len(_catalog)}})
            except Exception as exc: print(f"[map-engine] {exc}")
            await asyncio.sleep(5)
    asyncio.create_task(loop())

@app.get("/health")
async def health(): return {"status":"ok","maps":len(_catalog),"library":str(LIBRARY)}

@app.get("/maps")
async def maps(): return list(_catalog.values())

@app.post("/maps")
async def upload(file:UploadFile=File(...)):
    if not file.filename or not file.filename.lower().endswith(".mbtiles"): raise HTTPException(400,"Upload an .mbtiles file")
    dest=LIBRARY/Path(file.filename).name
    with dest.open("wb") as out: shutil.copyfileobj(file.file,out)
    try: inspect(dest)
    except Exception as exc:
        dest.unlink(missing_ok=True);raise HTTPException(400,f"Invalid MBTiles file: {exc}")
    await rescan();return inspect(dest)

@app.delete("/maps/{layer_id}")
async def remove(layer_id:str):
    item=_catalog.get(layer_id)
    if not item: raise HTTPException(404,"Map not found")
    Path(item["path"]).unlink(missing_ok=True);await rescan();return {"removed":layer_id}

@app.get("/tiles/{layer_id}/{z}/{x}/{y}")
async def tile(layer_id:str,z:int,x:int,y:int):
    item=_catalog.get(layer_id)
    if not item: raise HTTPException(404,"Map not found")
    tms_y=(1<<z)-1-y
    with sqlite3.connect(item["path"]) as db:
        row=db.execute("SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?",(z,x,tms_y)).fetchone()
    if not row: raise HTTPException(404,"Tile not found")
    media={"png":"image/png","jpg":"image/jpeg","jpeg":"image/jpeg","webp":"image/webp","pbf":"application/vnd.mapbox-vector-tile"}.get(item["format"],"application/octet-stream")
    return Response(row[0],media_type=media,headers={"Cache-Control":"public,max-age=31536000,immutable"})
