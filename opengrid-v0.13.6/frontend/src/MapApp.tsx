import { useEffect, useMemo, useRef, useState } from "react";
import maplibregl, { Map, MapMouseEvent } from "maplibre-gl";
import NavMenu from "./NavMenu";
const API=""; const WS=`${window.location.protocol==="https:"?"wss":"ws"}://${window.location.host}`;
type Entity={entity_id:string;revision:number;template:string;is_live:boolean;updated_at?:string;components:Record<string,any>;};
type Task={task_id:string;description:string;specification:Record<string,any>;assigned_agent_id:string;queue_position:number;status:string;progress:number;status_message?:string;execution?:Record<string,any>;};
type Def={type:string;display_name:string;objective_types:string[];parameter_schema:Record<string,any>;};
type Sample={latitude:number;longitude:number;timestamp:string;};
const TERMINAL=new Set(["STATUS_DONE_OK","STATUS_DONE_NOT_OK","STATUS_CANCELED","STATUS_TIMED_OUT"]);
const nameOf=(e?:Entity|null)=>e?.components?.aliases?.name||e?.entity_id||"Unknown"; const fused=(e:Entity)=>e.components?.ontology?.track_type==="FUSED"; const taskName=(t:Task)=>t.specification?.type?.split(".").pop()||"Task";

function LiveCamera({video}:{video:any}){
 if(String(video?.stream_type).toUpperCase()==="IMAGE"||String(video?.stream_type).toUpperCase()==="MJPEG")return <img className="liveCamera" src={video.snapshot_url||video.stream_url}/>;
 return <video className="liveCamera" controls autoPlay muted playsInline src={video.stream_url}/>;
}

function appendLiveSample(history:Record<string,Sample[]>,entity:Entity){
 const l=entity.components?.location;
 if(l?.latitude==null||l?.longitude==null)return history;
 const previous=history[entity.entity_id]||[];
 const last=previous[previous.length-1];
 if(last&&Math.abs(last.latitude-l.latitude)<1e-8&&Math.abs(last.longitude-l.longitude)<1e-8)return history;
 const next=[...previous,{latitude:Number(l.latitude),longitude:Number(l.longitude),timestamp:new Date().toISOString()}];
 return {...history,[entity.entity_id]:next.slice(-1000)};
}
function platformKind(e:Entity){const o=e.components?.ontology||{},x=String(o.specific_type||o.platform_type||e.components?.classification?.type||e.components?.ais?.ship_type||e.components?.adsb?.aircraft_type||"").toUpperCase();if(x.includes("HELICOPTER")||x.includes("ROTOR"))return"HELICOPTER";if(x.includes("CARGO")&&(x.includes("AIR")||o.domain==="AIR"))return"CARGO_PLANE";if(x.includes("PLANE")||x.includes("AIRCRAFT")||x.includes("FIXED_WING"))return"PLANE";if(x.includes("CAMERA"))return"CAMERA";if(x.includes("RADAR"))return"RADAR";if(x.includes("UAV")||x.includes("DRONE"))return"DRONE";if(x.includes("AUV")||x.includes("SUBMARINE"))return"AUV";if(x.includes("USV"))return"USV";if(x.includes("CARGO")||x.includes("TANKER")||x.includes("SHIP")||x.includes("VESSEL"))return"SHIP";if(x.includes("TRAIN")||x.includes("RAIL"))return"TRAIN";if(x.includes("TANK")||x.includes("ARMORED"))return"TANK";if(x.includes("UGV")||x.includes("GROUND_VEHICLE"))return"GROUND";if(e.template==="TRACK"&&e.components?.ais)return"SHIP";if(e.template==="TRACK"&&e.components?.adsb)return"PLANE";return e.template==="ASSET"?"ROBOT":"CONTACT";}

function mergeSamples(existing:Sample[], incoming:Sample[]) {
 const all=[...existing,...incoming]
  .filter(x=>Number.isFinite(Number(x.latitude))&&Number.isFinite(Number(x.longitude)))
  .map(x=>({...x,latitude:Number(x.latitude),longitude:Number(x.longitude)}))
  .sort((a,b)=>String(a.timestamp||"").localeCompare(String(b.timestamp||"")));
 const output:Sample[]=[];
 for(const sample of all){
  const last=output[output.length-1];
  if(last&&Math.abs(last.latitude-sample.latitude)<1e-8&&Math.abs(last.longitude-sample.longitude)<1e-8)continue;
  output.push(sample);
 }
 return output.slice(-2000);
}

function markerColor(category:string){
 if(category==="asset")return"#2db7ff";
 if(category==="fused")return"#ffd33d";
 return"#ff5964";
}

function encFeatureColor(properties:Record<string,any>){
 const raw=properties?.COLOUR??properties?.Colour??properties?.colour??properties?.COLOR??properties?.Color??properties?.color;
 const first=Array.isArray(raw)?raw[0]:String(raw??"").split(/[;, ]+/).find(Boolean);
 const code=Number(first);
 const colors:Record<number,string>={1:"#f7f7f2",2:"#15191d",3:"#e53935",4:"#20a957",5:"#2787d8",6:"#f2cf32",7:"#8d969d",8:"#8b5a2b",9:"#ffbf00",10:"#8b5fc7",11:"#f57c00",12:"#d73ea8",13:"#f48fb1"};
 return colors[code]||"#dff8ff";
}

function geoClass(e:Entity){return String(e.components?.provenance?.source_class||e.components?.ontology?.specific_type||"GEOENTITY").toUpperCase();}
function isSoundingClass(value:string){return String(value||"").toUpperCase().startsWith("SOUNDG");}
function soundingValue(e:Entity){
 const a=e.components?.attributes||{};
 const geometry=e.components?.geometry?.geojson||e.components?.geometry||{};
 const coordinates=geometry?.coordinates;
 const z=geometry?.type==="Point"&&Array.isArray(coordinates)&&coordinates.length>=3?coordinates[2]:undefined;
 const raw=a.VALSOU??a.DEPTH??a.DEPTH_M??a.DRVAL1??a.DRVAL2??a.value??a.VALUE??z;
 const value=Number(Array.isArray(raw)?raw[0]:raw);
 return Number.isFinite(value)?String(Math.round(value*10)/10):"";
}
function promoteOperationalLayers(map:Map){for(const id of ["breadcrumbs","queued-task-routes","selected-task-routes","entity-icons","task-waypoints"]){if(map.getLayer(id))map.moveLayer(id);}}

