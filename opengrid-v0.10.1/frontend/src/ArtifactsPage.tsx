import {useEffect,useState} from "react";
import NavMenu from "./NavMenu";
const API="";
type Artifact={artifact_id:string;name:string;artifact_type:string;content_type:string;size_bytes:number;sha256:string;metadata:any;created_at:string};
type Entity={entity_id:string;template:string;components:any};
const template=JSON.stringify({items:[
 {command:22,frame:3,latitude:41.49,longitude:-71.315,altitude_m:20},
 {command:16,frame:3,latitude:41.492,longitude:-71.312,altitude_m:30},
 {command:16,frame:3,latitude:41.494,longitude:-71.309,altitude_m:30},
 {command:20,frame:3,latitude:0,longitude:0,altitude_m:0}
]},null,2);
export default function ArtifactsPage(){
 const[a,setA]=useState<Artifact[]>([]),[selected,setSelected]=useState<Artifact|null>(null),[assets,setAssets]=useState<Entity[]>([]);
 const[name,setName]=useState("mission.json"),[content,setContent]=useState(template),[error,setError]=useState(""),[asset,setAsset]=useState("");
 const load=async()=>{try{const[r,e]=await Promise.all([fetch("/api/v1/artifacts"),fetch("/api/v1/entities?template=ASSET")]);if(!r.ok)throw new Error(await r.text());setA(await r.json());if(e.ok){const x=await e.json();setAssets(x);if(!asset&&x.length)setAsset(x[0].entity_id)}setError("")}catch(x:any){setError(String(x))}};
 useEffect(()=>{load()},[]);
 const create=async()=>{try{JSON.parse(content)}catch{return setError("Mission must be valid JSON")};const r=await fetch("/api/v1/artifacts/text",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name,artifact_type:"MAVLINK_MISSION",content_type:"application/json",content,metadata:{schema:"opengrid.mavlink.mission.v1"}})});if(!r.ok)return setError(await r.text());const x=await r.json();setA(p=>[x,...p]);setSelected(x)};
 const execute=async()=>{if(!selected||!asset)return;const r=await fetch("/api/v1/tasks",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({description:`Execute ${selected.name}`,specification:{type:"opengrid.tasks.v1.ExecuteMission",objective:{type:"ARTIFACT",artifact_id:selected.artifact_id},parameters:{auto_arm:true}},assigned_agent_id:asset,created_by:"operator-ui"})});if(!r.ok)return setError(await r.text());alert("Mission queued")};
 return <div className="adminShell"><header><NavMenu active="artifacts"/><div/></header><div className="adminPage"><section className="adminList"><div className="panelTitle">ARTIFACTS</div>{error&&<div className="errorBanner">{error}</div>}{a.map(x=><button className={`artifactCard ${selected?.artifact_id===x.artifact_id?"selected":""}`} key={x.artifact_id} onClick={()=>setSelected(x)}><strong>{x.name}</strong><small>{x.artifact_type} · {x.size_bytes} bytes</small></button>)}</section><section className="adminDetail">{selected?<><div className="panelTitle">ARTIFACT</div><h2>{selected.name}</h2><pre>{JSON.stringify(selected,null,2)}</pre>{selected.artifact_type==="MAVLINK_MISSION"&&<><label>Execute on<select value={asset} onChange={e=>setAsset(e.target.value)}>{assets.map(x=><option key={x.entity_id} value={x.entity_id}>{x.components?.aliases?.name||x.entity_id}</option>)}</select></label><button className="primary" onClick={execute}>Queue Execute Mission</button></>}<button className="quiet" onClick={()=>setSelected(null)}>Create another</button></>:<><div className="panelTitle">CREATE MISSION ARTIFACT</div><h2>MAVLink Mission</h2><label>Name<input value={name} onChange={e=>setName(e.target.value)}/></label><label>Mission JSON<textarea className="missionEditor" value={content} onChange={e=>setContent(e.target.value)}/></label><button className="primary" onClick={create}>Save Mission Artifact</button></>}</section></div></div>
}
