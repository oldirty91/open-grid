import { useEffect, useMemo, useRef, useState } from "react";
import maplibregl, { Map, MapMouseEvent } from "maplibre-gl";
const API=import.meta.env.VITE_API_URL||"http://localhost:8000"; const WS=import.meta.env.VITE_WS_URL||"ws://localhost:8000";
type Entity={entity_id:string;revision:number;template:string;is_live:boolean;components:Record<string,any>;};
type Task={task_id:string;description:string;specification:Record<string,any>;assigned_agent_id:string;queue_position:number;status:string;progress:number;status_message?:string;};
type Def={type:string;display_name:string;objective_types:string[];parameter_schema:Record<string,any>;};
type Sample={latitude:number;longitude:number;timestamp:string;};
const TERMINAL=new Set(["STATUS_DONE_OK","STATUS_DONE_NOT_OK","STATUS_CANCELED"]);
const nameOf=(e?:Entity|null)=>e?.components?.aliases?.name||e?.entity_id||"Unknown"; const fused=(e:Entity)=>e.components?.ontology?.track_type==="FUSED"; const taskName=(t:Task)=>t.specification?.type?.split(".").pop()||"Task";
function appendLiveSample(history:Record<string,Sample[]>,entity:Entity){
 const l=entity.components?.location;
 if(l?.latitude==null||l?.longitude==null)return history;
 const previous=history[entity.entity_id]||[];
 const last=previous[previous.length-1];
 if(last&&Math.abs(last.latitude-l.latitude)<1e-8&&Math.abs(last.longitude-l.longitude)<1e-8)return history;
 const next=[...previous,{latitude:Number(l.latitude),longitude:Number(l.longitude),timestamp:new Date().toISOString()}];
 return {...history,[entity.entity_id]:next.slice(-1000)};
}
function platformKind(e:Entity){const o=e.components?.ontology||{},x=String(o.specific_type||o.platform_type||e.components?.classification?.type||e.components?.ais?.ship_type||e.components?.adsb?.aircraft_type||"").toUpperCase();if(x.includes("HELICOPTER")||x.includes("ROTOR"))return"HELICOPTER";if(x.includes("CARGO")&&(x.includes("AIR")||o.domain==="AIR"))return"CARGO_PLANE";if(x.includes("PLANE")||x.includes("AIRCRAFT")||x.includes("FIXED_WING"))return"PLANE";if(x.includes("UAV")||x.includes("DRONE"))return"DRONE";if(x.includes("AUV")||x.includes("SUBMARINE"))return"AUV";if(x.includes("USV"))return"USV";if(x.includes("CARGO")||x.includes("TANKER")||x.includes("SHIP")||x.includes("VESSEL"))return"SHIP";if(x.includes("TRAIN")||x.includes("RAIL"))return"TRAIN";if(x.includes("TANK")||x.includes("ARMORED"))return"TANK";if(x.includes("UGV")||x.includes("GROUND_VEHICLE"))return"GROUND";if(e.template==="TRACK"&&e.components?.ais)return"SHIP";if(e.template==="TRACK"&&e.components?.adsb)return"PLANE";return e.template==="ASSET"?"ROBOT":"CONTACT";}

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
 const kinds=["SHIP","USV","AUV","PLANE","CARGO_PLANE","HELICOPTER","DRONE","TRAIN","TANK","GROUND","ROBOT","CONTACT"];
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
 const [entities,setEntities]=useState<Entity[]>([]),[tasks,setTasks]=useState<Task[]>([]),[defs,setDefs]=useState<Def[]>([]),[selectedEntity,setSelectedEntity]=useState<Entity|null>(null),[selectedTaskId,setSelectedTaskId]=useState<string|null>(null),[assetId,setAssetId]=useState("asset-alpha"),[filter,setFilter]=useState(""),[connected,setConnected]=useState(false),[point,setPoint]=useState<{lat:number;lon:number}|null>(null),[composer,setComposer]=useState(false),[review,setReview]=useState(false),[taskType,setTaskType]=useState(""),[speed,setSpeed]=useState(3),[radius,setRadius]=useState(20),[cancel,setCancel]=useState<Task|null>(null),[history,setHistory]=useState<Record<string,Sample[]>>({}),[mapReady,setMapReady]=useState(0);
 const selectedTask=tasks.find(t=>t.task_id===selectedTaskId)||null, assets=useMemo(()=>entities.filter(e=>e.template==="ASSET"),[entities]);
 useEffect(()=>{Promise.all([fetch(`${API}/api/v1/entities`),fetch(`${API}/api/v1/tasks`),fetch(`${API}/api/v1/task-definitions`)]).then(async([e,t,d])=>{if(e.ok){const items:Entity[]=await e.json();setEntities(items);setHistory(p=>items.reduce((acc,item)=>appendLiveSample(acc,item),p));}if(t.ok)setTasks(await t.json());if(d.ok)setDefs(await d.json());});},[]);
 useEffect(()=>{if(!mapEl.current||mapRef.current)return;const map=new maplibregl.Map({container:mapEl.current,style:{version:8,sources:{osm:{type:"raster",tiles:["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],tileSize:256,attribution:"© OpenStreetMap contributors"}},layers:[{id:"osm",type:"raster",source:"osm"}]},center:[-71.305,41.498],zoom:12});map.addControl(new maplibregl.NavigationControl(),"bottom-right");map.on("load",()=>setMapReady(x=>x+1));map.on("contextmenu",(ev:MapMouseEvent)=>{setPoint({lat:ev.lngLat.lat,lon:ev.lngLat.lng});setSelectedTaskId(null);setTaskType("opengrid.tasks.v1.Navigate");setRadius(20);setReview(false);setComposer(true);});mapRef.current=map;},[]);
 useEffect(()=>{let s:WebSocket|null=null,r:number|undefined;const go=()=>{s=new WebSocket(`${WS}/api/v1/stream`);s.onopen=()=>{setConnected(true);s?.send("subscribe")};s.onmessage=ev=>{const m=JSON.parse(ev.data),d=m.data;if(m.type.startsWith("entity.")&&d){const e:Entity=d.entity||d;if(e.entity_id){setEntities(p=>p.some(x=>x.entity_id===e.entity_id)?p.map(x=>x.entity_id===e.entity_id?e:x):[e,...p]);setHistory(p=>appendLiveSample(p,e));setSelectedEntity(p=>p?.entity_id===e.entity_id?e:p);}}if(m.type.startsWith("task.")&&d?.task_id)setTasks(p=>p.some(x=>x.task_id===d.task_id)?p.map(x=>x.task_id===d.task_id?d:x):[...p,d]);};s.onclose=()=>{setConnected(false);r=window.setTimeout(go,1500)};s.onerror=()=>s?.close();};go();return()=>{if(r)clearTimeout(r);s?.close();};},[]);
 const valid=useMemo(()=>{const a=assets.find(x=>x.entity_id===assetId),adv=new Set((a?.components?.task_catalog?.definitions||[]).map((x:any)=>typeof x==="string"?x:x.type));return defs.filter(d=>adv.has(d.type)&&((point&&d.objective_types.includes("POINT"))||(selectedEntity?.template==="TRACK"&&d.objective_types.includes("ENTITY"))));},[assets,assetId,defs,point,selectedEntity]);
 useEffect(()=>{if(composer&&valid.length&&!valid.some(d=>d.type===taskType))setTaskType(valid[0].type);},[composer,valid]);
 useEffect(()=>{
 if(!selectedEntity)return;
 const load=()=>fetch(`${API}/api/v1/entities/${selectedEntity.entity_id}/location-history?limit=2000`)
  .then(r=>r.ok?r.json():[])
  .then((samples:Sample[])=>setHistory(p=>({...p,[selectedEntity.entity_id]:mergeSamples(p[selectedEntity.entity_id]||[],samples)})))
  .catch(()=>{});
 load();
 const timer=window.setInterval(load,2000);
 return()=>window.clearInterval(timer);
},[selectedEntity?.entity_id]);
 async function send(){const d=defs.find(x=>x.type===taskType);if(!d)return;const objective=(selectedEntity?.template==="TRACK"&&d.objective_types.includes("ENTITY"))?{type:"ENTITY",entity_id:selectedEntity.entity_id}:point?{type:"POINT",position:{latitude:point.lat,longitude:point.lon}}:null;if(!objective)return alert("Select a compatible objective");const params=taskType.endsWith("Investigate")?{speed_mps:speed,standoff_m:radius}:{speed_mps:speed,arrival_radius_m:radius};const res=await fetch(`${API}/api/v1/tasks`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({description:`${d.display_name} using ${assetId}`,specification:{type:taskType,objective,parameters:params},assigned_agent_id:assetId,created_by:"operator-ui"})});if(!res.ok)return alert(await res.text());const t=await res.json();setTasks(p=>p.some(x=>x.task_id===t.task_id)?p:[...p,t]);setSelectedTaskId(t.task_id);setComposer(false);setPoint(null);}
 async function cancelTask(t:Task){const r=await fetch(`${API}/api/v1/tasks/${t.task_id}/cancel`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({reason:"Canceled by operator",actor_id:"operator-ui"})});if(!r.ok)return alert(await r.text());const u=await r.json();setTasks(p=>p.map(x=>x.task_id===u.task_id?u:x));setCancel(null);}
 function composeTrack(e:Entity){setSelectedEntity(e);setSelectedTaskId(null);setPoint(null);setTaskType("opengrid.tasks.v1.Investigate");setRadius(50);setReview(false);setComposer(true);}
 const visible=useMemo(()=>{const q=filter.toLowerCase();return entities.filter(e=>!q||e.entity_id.toLowerCase().includes(q)||nameOf(e).toLowerCase().includes(q)||e.template.toLowerCase().includes(q));},[entities,filter]);
 
useEffect(()=>{
 const map=mapRef.current;
 if(!map||!map.isStyleLoaded())return;
 ensureMapImages(map);

 const entityFeatures=entities.flatMap(e=>{
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

 setSource("entity-features",{type:"FeatureCollection",features:entityFeatures});
 setSource("queued-task-routes",{type:"FeatureCollection",features:queuedRoutes});
 setSource("selected-task-routes",{type:"FeatureCollection",features:selectedRoutes});
 setSource("task-waypoints",{type:"FeatureCollection",features:waypoints});
 setSource("breadcrumbs",{type:"FeatureCollection",features:trail});

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
},[entities,tasks,selectedTaskId,selectedEntity?.entity_id,history,mapReady]);

useEffect(()=>{
 const map=mapRef.current;
 if(!map)return;

 const click=(ev:any)=>{
  if(!map.getLayer("entity-icons"))return;
  const features=map.queryRenderedFeatures(ev.point,{layers:["entity-icons"]});
  const id=features?.[0]?.properties?.entity_id;
  const entity=entities.find(e=>e.entity_id===id);
  if(!entity)return;
  setSelectedEntity(entity);
  setSelectedTaskId(null);
  if(entity.template==="ASSET")setAssetId(entity.entity_id);
 };

 const move=(ev:any)=>{
  if(!map.getLayer("entity-icons"))return;
  const features=map.queryRenderedFeatures(ev.point,{layers:["entity-icons"]});
  map.getCanvas().style.cursor=features.length?"pointer":"";
 };

 map.on("click",click);
 map.on("mousemove",move);
 return()=>{
  map.off("click",click);
  map.off("mousemove",move);
 };
},[entities,mapReady]);

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

 return <div className="shell"><header><div className="brand"><span>△</span> OPENGRID</div><nav className="topNav"><a className="active" href="/">Map</a><a href="/plugins">Plugins</a><a href="/artifacts">Artifacts</a></nav><div className={connected?"connection online":"connection"}><i/>{connected?"LIVE":"RECONNECTING"}</div></header><aside className="left"><div className="panelTitle">WORLD</div><input value={filter} onChange={e=>setFilter(e.target.value)} placeholder="Search entities"/><div className="entityList">{visible.map(e=><button key={e.entity_id} className={`entityRow ${selectedEntity?.entity_id===e.entity_id?"selected":""}`} onDoubleClick={()=>e.template==="TRACK"&&composeTrack(e)} onClick={()=>{setSelectedEntity(e);setSelectedTaskId(null);if(e.template==="ASSET")setAssetId(e.entity_id)}}><span className={`entityGlyph ${e.template.toLowerCase()} ${fused(e)?"fused":""}`}/><span><strong>{nameOf(e)}</strong><small>{e.components?.ontology?.platform_type||e.template}{fused(e)?" · FUSED":""}</small></span></button>)}</div><div className="panelTitle tasksTitle">TASK QUEUES</div><div className="taskList">{tasks.filter(t=>!TERMINAL.has(t.status)).map(t=><button key={t.task_id} className={`taskRow ${selectedTaskId===t.task_id?"selected":""}`} onClick={()=>{setSelectedTaskId(t.task_id);setSelectedEntity(null)}}><div><strong>#{t.queue_position} {taskName(t)}</strong><small>{t.assigned_agent_id}</small></div><span>{Math.round((t.progress||0)*100)}%</span><div className="progress"><i style={{width:`${(t.progress||0)*100}%`}}/></div><small>{t.status_message||t.status}</small></button>)}</div></aside><main ref={mapEl}></main><aside className="right">{selectedTask?<><div className="panelTitle">TASK</div><h2>{taskName(selectedTask)}</h2><div className="tags"><span>{selectedTask.status}</span><span>#{selectedTask.queue_position}</span></div><section><h3>Assignment</h3><dl><dt>Agent</dt><dd>{selectedTask.assigned_agent_id}</dd><dt>Progress</dt><dd>{Math.round((selectedTask.progress||0)*100)}%</dd><dt>Status</dt><dd>{selectedTask.status_message||selectedTask.status}</dd></dl></section><section><h3>Objective</h3><pre>{JSON.stringify(selectedTask.specification?.objective,null,2)}</pre></section><section><h3>Parameters</h3><pre>{JSON.stringify(selectedTask.specification?.parameters,null,2)}</pre></section>{!TERMINAL.has(selectedTask.status)&&<button className="danger" onClick={()=>setCancel(selectedTask)}>Cancel task</button>}</>:selectedEntity?<><div className="panelTitle">ENTITY</div><h2>{nameOf(selectedEntity)}</h2><div className="tags"><span>{selectedEntity.template}</span>{selectedEntity.components?.ontology?.platform_type&&<span>{selectedEntity.components.ontology.platform_type}</span>}{fused(selectedEntity)&&<span>FUSED</span>}</div>{selectedEntity.template==="TRACK"&&<section><h3>Tasking</h3><select value={assetId} onChange={e=>setAssetId(e.target.value)}>{assets.map(a=><option key={a.entity_id} value={a.entity_id}>{nameOf(a)}</option>)}</select><button className="primary" onClick={()=>composeTrack(selectedEntity)}>Create task</button></section>}<section><h3>Identity</h3><dl><dt>ID</dt><dd>{selectedEntity.entity_id}</dd><dt>Revision</dt><dd>{selectedEntity.revision}</dd><dt>Source</dt><dd>{selectedEntity.components?.provenance?.source_system||"—"}</dd></dl></section><section><h3>Location</h3><dl><dt>Latitude</dt><dd>{selectedEntity.components?.location?.latitude?.toFixed?.(6)||"—"}</dd><dt>Longitude</dt><dd>{selectedEntity.components?.location?.longitude?.toFixed?.(6)||"—"}</dd><dt>Heading</dt><dd>{selectedEntity.components?.location?.heading_degrees??"—"}°</dd><dt>Speed</dt><dd>{selectedEntity.components?.location?.speed_mps??"—"} m/s</dd></dl></section>{selectedEntity.template==="ASSET"&&<section><h3>Available capabilities</h3><div className="chips">{(selectedEntity.components?.capabilities?.available||[]).map((c:any)=><span key={c.name}>{c.name}</span>)}</div></section>}<section><h3>Components</h3><pre>{JSON.stringify(selectedEntity.components,null,2)}</pre></section></>:<div className="empty"><div>⌖</div>Select an entity or task</div>}</aside>{composer&&<div className="modalBackdrop"><div className="modal"><div className="panelTitle">TASK COMPOSER</div>{!review?<><label>Agent<select value={assetId} onChange={e=>setAssetId(e.target.value)}>{assets.map(a=><option key={a.entity_id} value={a.entity_id}>{nameOf(a)}</option>)}</select></label><label>Available task<select value={taskType} onChange={e=>{setTaskType(e.target.value);setRadius(e.target.value.endsWith("Investigate")?50:20)}}>{valid.map(d=><option key={d.type} value={d.type}>{d.display_name}</option>)}</select></label><label>Speed (m/s)<input type="number" min="0" step=".5" value={speed} onChange={e=>setSpeed(Number(e.target.value))}/></label><label>{taskType.endsWith("Investigate")?"Stand-off radius (m)":"Arrival radius (m)"}<input type="number" min="1" value={radius} onChange={e=>setRadius(Number(e.target.value))}/></label><div className="modalActions"><button className="quiet" onClick={()=>setComposer(false)}>Close</button><button className="primary" disabled={!valid.length} onClick={()=>setReview(true)}>Review task</button></div></>:<><h3>Confirm send task</h3><dl><dt>Task</dt><dd>{defs.find(d=>d.type===taskType)?.display_name}</dd><dt>Agent</dt><dd>{assetId}</dd><dt>Objective</dt><dd>{selectedEntity?.template==="TRACK"?nameOf(selectedEntity):point?`${point.lat.toFixed(5)}, ${point.lon.toFixed(5)}`:"—"}</dd><dt>Speed</dt><dd>{speed} m/s</dd><dt>Radius</dt><dd>{radius} m</dd></dl><div className="modalActions"><button className="quiet" onClick={()=>setReview(false)}>Back</button><button className="primary" onClick={send}>Confirm send</button></div></>}</div></div>}{cancel&&<div className="modalBackdrop"><div className="modal"><div className="panelTitle">CONFIRM CANCELLATION</div><h2>Cancel {taskName(cancel)}?</h2><p>This stops active execution or removes the queued task from future execution.</p><div className="modalActions"><button className="quiet" onClick={()=>setCancel(null)}>Keep task</button><button className="danger" onClick={()=>cancelTask(cancel)}>Cancel task</button></div></div></div>}</div>;
}