function makePlatformIcon(kind:string,color:string):ImageData {
 const size=64, canvas=document.createElement("canvas");
 canvas.width=size; canvas.height=size;
 const ctx=canvas.getContext("2d")!;
 ctx.clearRect(0,0,size,size);
 ctx.fillStyle=color;
 ctx.strokeStyle="#071018";
 ctx.lineWidth=3;
 ctx.lineJoin="round";
 ctx.lineCap="round";
 ctx.translate(32,32);

 const path=(points:[number,number][])=>{
  ctx.beginPath();
  points.forEach(([x,y],i)=>i?ctx.lineTo(x,y):ctx.moveTo(x,y));
  ctx.closePath(); ctx.fill();
 };

 if(kind==="PLANE"||kind==="CARGO_PLANE"){
  path([[0,-28],[6,-7],[28,2],[7,7],[4,28],[0,22],[-4,28],[-7,7],[-28,2],[-6,-7]]);
 } else if(kind==="HELICOPTER"){
  ctx.fillRect(-24,-2,35,15);
  path([[10,-2],[20,-2],[29,8],[11,8]]);
  ctx.fillRect(-1,-24,3,23); ctx.fillRect(-29,-25,58,3);
 } else if(kind==="DRONE"){
  for(const [x,y] of [[-18,-18],[18,-18],[-18,18],[18,18]]){
   ctx.beginPath();ctx.arc(x,y,8,0,Math.PI*2);ctx.fill();
  }
  ctx.fillRect(-9,-9,18,18);
  ctx.fillRect(-20,-2,40,4);ctx.fillRect(-2,-20,4,40);
 } else if(kind==="SHIP"||kind==="USV"){
  path([[0,-29],[19,22],[0,15],[-19,22]]);
  if(kind==="USV"){ctx.fillStyle="#071018";ctx.fillRect(-7,2,14,10);}
 } else if(kind==="AUV"){
  ctx.beginPath();ctx.ellipse(0,0,25,12,0,0,Math.PI*2);ctx.fill();
  path([[-22,0],[-31,-9],[-31,9]]);
  path([[22,0],[30,-7],[30,7]]);
 } else if(kind==="CAMERA"){
  ctx.fillRect(-22,-13,34,26);path([[12,-8],[29,-18],[29,18],[12,8]]);ctx.fillRect(-5,13,5,14);ctx.fillRect(-18,26,31,4);
 } else if(kind==="RADAR"){
  ctx.beginPath();ctx.arc(0,0,22,Math.PI,Math.PI*2);ctx.fill();ctx.fillRect(-3,0,6,27);ctx.fillRect(-16,25,32,4);
 } else if(kind==="TRAIN"){
  ctx.fillRect(-15,-27,30,48);
  ctx.fillStyle="#071018";ctx.fillRect(-10,-20,20,15);
  ctx.fillStyle=color;
  ctx.beginPath();ctx.arc(-10,23,6,0,Math.PI*2);ctx.fill();
  ctx.beginPath();ctx.arc(10,23,6,0,Math.PI*2);ctx.fill();
 } else if(kind==="TANK"){
  ctx.fillRect(-25,-7,48,22);ctx.fillRect(-12,-17,24,14);ctx.fillRect(8,-14,25,5);
 } else if(kind==="GROUND"){
  path([[-25,-8],[20,-8],[29,12],[-29,12]]);
  ctx.beginPath();ctx.arc(-15,15,7,0,Math.PI*2);ctx.fill();
  ctx.beginPath();ctx.arc(17,15,7,0,Math.PI*2);ctx.fill();
 } else if(kind==="ROBOT"){
  ctx.fillRect(-18,-17,36,35);
  ctx.fillStyle="#071018";
  ctx.beginPath();ctx.arc(-7,-5,3,0,Math.PI*2);ctx.fill();
  ctx.beginPath();ctx.arc(7,-5,3,0,Math.PI*2);ctx.fill();
 } else {
  ctx.beginPath();ctx.arc(0,0,13,0,Math.PI*2);ctx.fill();
  ctx.fillStyle="#071018";ctx.beginPath();ctx.arc(0,0,5,0,Math.PI*2);ctx.fill();
 }
 return ctx.getImageData(0,0,size,size);
}

function makeWaypointIcon():ImageData {
 const size=64,canvas=document.createElement("canvas");
 canvas.width=size;canvas.height=size;
 const ctx=canvas.getContext("2d")!;
 ctx.clearRect(0,0,size,size);
 ctx.strokeStyle="#5fe4ff";ctx.fillStyle="#071018";ctx.lineWidth=5;
 ctx.beginPath();ctx.arc(32,32,17,0,Math.PI*2);ctx.fill();ctx.stroke();
 ctx.fillStyle="#5fe4ff";ctx.beginPath();ctx.arc(32,32,6,0,Math.PI*2);ctx.fill();
 return ctx.getImageData(0,0,size,size);
}

function ensureMapImages(map:Map){
 const kinds=["SHIP","USV","AUV","PLANE","CARGO_PLANE","HELICOPTER","DRONE","CAMERA","RADAR","TRAIN","TANK","GROUND","ROBOT","CONTACT"];
 for(const category of ["asset","track","fused"]){
  for(const kind of kinds){
   const id=`${category}-${kind}`;
   if(!map.hasImage(id))map.addImage(id,makePlatformIcon(kind,markerColor(category)),{pixelRatio:2});
  }
 }
 if(!map.hasImage("task-waypoint"))map.addImage("task-waypoint",makeWaypointIcon(),{pixelRatio:2});
}
export default function App(){
 const mapEl=useRef<HTMLDivElement>(null), mapRef=useRef<Map|null>(null);
 const gisFeatureCacheRef=useRef<Record<string,globalThis.Map<string,any>>>({});
 const gisRefreshSequenceRef=useRef(0);
 const [entities,setEntities]=useState<Entity[]>([]),[tasks,setTasks]=useState<Task[]>([]),[defs,setDefs]=useState<Def[]>([]),[selectedEntity,setSelectedEntity]=useState<Entity|null>(null),[selectedTaskId,setSelectedTaskId]=useState<string|null>(null),[assetId,setAssetId]=useState("asset-alpha"),[filter,setFilter]=useState(""),[connected,setConnected]=useState(false),[point,setPoint]=useState<{lat:number;lon:number}|null>(null),[composer,setComposer]=useState(false),[review,setReview]=useState(false),[taskType,setTaskType]=useState(""),[speed,setSpeed]=useState(3),[radius,setRadius]=useState(20),[altitude,setAltitude]=useState(20),[cancel,setCancel]=useState<Task|null>(null),[priority,setPriority]=useState(50),[timeoutSeconds,setTimeoutSeconds]=useState(300),[maximumAttempts,setMaximumAttempts]=useState(1),[history,setHistory]=useState<Record<string,Sample[]>>({}),[mapReady,setMapReady]=useState(0),[overlays,setOverlays]=useState<any[]>([]),[overlaySettingsVersion,setOverlaySettingsVersion]=useState(0),[gisLayers,setGisLayers]=useState<any[]>([]),[selectedGisFeature,setSelectedGisFeature]=useState<any|null>(null),[encLoading,setEncLoading]=useState(false),[encStatus,setEncStatus]=useState(""),[leftDrawer,setLeftDrawer]=useState<"tracks"|"assets"|"geoentities"|null>("assets"),[rightOpen,setRightOpen]=useState(true),[gisCacheVersion,setGisCacheVersion]=useState(0),[hiddenGeoIds,setHiddenGeoIds]=useState<Set<string>>(()=>new Set()),[hiddenGeoClasses,setHiddenGeoClasses]=useState<Set<string>>(()=>new Set());
 const selectedTask=tasks.find(t=>t.task_id===selectedTaskId)||null, assets=useMemo(()=>entities.filter(e=>e.template==="ASSET"||e.template==="SENSOR"),[entities]);
 useEffect(()=>{Promise.all([fetch(`${API}/api/v1/entities?limit=5000`),fetch(`${API}/api/v1/tasks`),fetch(`${API}/api/v1/task-definitions`),fetch(`${API}/api/v1/artifacts`),fetch(`${API}/api/v1/gis/layers`),fetch(`${API}/api/v1/tracks/history?hours=24&limit_per_entity=20000`)]).then(async([e,t,d,a,g,h])=>{if(e.ok){const items:Entity[]=await e.json();setEntities(items);setHistory(p=>items.reduce((acc,item)=>appendLiveSample(acc,item),p));}if(h.ok){const payload=await h.json();const tracks=payload?.tracks||{};setHistory(p=>Object.entries(tracks).reduce((acc,[id,samples])=>({...acc,[id]:mergeSamples(samples as Sample[],acc[id]||[])}),p));}if(t.ok)setTasks(await t.json());if(d.ok)setDefs(await d.json());if(a.ok)setOverlays((await a.json()).filter((x:any)=>x.artifact_type==="MAP_OVERLAY"));if(g.ok)setGisLayers(await g.json());});},[]);
 useEffect(()=>{const refresh=()=>fetch(`${API}/api/v1/gis/layers`).then(r=>r.ok?r.json():[]).then(setGisLayers).catch(()=>{});const timer=window.setInterval(refresh,10000);return()=>window.clearInterval(timer)},[]);
 useEffect(()=>{if(!mapEl.current||mapRef.current)return;const map=new maplibregl.Map({container:mapEl.current,style:"https://tiles.openfreemap.org/styles/dark",center:[-71.305,41.498],zoom:12});map.addControl(new maplibregl.NavigationControl(),"bottom-right");map.on("load",()=>{
 const layers=map.getStyle().layers||[];
 for(const layer of layers){
  const id=layer.id.toLowerCase();
  if(
   id.includes("minor")||id.includes("service")||id.includes("path")||
   id.includes("pedestrian")||id.includes("road-label")||
   id.includes("poi")||id.includes("building")||id.includes("housenumber")
  ){
   try{map.setLayoutProperty(layer.id,"visibility","none")}catch{}
  }
 }
 setMapReady(x=>x+1);
});map.on("contextmenu",(ev:MapMouseEvent)=>{setPoint({lat:ev.lngLat.lat,lon:ev.lngLat.lng});setSelectedTaskId(null);setTaskType("opengrid.tasks.v1.Navigate");setRadius(20);setReview(false);setComposer(true);});mapRef.current=map;},[]);
 useEffect(()=>{
  const refresh=()=>setOverlaySettingsVersion(v=>v+1);
  window.addEventListener("storage",refresh);
  window.addEventListener("focus",refresh);
  return()=>{window.removeEventListener("storage",refresh);window.removeEventListener("focus",refresh)};
 },[]);
 useEffect(()=>{
  const map=mapRef.current;if(!map||!mapReady)return;
  let settings:Record<string,{enabled?:boolean;opacity?:number}>={};
  try{settings=JSON.parse(localStorage.getItem("opengrid.mapOverlays")||"{}")}catch{}
  for(const a of overlays){
   const id=`overlay-${a.artifact_id}`,meta=a.metadata||{};
   let url=meta.tile_url as string|undefined;
   if(meta.overlay_type==="WMS"&&meta.wms_url){
    const q=new URLSearchParams({service:"WMS",request:"GetMap",version:"1.1.1",layers:String(meta.layers||"0"),styles:"",format:String(meta.format||"image/png"),transparent:String(meta.transparent??true),srs:"EPSG:3857",width:"256",height:"256",bbox:"{bbox-epsg-3857}"});
    url=`${meta.wms_url}?${q.toString()}`.replace(encodeURIComponent("{bbox-epsg-3857}"),"{bbox-epsg-3857}");
   }
   if(!url)continue;
   const setting=settings[a.artifact_id]||{};
   const enabled=setting.enabled??Boolean(meta.default_enabled);
   const opacity=enabled?(meta.display_mode==="BASEMAP"?1:Number(setting.opacity??meta.default_opacity??0.72)):0;
   if(!map.getSource(id))map.addSource(id,{type:"raster",tiles:[url],tileSize:256});
   if(!map.getLayer(id))map.addLayer({id,type:"raster",source:id,paint:{"raster-opacity":opacity,"raster-fade-duration":0}});
   else map.setPaintProperty(id,"raster-opacity",opacity);
  }
 },[overlays,overlaySettingsVersion,mapReady]);
 useEffect(()=>{
  const map=mapRef.current;if(!map||!mapReady)return;
  let canceled=false;
  let debounceTimer:number|undefined;
  const activeSourceIds=new Set(gisLayers.map(layer=>{
   const key=`${layer.plugin_id}/${layer.layer_id}`;
   return `gis-source-${key.replace(/[^a-zA-Z0-9_-]/g,"-")}`;
  }));
  for(const styleLayer of [...(map.getStyle().layers||[])]){
   if(!styleLayer.id.startsWith("gis-"))continue;
   const source=String((styleLayer as any).source||"");
   if(source&&source.startsWith("gis-source-")&&!activeSourceIds.has(source)){try{map.removeLayer(styleLayer.id)}catch{}}
  }
  for(const sourceId of Object.keys(gisFeatureCacheRef.current)){
   if(activeSourceIds.has(sourceId))continue;
   delete gisFeatureCacheRef.current[sourceId];
   try{if(map.getSource(sourceId))map.removeSource(sourceId)}catch{}
  }
  if(!gisLayers.length){setEncLoading(false);setEncStatus("");return}
  let gisSettings:Record<string,{enabled?:boolean;opacity?:number}>={};
  try{gisSettings=JSON.parse(localStorage.getItem("opengrid.gisLayers")||"{}")}catch{}
  for(const layer of gisLayers.filter(x=>String(x.geometry_type).toLowerCase()==="raster_tile")){
   const key=`${layer.plugin_id}/${layer.layer_id}`;
   const safeKey=key.replace(/[^a-zA-Z0-9_-]/g,"-");
   const sourceId=`gis-source-${safeKey}`,layerId=`gis-${safeKey}-raster`;
   const tileUrl=`${API}/api/v1/gis/layers/${encodeURIComponent(layer.plugin_id)}/${encodeURIComponent(layer.layer_id)}/tiles/{z}/{x}/{y}`;
   const setting=gisSettings[key]||{};
   const enabled=setting.enabled??Boolean(layer.default_visible);
   if(!map.getSource(sourceId))map.addSource(sourceId,{type:"raster",tiles:[tileUrl],tileSize:256,minzoom:Number(layer.min_zoom||0),maxzoom:Number(layer.max_zoom||24)});
   if(!map.getLayer(layerId))map.addLayer({id:layerId,type:"raster",source:sourceId,minzoom:Number(layer.min_zoom||0),maxzoom:Number(layer.max_zoom||24),paint:{"raster-opacity":enabled?Number(setting.opacity??1):0,"raster-fade-duration":0}});
   else map.setPaintProperty(layerId,"raster-opacity",enabled?Number(setting.opacity??1):0);
  }
  const refresh=async()=>{
   const sequence=++gisRefreshSequenceRef.current;
   const bounds=map.getBounds();
   const west=bounds.getWest(),east=bounds.getEast(),south=bounds.getSouth(),north=bounds.getNorth();
   const padX=(east-west)*0.2,padY=(north-south)*0.2;
   const bbox=[west-padX,south-padY,east+padX,north+padY].join(",");
   const zoom=map.getZoom();
   const visibleAtZoom=gisLayers.filter(layer=>String(layer.geometry_type).toLowerCase()!=="raster_tile"&&zoom>=Number(layer.min_zoom??0)&&zoom<Number(layer.max_zoom??24));
   setEncLoading(true);setEncStatus(`Loading ${visibleAtZoom.length} ENC layers`);
   let loaded=0;
   await Promise.all(visibleAtZoom.map(async layer=>{
    const key=`${layer.plugin_id}/${layer.layer_id}`;
    const safeKey=key.replace(/[^a-zA-Z0-9_-]/g,"-");
    const sourceId=`gis-source-${safeKey}`;
    const baseId=`gis-${safeKey}`;
    try{
     const response=await fetch(`${API}/api/v1/gis/layers/${encodeURIComponent(layer.plugin_id)}/${encodeURIComponent(layer.layer_id)}/geojson?bbox=${encodeURIComponent(bbox)}`);
     if(!response.ok)return;
     const data=await response.json();if(canceled)return;
     const layerName=String(layer.name||"");
     const icon=layerName.match(/buoy/i)?"◆":layerName.match(/beacon/i)?"▲":layerName.match(/light/i)?"✦":layerName.match(/wreck/i)?"×":layerName.match(/obstruction|rock/i)?"!":layerName.match(/sounding/i)?"·":"•";
     const cache=gisFeatureCacheRef.current[sourceId]||(gisFeatureCacheRef.current[sourceId]=new globalThis.Map<string,any>());
     for(const feature of data.features||[]){
      const props=feature.properties||{};
      const id=String(feature.id??props.OBJECTID??props.FID??props.RCID??JSON.stringify(feature.geometry));
      cache.set(id,{...feature,id,properties:{...props,__og_plugin_id:layer.plugin_id,__og_layer_id:layer.layer_id,__og_layer_name:layer.name,__og_class_name:layer.metadata?.class_name||layer.name,__og_dataset:layer.metadata?.dataset||"custom",__og_icon:icon,__og_color:encFeatureColor(props)}});
     }
     if(cache.size>25000){const trim=cache.size-25000;let i=0;for(const cacheKey of cache.keys()){cache.delete(cacheKey);if(++i>=trim)break}}
     const merged={type:"FeatureCollection",features:[...cache.values()]};
     const existing=map.getSource(sourceId) as maplibregl.GeoJSONSource|undefined;
     if(existing)existing.setData(merged as any);else map.addSource(sourceId,{type:"geojson",data:merged as any});
     const style=layer.style||{};
     const geometry=String(layer.geometry_type||"").toLowerCase();
     const show=(id:string)=>{if(map.getLayer(id))map.setLayoutProperty(id,"visibility","visible")};
     if(geometry.includes("polygon")||geometry==="mixed"){
      const id=baseId+"-fill";
      if(!map.getLayer(id))map.addLayer({id,type:"fill",source:sourceId,minzoom:Number(layer.min_zoom||0),maxzoom:Number(layer.max_zoom||24),paint:{"fill-color":style.fillColor||"#41829a","fill-opacity":Number(style.fillOpacity??0.18),"fill-outline-color":style.lineColor||"#6db7ce"}});else show(id);
     }
     if(geometry.includes("line")||geometry==="mixed"||geometry.includes("polygon")){
      const id=baseId+"-line";
      if(!map.getLayer(id))map.addLayer({id,type:"line",source:sourceId,minzoom:Number(layer.min_zoom||0),maxzoom:Number(layer.max_zoom||24),paint:{"line-color":style.lineColor||"#6db7ce","line-width":Number(style.lineWidth??1.2),"line-opacity":0.9}});else show(id);
     }
     if(geometry.includes("point")||geometry==="mixed"){
      const circleId=baseId+"-circle";
      if(!map.getLayer(circleId))map.addLayer({id:circleId,type:"circle",source:sourceId,minzoom:Number(layer.min_zoom||0),maxzoom:Number(layer.max_zoom||24),paint:{"circle-color":["coalesce",["get","__og_color"],style.circleColor||"#dff8ff"],"circle-radius":Number(style.circleRadius??5),"circle-stroke-color":"#071018","circle-stroke-width":1}});else show(circleId);
      const symbolId=baseId+"-symbol";
      if(!map.getLayer(symbolId))map.addLayer({id:symbolId,type:"symbol",source:sourceId,minzoom:Number(layer.min_zoom||0),maxzoom:Number(layer.max_zoom||24),layout:{"text-field":["get","__og_icon"],"text-size":15,"text-allow-overlap":true,"text-ignore-placement":true},paint:{"text-color":["coalesce",["get","__og_color"],"#dff8ff"],"text-halo-color":"#071018","text-halo-width":1.5}});else show(symbolId);
     }
     loaded++;
    }catch{}
   }));
   if(!canceled&&sequence===gisRefreshSequenceRef.current){promoteOperationalLayers(map);setEncLoading(false);setEncStatus(`${loaded}/${visibleAtZoom.length} ENC layers ready`);setGisCacheVersion(v=>v+1)}
  };
  const schedule=()=>{if(debounceTimer)window.clearTimeout(debounceTimer);debounceTimer=window.setTimeout(refresh,180)};
  refresh();map.on("moveend",schedule);map.on("zoomend",schedule);
  return()=>{canceled=true;if(debounceTimer)window.clearTimeout(debounceTimer);map.off("moveend",schedule);map.off("zoomend",schedule)};
 },[gisLayers,mapReady]);

 useEffect(()=>{let s:WebSocket|null=null,r:number|undefined;const go=()=>{s=new WebSocket(`${WS}/ws/`);s.onopen=()=>{setConnected(true);s?.send("subscribe")};s.onmessage=ev=>{const m=JSON.parse(ev.data),d=m.data;if(m.type==="entity.deleted"&&d?.entity_id){setEntities(p=>p.filter(x=>x.entity_id!==d.entity_id));setSelectedEntity(p=>p?.entity_id===d.entity_id?null:p);}else if(m.type.startsWith("entity.")&&d){const e:Entity=d.entity||d;if(e.entity_id){setEntities(p=>p.some(x=>x.entity_id===e.entity_id)?p.map(x=>x.entity_id===e.entity_id?e:x):[e,...p]);setHistory(p=>appendLiveSample(p,e));setSelectedEntity(p=>p?.entity_id===e.entity_id?e:p);}}if(m.type.startsWith("task.")&&d?.task_id)setTasks(p=>p.some(x=>x.task_id===d.task_id)?p.map(x=>x.task_id===d.task_id?d:x):[...p,d]);};s.onclose=()=>{setConnected(false);r=window.setTimeout(go,1500)};s.onerror=()=>s?.close();};go();return()=>{if(r)clearTimeout(r);s?.close();};},[]);
 const valid=useMemo(()=>{const a=assets.find(x=>x.entity_id===assetId),adv=new Set((a?.components?.task_catalog?.definitions||[]).map((x:any)=>typeof x==="string"?x:x.type));return defs.filter(d=>adv.has(d.type)&&(d.objective_types.includes("NONE")||(point&&d.objective_types.includes("POINT"))||(selectedEntity?.template==="TRACK"&&d.objective_types.includes("ENTITY"))));},[assets,assetId,defs,point,selectedEntity]);
 useEffect(()=>{if(composer&&valid.length&&!valid.some(d=>d.type===taskType))setTaskType(valid[0].type);},[composer,valid]);
 useEffect(()=>{
 if(!selectedEntity)return;
 fetch(`${API}/api/v1/entities/${encodeURIComponent(selectedEntity.entity_id)}/location-history?limit=20000&hours=24`)
  .then(r=>r.ok?r.json():[])
  .then((samples:Sample[])=>setHistory(p=>({...p,[selectedEntity.entity_id]:mergeSamples(samples,p[selectedEntity.entity_id]||[])})))
  .catch(()=>{});
},[selectedEntity?.entity_id]);
 async function send(){const d=defs.find(x=>x.type===taskType);if(!d)return;const objective=(selectedEntity?.template==="TRACK"&&d.objective_types.includes("ENTITY"))?{type:"ENTITY",entity_id:selectedEntity.entity_id}:point&&d.objective_types.includes("POINT")?{type:"POINT",position:{latitude:point.lat,longitude:point.lon}}:null;if(!objective&&!d.objective_types.includes("NONE"))return alert("Select a compatible objective");let params:Record<string,any>={};if(taskType.endsWith("Investigate"))params={speed_mps:speed,standoff_m:radius};else if(taskType.endsWith("Takeoff"))params={altitude_m:altitude};else if(taskType.endsWith("LaunchAndNavigate"))params={speed_mps:speed,arrival_radius_m:radius,takeoff_altitude_m:altitude};else if(taskType.endsWith("Navigate")||taskType.endsWith("Loiter"))params={speed_mps:speed,arrival_radius_m:radius,radius_m:radius,altitude_m:altitude};const res=await fetch(`${API}/api/v1/tasks`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({description:`${d.display_name} using ${assetId}`,specification:{type:taskType,objective,parameters:params},assigned_agent_id:assetId,created_by:"operator-ui",priority,timeout_seconds:timeoutSeconds||null,maximum_attempts:maximumAttempts,depends_on:[]})});if(!res.ok)return alert(await res.text());const t=await res.json();setTasks(p=>p.some(x=>x.task_id===t.task_id)?p:[...p,t]);setSelectedTaskId(t.task_id);setComposer(false);setPoint(null);}
 async function cancelTask(t:Task){const r=await fetch(`${API}/api/v1/tasks/${t.task_id}/cancel`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({reason:"Canceled by operator",actor_id:"operator-ui"})});if(!r.ok)return alert(await r.text());const u=await r.json();setTasks(p=>p.map(x=>x.task_id===u.task_id?u:x));setCancel(null);}
 function composeTrack(e:Entity){setSelectedGisFeature(null);setSelectedEntity(e);setSelectedTaskId(null);setPoint(null);setTaskType("opengrid.tasks.v1.Investigate");setRadius(50);setReview(false);setComposer(true);}
 const visible=useMemo(()=>{const q=filter.toLowerCase();return entities.filter(e=>!q||e.entity_id.toLowerCase().includes(q)||nameOf(e).toLowerCase().includes(q)||e.template.toLowerCase().includes(q));},[entities,filter]);
 const tracks=useMemo(()=>visible.filter(e=>e.template==="TRACK"),[visible]);
 const operationalAssets=useMemo(()=>visible.filter(e=>e.template==="ASSET"||e.template==="SENSOR"),[visible]);
 const coreGeoEntities=useMemo(()=>visible.filter(e=>e.template==="GEOENTITY"),[visible]);
 const pluginGeoEntities:any[]=[];
 useEffect(()=>{try{const saved=localStorage.getItem("opengrid.leftDrawer");if(saved==="contacts")setLeftDrawer("tracks");else if(saved==="tracks"||saved==="assets"||saved==="geoentities"||saved==="closed")setLeftDrawer(saved==="closed"?null:saved as any)}catch{}},[]);
 useEffect(()=>{try{setHiddenGeoIds(new Set(JSON.parse(localStorage.getItem("opengrid.hiddenGeoIds")||"[]")));setHiddenGeoClasses(new Set(JSON.parse(localStorage.getItem("opengrid.hiddenGeoClasses")||"[]")))}catch{}},[]);
 useEffect(()=>{localStorage.setItem("opengrid.hiddenGeoIds",JSON.stringify([...hiddenGeoIds]));localStorage.setItem("opengrid.hiddenGeoClasses",JSON.stringify([...hiddenGeoClasses]))},[hiddenGeoIds,hiddenGeoClasses]);
 useEffect(()=>{localStorage.setItem("opengrid.leftDrawer",leftDrawer||"closed");window.setTimeout(()=>mapRef.current?.resize(),220)},[leftDrawer]);
 useEffect(()=>{window.setTimeout(()=>mapRef.current?.resize(),220)},[rightOpen]);

useEffect(()=>{
 const map=mapRef.current;
 if(!map||!map.isStyleLoaded())return;
 ensureMapImages(map);

 const entityFeatures=entities.filter(e=>e.template!=="GEOENTITY").flatMap(e=>{
  const l=e.components?.location;
  if(l?.latitude==null||l?.longitude==null)return[];
  const category=e.template==="ASSET"?"asset":fused(e)?"fused":"track";
  return [{
   type:"Feature",
   properties:{
    entity_id:e.entity_id,
    icon:`${category}-${platformKind(e)}`,
    heading:Number(l.heading_degrees||0),
    name:nameOf(e)
   },
   geometry:{type:"Point",coordinates:[Number(l.longitude),Number(l.latitude)]}
  }];
 });

 const coreGeoFeatures=entities.filter(e=>e.template==="GEOENTITY"&&!hiddenGeoIds.has(e.entity_id)&&!hiddenGeoClasses.has(geoClass(e))).flatMap(e=>{
  const raw=e.components?.geometry?.geojson||e.components?.geometry||e.components?.geojson;
  if(!raw?.type)return[];
  const s=e.components?.style||{},cls=geoClass(e),attributes=e.components?.attributes||{};
  const importedColor=e.components?.provenance?.source_system==="opengrid.noaa_enc"?encFeatureColor(attributes):undefined;
  const pointColor=(cls.includes("BOY")||cls.includes("BCN")||cls.includes("LIGHT"))?importedColor:(s.circleColor||importedColor);
  return[{type:"Feature",properties:{
   entity_id:e.entity_id,name:nameOf(e),class_name:cls,is_sounding:isSoundingClass(cls),
   sounding_value:soundingValue(e),fillColor:s.fillColor,lineColor:s.lineColor,
   circleColor:pointColor||s.circleColor,fillOpacity:s.fillOpacity,lineWidth:s.lineWidth,circleRadius:s.circleRadius
  },geometry:raw}]
 });

 const fovFeatures=entities.flatMap(e=>{
  if(platformKind(e)!=="CAMERA")return[];
  const l=e.components?.location,s=e.components?.sensor||{};
  if(l?.latitude==null||l?.longitude==null)return[];
  const range=Number(s.range_m||0),fov=Number(s.horizontal_fov_deg||0),dir=Number(s.direction_deg??l.heading_degrees??0);
  if(range<=0||fov<=0)return[];
  const dest=(bearing:number)=>{const R=6378137,lat1=Number(l.latitude)*Math.PI/180,lon1=Number(l.longitude)*Math.PI/180,d=range/R,b=bearing*Math.PI/180;const lat2=Math.asin(Math.sin(lat1)*Math.cos(d)+Math.cos(lat1)*Math.sin(d)*Math.cos(b));const lon2=lon1+Math.atan2(Math.sin(b)*Math.sin(d)*Math.cos(lat1),Math.cos(d)-Math.sin(lat1)*Math.sin(lat2));return[lon2*180/Math.PI,lat2*180/Math.PI]};
  return[{type:"Feature",properties:{entity_id:e.entity_id},geometry:{type:"Polygon",coordinates:[[[Number(l.longitude),Number(l.latitude)],dest(dir-fov/2),dest(dir),dest(dir+fov/2),[Number(l.longitude),Number(l.latitude)]]]}}];
 });

 const activeTasks=tasks.filter(t=>!TERMINAL.has(t.status));
 const queuedRoutes:any[]=[],selectedRoutes:any[]=[],waypoints:any[]=[];
 for(const t of activeTasks){
  const a=entities.find(e=>e.entity_id===t.assigned_agent_id)?.components?.location;
  const o=t.specification?.objective;
  let target:[number,number]|null=null;
  if(o?.type==="POINT")target=[Number(o.position.longitude),Number(o.position.latitude)];
  if(o?.type==="ENTITY"){
   const l=entities.find(e=>e.entity_id===o.entity_id)?.components?.location;
   if(l)target=[Number(l.longitude),Number(l.latitude)];
  }
  if(!a||!target)continue;
  const route={
   type:"Feature",
   properties:{task_id:t.task_id},
   geometry:{type:"LineString",coordinates:[[Number(a.longitude),Number(a.latitude)],target]}
  };
  (t.task_id===selectedTaskId?selectedRoutes:queuedRoutes).push(route);
  if(t.task_id===selectedTaskId){
   waypoints.push({
    type:"Feature",
    properties:{task_id:t.task_id,icon:"task-waypoint"},
    geometry:{type:"Point",coordinates:target}
   });
  }
 }

 const hs=selectedEntity?history[selectedEntity.entity_id]||[]:[];
 const trail=hs.length>1?[{
  type:"Feature",
  properties:{entity_id:selectedEntity?.entity_id},
  geometry:{type:"LineString",coordinates:hs.map(x=>[Number(x.longitude),Number(x.latitude)])}
 }]:[];

 const setSource=(id:string,data:any)=>{
  const source=map.getSource(id) as maplibregl.GeoJSONSource|undefined;
  if(source)source.setData(data);
  else map.addSource(id,{type:"geojson",data});
 };

 setSource("camera-fov",{type:"FeatureCollection",features:fovFeatures});
 setSource("core-geoentities",{type:"FeatureCollection",features:coreGeoFeatures});
 setSource("entity-features",{type:"FeatureCollection",features:entityFeatures});
 setSource("queued-task-routes",{type:"FeatureCollection",features:queuedRoutes});
 setSource("selected-task-routes",{type:"FeatureCollection",features:selectedRoutes});
 setSource("task-waypoints",{type:"FeatureCollection",features:waypoints});
 setSource("breadcrumbs",{type:"FeatureCollection",features:trail});

 if(!map.getLayer("camera-fov"))map.addLayer({
  id:"camera-fov",type:"fill",source:"camera-fov",
  paint:{"fill-color":"#2db7ff","fill-opacity":0.16,"fill-outline-color":"#2db7ff"}
 });
 if(!map.getLayer("core-geoentities-fill"))map.addLayer({id:"core-geoentities-fill",type:"fill",source:"core-geoentities",filter:["==",["geometry-type"],"Polygon"],paint:{"fill-color":["coalesce",["get","fillColor"],"#8ecae6"],"fill-opacity":["coalesce",["get","fillOpacity"],0.18],"fill-outline-color":["coalesce",["get","lineColor"],"#8ecae6"]}});
 if(!map.getLayer("core-geoentities-line"))map.addLayer({id:"core-geoentities-line",type:"line",source:"core-geoentities",filter:["in",["geometry-type"],["literal",["LineString","Polygon"]]],paint:{"line-color":["coalesce",["get","lineColor"],"#8ecae6"],"line-width":["coalesce",["get","lineWidth"],2]}});
 if(!map.getLayer("core-geoentities-point"))map.addLayer({id:"core-geoentities-point",type:"circle",source:"core-geoentities",filter:["all",["==",["geometry-type"],"Point"],["!=",["get","is_sounding"],true]],paint:{"circle-color":["coalesce",["get","circleColor"],"#8ecae6"],"circle-radius":["coalesce",["get","circleRadius"],6],"circle-stroke-color":"#071018","circle-stroke-width":1}});
 if(!map.getLayer("core-geoentities-soundings"))map.addLayer({id:"core-geoentities-soundings",type:"symbol",source:"core-geoentities",minzoom:11,filter:["all",["==",["geometry-type"],"Point"],["==",["get","is_sounding"],true],["!=",["get","sounding_value"],""]],layout:{"text-field":["get","sounding_value"],"text-size":8,"text-allow-overlap":true,"text-ignore-placement":true},paint:{"text-color":"#9bdcf5","text-halo-color":"#071018","text-halo-width":1}});
 if(!map.getLayer("breadcrumbs"))map.addLayer({
  id:"breadcrumbs",type:"line",source:"breadcrumbs",
  paint:{"line-width":4,"line-color":"#00d8ff","line-opacity":0.95}
 });
 if(!map.getLayer("queued-task-routes"))map.addLayer({
  id:"queued-task-routes",type:"line",source:"queued-task-routes",
  paint:{"line-width":2,"line-dasharray":[2,2],"line-color":"#6b8794","line-opacity":0.65}
 });
 if(!map.getLayer("selected-task-routes"))map.addLayer({
  id:"selected-task-routes",type:"line",source:"selected-task-routes",
  paint:{"line-width":4,"line-color":"#72dfff"}
 });
 if(!map.getLayer("entity-icons"))map.addLayer({
  id:"entity-icons",type:"symbol",source:"entity-features",
  layout:{
   "icon-image":["get","icon"],
   "icon-size":0.8,
   "icon-rotate":["get","heading"],
   "icon-rotation-alignment":"map",
   "icon-allow-overlap":true,
   "icon-ignore-placement":true
  }
 });
 if(!map.getLayer("task-waypoints"))map.addLayer({
  id:"task-waypoints",type:"symbol",source:"task-waypoints",
  layout:{
   "icon-image":"task-waypoint",
   "icon-size":0.8,
   "icon-allow-overlap":true,
   "icon-ignore-placement":true
  }
 });
 promoteOperationalLayers(map);
},[entities,tasks,selectedTaskId,selectedEntity?.entity_id,history,mapReady,hiddenGeoIds,hiddenGeoClasses]);

useEffect(()=>{
 const map=mapRef.current;
 if(!map)return;

const click=(ev:any)=>{
 // Operational Assets and Tracks always win hit-testing over chart reference data.
 if(map.getLayer("entity-icons")){
  const operational=map.queryRenderedFeatures(ev.point,{layers:["entity-icons"]})?.[0];
  const operationalId=operational?.properties?.entity_id;
  const operationalEntity=entities.find(e=>e.entity_id===operationalId);
  if(operationalEntity){
   setSelectedGisFeature(null);setSelectedEntity(operationalEntity);setSelectedTaskId(null);setRightOpen(true);
   if(operationalEntity.template==="ASSET")setAssetId(operationalEntity.entity_id);
   return;
  }
 }
 const coreGeoLayers=["core-geoentities-point","core-geoentities-soundings","core-geoentities-line","core-geoentities-fill"].filter(id=>Boolean(map.getLayer(id)));
 const coreGeo=coreGeoLayers.length?map.queryRenderedFeatures(ev.point,{layers:coreGeoLayers})?.[0]:null;
 if(coreGeo){
  const entity=entities.find(e=>e.entity_id===coreGeo.properties?.entity_id);
  if(entity){setSelectedGisFeature(null);setSelectedEntity(entity);setSelectedTaskId(null);setRightOpen(true);return}
 }
 const gisIds=(map.getStyle().layers||[]).map(x=>x.id).filter(id=>id.startsWith("gis-")&&(id.endsWith("-fill")||id.endsWith("-line")||id.endsWith("-circle")||id.endsWith("-symbol")));
 if(gisIds.length){
  const gis=map.queryRenderedFeatures(ev.point,{layers:gisIds})?.[0];
  if(gis){setSelectedGisFeature({properties:gis.properties||{},geometry:gis.geometry});setSelectedEntity(null);setSelectedTaskId(null);setRightOpen(true);return}
 }
};
 const move=(ev:any)=>{
  if(!map.getLayer("entity-icons"))return;
  const gisIds=(map.getStyle().layers||[]).map(x=>x.id).filter(id=>id.startsWith("gis-"));
  const layers=["entity-icons","core-geoentities-fill","core-geoentities-line","core-geoentities-point","core-geoentities-soundings",...gisIds].filter(id=>Boolean(map.getLayer(id)));
  const features=layers.length?map.queryRenderedFeatures(ev.point,{layers}):[];
  map.getCanvas().style.cursor=features.length?"pointer":"";
 };

 map.on("click",click);
 map.on("mousemove",move);
 return()=>{
  map.off("click",click);
  map.off("mousemove",move);
 };
},[entities,mapReady]);

function toggleHiddenEntity(e:Entity){setHiddenGeoIds(prev=>{const next=new Set(prev);next.has(e.entity_id)?next.delete(e.entity_id):next.add(e.entity_id);return next;});}
function toggleHiddenClass(e:Entity){const cls=geoClass(e);setHiddenGeoClasses(prev=>{const next=new Set(prev);next.has(cls)?next.delete(cls):next.add(cls);return next;});}
const hideSelectedEncClass=async()=>{
 const props=selectedGisFeature?.properties||{};
 const pluginId=props.__og_plugin_id,layerId=props.__og_layer_id;
 if(!pluginId||!layerId)return;
 const response=await fetch(`${API}/api/v1/gis/layers/${encodeURIComponent(pluginId)}/${encodeURIComponent(layerId)}/hide-class`,{method:"POST"});
 if(!response.ok){setEncStatus("Could not hide ENC class");return}
 const className=props.__og_class_name||props.__og_layer_name;
 setSelectedGisFeature(null);setEncStatus(`${className} hidden`);
 const layersResponse=await fetch(`${API}/api/v1/gis/layers`);
 if(layersResponse.ok)setGisLayers(await layersResponse.json());
};

useEffect(()=>{
 const map=mapRef.current,t=selectedTask;
 if(!map||!t)return;
 const a=entities.find(e=>e.entity_id===t.assigned_agent_id)?.components?.location;
 const o=t.specification?.objective;
 let target:[number,number]|null=null;
 if(o?.type==="POINT")target=[Number(o.position.longitude),Number(o.position.latitude)];
 if(o?.type==="ENTITY"){
  const l=entities.find(e=>e.entity_id===o.entity_id)?.components?.location;
  if(l)target=[Number(l.longitude),Number(l.latitude)];
 }
 if(a&&target){
  const bounds=new maplibregl.LngLatBounds();
  bounds.extend([Number(a.longitude),Number(a.latitude)]).extend(target);
  map.fitBounds(bounds,{padding:100,maxZoom:14});
 }
},[selectedTaskId]);

 return <div className={`shell ${leftDrawer?"left-open":"left-closed"} ${rightOpen?"right-open":"right-closed"}`}><header><div className="headerControls"><NavMenu active="map"/><button className={`headerTool ${leftDrawer==="assets"?"active":""}`} onClick={()=>setLeftDrawer(leftDrawer==="assets"?null:"assets")} title="Assets" aria-label="Open assets">◆</button><button className={`headerTool ${leftDrawer==="tracks"?"active":""}`} onClick={()=>setLeftDrawer(leftDrawer==="tracks"?null:"tracks")} title="Tracks" aria-label="Open tracks">◎</button><button className={`headerTool ${leftDrawer==="geoentities"?"active":""}`} onClick={()=>setLeftDrawer(leftDrawer==="geoentities"?null:"geoentities")} title="Geo-Entities" aria-label="Open geo-entities">⬡</button></div><div className="headerStatus">{encStatus&&<span className={encLoading?"encLoad active":"encLoad"}>{encStatus}</span>}<div className={connected?"connection online":"connection"}><i/>{connected?"LIVE":"RECONNECTING"}</div></div></header>{leftDrawer&&<aside className="left"><button className="drawerClose leftClose" onClick={()=>setLeftDrawer(null)} aria-label="Hide list">‹</button><div className="panelTitle">{leftDrawer==="tracks"?"TRACKS":leftDrawer==="geoentities"?"GEO-ENTITIES":"ASSETS"}</div><input value={filter} onChange={e=>setFilter(e.target.value)} placeholder={leftDrawer==="tracks"?"Search tracks":leftDrawer==="geoentities"?"Search geo-entities":"Search assets"}/><div className="entityList">{(leftDrawer==="tracks"?tracks:leftDrawer==="assets"?operationalAssets:coreGeoEntities).map(e=><button key={e.entity_id} className={`entityRow ${selectedEntity?.entity_id===e.entity_id?"selected":""} ${e.template==="GEOENTITY"&&(hiddenGeoIds.has(e.entity_id)||hiddenGeoClasses.has(geoClass(e)))?"mapHidden":""}`} onDoubleClick={()=>e.template==="TRACK"&&composeTrack(e)} onClick={()=>{setSelectedGisFeature(null);setSelectedEntity(e);setSelectedTaskId(null);setRightOpen(true);if(e.template==="ASSET"||e.template==="SENSOR")setAssetId(e.entity_id)}}><span className={`entityGlyph ${e.template.toLowerCase()} ${fused(e)?"fused":""}`}/><span><strong>{nameOf(e)}</strong><small>{e.components?.ontology?.platform_type||e.template}{fused(e)?" · FUSED":""}{e.template==="GEOENTITY"&&(hiddenGeoIds.has(e.entity_id)||hiddenGeoClasses.has(geoClass(e)))?" · HIDDEN":""}</small></span></button>)}{leftDrawer==="geoentities"&&pluginGeoEntities.map((f:any)=><button key={`${f.__sourceId}-${String(f.id)}`} className={`entityRow ${selectedGisFeature?.id===f.id?"selected":""}`} onClick={()=>{setSelectedEntity(null);setSelectedTaskId(null);setSelectedGisFeature(f);setRightOpen(true)}}><span className="entityGlyph geoentity"/><span><strong>{f.__displayName}</strong><small>{f.properties?.__og_class_name||"GIS feature"} · {f.properties?.__og_dataset||"plugin"}</small></span></button>)}</div><div className="panelTitle tasksTitle">TASK QUEUES</div><div className="taskList">{tasks.filter(t=>!TERMINAL.has(t.status)).map(t=><button key={t.task_id} className={`taskRow ${selectedTaskId===t.task_id?"selected":""}`} onClick={()=>{setSelectedGisFeature(null);setSelectedTaskId(t.task_id);setSelectedEntity(null);setRightOpen(true)}}><div><strong>#{t.queue_position} {taskName(t)}</strong><small>{t.assigned_agent_id}</small></div><span>{Math.round((t.progress||0)*100)}%</span><div className="progress"><i style={{width:`${(t.progress||0)*100}%`}}/></div><small>{t.status_message||t.status}</small></button>)}</div></aside>} {!leftDrawer&&<button className="drawerHandle leftHandle" onClick={()=>setLeftDrawer("assets")} aria-label="Show assets">›</button>}<main ref={mapEl}></main><aside className={`right ${rightOpen?"":"collapsed"}`}><button className="drawerClose rightClose" onClick={()=>setRightOpen(false)} aria-label="Hide details">›</button>{selectedGisFeature?<><div className="panelTitle">ENC FEATURE</div><h2>{selectedGisFeature.properties?.OBJNAM||selectedGisFeature.properties?.NOBJNM||selectedGisFeature.properties?.__og_layer_name||"Chart feature"}</h2><div className="tags"><span>{selectedGisFeature.properties?.__og_class_name||selectedGisFeature.properties?.__og_layer_name}</span><span>{selectedGisFeature.properties?.__og_dataset||"NOAA ENC"}</span></div><section><h3>Visibility</h3><button className="quiet hideClassButton" onClick={hideSelectedEncClass}>Hide this class</button><small>Hides this ENC class across every chart scale. Restore it from the NOAA ENC plugin configuration.</small></section><section><h3>Feature information</h3><dl>{Object.entries(selectedGisFeature.properties||{}).filter(([k,v])=>!k.startsWith("__og_")&&v!==null&&v!=="").slice(0,24).map(([k,v])=><><dt key={`${k}-k`}>{k}</dt><dd key={`${k}-v`}>{String(v)}</dd></>)}</dl></section><section><h3>Geometry</h3><pre>{JSON.stringify(selectedGisFeature.geometry,null,2)}</pre></section></>:selectedTask?<><div className="panelTitle">TASK</div><h2>{taskName(selectedTask)}</h2><div className="tags"><span>{selectedTask.status}</span><span>#{selectedTask.queue_position}</span></div><section><h3>Assignment</h3><dl><dt>Agent</dt><dd>{selectedTask.assigned_agent_id}</dd><dt>Progress</dt><dd>{Math.round((selectedTask.progress||0)*100)}%</dd><dt>Status</dt><dd>{selectedTask.status_message||selectedTask.status}</dd><dt>Priority</dt><dd>{(selectedTask as any).priority??50}</dd><dt>Attempt</dt><dd>{(selectedTask as any).attempt??0} / {(selectedTask as any).maximum_attempts??1}</dd></dl></section><section><h3>Objective</h3><pre>{JSON.stringify(selectedTask.specification?.objective,null,2)}</pre></section><section><h3>Parameters</h3><pre>{JSON.stringify(selectedTask.specification?.parameters,null,2)}</pre></section>{!TERMINAL.has(selectedTask.status)&&<button className="danger" onClick={()=>setCancel(selectedTask)}>Cancel task</button>}</>:selectedEntity?<><div className="panelTitle">ENTITY</div><h2>{nameOf(selectedEntity)}</h2><a className="quiet buttonLink" target="_blank" rel="noreferrer" href={`/entities/${encodeURIComponent(selectedEntity.entity_id)}`}>Open profile ↗</a><div className="tags"><span>{selectedEntity.template}</span>{selectedEntity.components?.ontology?.platform_type&&<span>{selectedEntity.components.ontology.platform_type}</span>}{fused(selectedEntity)&&<span>FUSED</span>}</div>{selectedEntity.template==="TRACK"&&<section><h3>Tasking</h3><select value={assetId} onChange={e=>setAssetId(e.target.value)}>{assets.map(a=><option key={a.entity_id} value={a.entity_id}>{nameOf(a)}</option>)}</select><button className="primary" onClick={()=>composeTrack(selectedEntity)}>Create task</button></section>}{selectedEntity.components?.video?.live_available&&<section><h3>Live view</h3><LiveCamera video={selectedEntity.components.video}/><small>Source supplied directly by the camera adapter.</small></section>}{(selectedEntity.template==="ASSET"||selectedEntity.template==="SENSOR")&&<section><h3>Tasking</h3><button className="primary" onClick={()=>{setAssetId(selectedEntity.entity_id);setPoint(null);setSelectedTaskId(null);setTaskType(selectedEntity.template==="SENSOR"?"opengrid.tasks.v1.CaptureSnapshot":"opengrid.tasks.v1.Arm");setReview(false);setComposer(true)}}>Create vehicle task</button></section>}{selectedEntity.template==="GEOENTITY"&&<section><h3>Map visibility</h3><button className="quiet" onClick={()=>toggleHiddenEntity(selectedEntity)}>{hiddenGeoIds.has(selectedEntity.entity_id)?"Show this entity":"Hide this entity"}</button><button className="quiet" onClick={()=>toggleHiddenClass(selectedEntity)}>{hiddenGeoClasses.has(geoClass(selectedEntity))?`Show class ${geoClass(selectedEntity)}`:`Hide class ${geoClass(selectedEntity)}`}</button><small>Hidden Geo-Entities remain available in the drawer and profile.</small></section>}<section><h3>Identity</h3><dl><dt>ID</dt><dd>{selectedEntity.entity_id}</dd><dt>Revision</dt><dd>{selectedEntity.revision}</dd><dt>Source</dt><dd>{selectedEntity.components?.provenance?.source_system||"—"}</dd></dl></section><section><h3>Location</h3><dl><dt>Latitude</dt><dd>{selectedEntity.components?.location?.latitude?.toFixed?.(6)||"—"}</dd><dt>Longitude</dt><dd>{selectedEntity.components?.location?.longitude?.toFixed?.(6)||"—"}</dd><dt>Heading</dt><dd>{selectedEntity.components?.location?.heading_degrees??"—"}°</dd><dt>Speed</dt><dd>{selectedEntity.components?.location?.speed_mps??"—"} m/s</dd></dl></section>{selectedEntity.template==="ASSET"&&<section><h3>Available capabilities</h3><div className="chips">{(selectedEntity.components?.capabilities?.available||[]).map((c:any)=><span key={c.name}>{c.name}</span>)}</div></section>}<section><h3>Components</h3><pre>{JSON.stringify(selectedEntity.components,null,2)}</pre></section></>:<div className="empty"><div>⌖</div>Select an entity or task</div>}</aside>{!rightOpen&&<button className="drawerHandle rightHandle" onClick={()=>setRightOpen(true)} aria-label="Show details">‹</button>}{composer&&<div className="modalBackdrop"><div className="modal"><div className="panelTitle">TASK COMPOSER</div>{!review?<><label>Agent<select value={assetId} onChange={e=>setAssetId(e.target.value)}>{assets.map(a=><option key={a.entity_id} value={a.entity_id}>{nameOf(a)}</option>)}</select></label><label>Available task<select value={taskType} onChange={e=>{setTaskType(e.target.value);setRadius(e.target.value.endsWith("Investigate")?50:20)}}>{valid.map(d=><option key={d.type} value={d.type}>{d.display_name}</option>)}</select></label>{(taskType.endsWith("Navigate")||taskType.endsWith("LaunchAndNavigate")||taskType.endsWith("Loiter")||taskType.endsWith("Investigate"))&&<label>Speed (m/s)<input type="number" min="0" step=".5" value={speed} onChange={e=>setSpeed(Number(e.target.value))}/></label>}{(taskType.endsWith("Navigate")||taskType.endsWith("LaunchAndNavigate")||taskType.endsWith("Loiter")||taskType.endsWith("Investigate"))&&<label>{taskType.endsWith("Investigate")?"Stand-off radius (m)":"Arrival / loiter radius (m)"}<input type="number" min="1" value={radius} onChange={e=>setRadius(Number(e.target.value))}/></label>}{(taskType.endsWith("Takeoff")||taskType.endsWith("Navigate")||taskType.endsWith("LaunchAndNavigate")||taskType.endsWith("Loiter"))&&<label>Altitude (m)<input type="number" min="2" value={altitude} onChange={e=>setAltitude(Number(e.target.value))}/></label>}<label>Priority (0–100)<input type="number" min="0" max="100" value={priority} onChange={e=>setPriority(Number(e.target.value))}/></label><label>Timeout (seconds)<input type="number" min="1" value={timeoutSeconds} onChange={e=>setTimeoutSeconds(Number(e.target.value))}/></label><label>Maximum attempts<input type="number" min="1" max="10" value={maximumAttempts} onChange={e=>setMaximumAttempts(Number(e.target.value))}/></label><div className="modalActions"><button className="quiet" onClick={()=>setComposer(false)}>Close</button><button className="primary" disabled={!valid.length} onClick={()=>setReview(true)}>Review task</button></div></>:<><h3>Confirm send task</h3><dl><dt>Task</dt><dd>{defs.find(d=>d.type===taskType)?.display_name}</dd><dt>Agent</dt><dd>{assetId}</dd><dt>Objective</dt><dd>{selectedEntity?.template==="TRACK"?nameOf(selectedEntity):point?`${point.lat.toFixed(5)}, ${point.lon.toFixed(5)}`:"—"}</dd>{(taskType.endsWith("Navigate")||taskType.endsWith("LaunchAndNavigate")||taskType.endsWith("Loiter")||taskType.endsWith("Investigate"))&&<><dt>Speed</dt><dd>{speed} m/s</dd><dt>Radius</dt><dd>{radius} m</dd></>}{(taskType.endsWith("Takeoff")||taskType.endsWith("Navigate")||taskType.endsWith("LaunchAndNavigate")||taskType.endsWith("Loiter"))&&<><dt>Altitude</dt><dd>{altitude} m</dd></>}</dl><div className="modalActions"><button className="quiet" onClick={()=>setReview(false)}>Back</button><button className="primary" onClick={send}>Confirm send</button></div></>}</div></div>}{cancel&&<div className="modalBackdrop"><div className="modal"><div className="panelTitle">CONFIRM CANCELLATION</div><h2>Cancel {taskName(cancel)}?</h2><p>This stops active execution or removes the queued task from future execution.</p><div className="modalActions"><button className="quiet" onClick={()=>setCancel(null)}>Keep task</button><button className="danger" onClick={()=>cancelTask(cancel)}>Cancel task</button></div></div></div>}</div>;
}
