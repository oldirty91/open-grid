import {useEffect,useState} from "react";
const API="";
type Plugin={plugin_id:string;name:string;version:string;plugin_type:string;protocol?:string;enabled:boolean;status:string;status_message?:string;metrics:Record<string,any>;configuration:Record<string,any>;last_heartbeat?:string};

const toJson=(value:any,fallback:any)=>{try{return JSON.parse(value)}catch{return fallback}};

export default function PluginsPage(){
 const [plugins,setPlugins]=useState<Plugin[]>([]),[selected,setSelected]=useState<Plugin|null>(null),[logs,setLogs]=useState<any[]>([]),[error,setError]=useState("");
 const [form,setForm]=useState<Record<string,any>>({}),[saving,setSaving]=useState(false);

 const load=async()=>{
  try{
   const r=await fetch(`${API}/api/v1/plugins`);
   if(!r.ok)throw new Error(await r.text());
   const items=await r.json();
   setPlugins(items);setError("");
   if(selected){
    const refreshed=items.find((x:Plugin)=>x.plugin_id===selected.plugin_id);
    if(refreshed)setSelected(refreshed);
   }
  }catch(e:any){setError(String(e?.message||e))}
 };
 useEffect(()=>{load();const t=setInterval(load,3000);return()=>clearInterval(t)},[]);
 useEffect(()=>{if(selected)setForm({...selected.configuration,websocket_api_key:selected.configuration?.websocket_api_key||""})},[selected?.plugin_id]);

 const pick=async(p:Plugin)=>{setSelected(p);setForm({...p.configuration});const r=await fetch(`${API}/api/v1/plugins/${p.plugin_id}/logs`);if(r.ok)setLogs(await r.json())};
 const toggle=async()=>{if(!selected)return;const a=selected.enabled?"disable":"enable";const r=await fetch(`${API}/api/v1/plugins/${selected.plugin_id}/${a}`,{method:"POST"});if(r.ok){const u=await r.json();setSelected(u);load()}};
 const save=async()=>{if(!selected)return;setSaving(true);const r=await fetch(`${API}/api/v1/plugins/${selected.plugin_id}/configuration`,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify({configuration:form})});setSaving(false);if(!r.ok){setError(await r.text());return}const u=await r.json();setSelected(u);setPlugins(p=>p.map(x=>x.plugin_id===u.plugin_id?u:x));setError("")};

 const mode=form.input_mode||"replay";
 return <div className="adminShell"><header><div className="brand"><span>△</span> OPENGRID</div><nav className="topNav"><a href="/">Map</a><a className="active" href="/plugins">Plugins</a><a href="/artifacts">Artifacts</a></nav><div/></header><div className="adminPage"><section className="adminList"><div className="panelTitle">PLUGINS</div><button className="quiet refreshButton" onClick={load}>Refresh registry</button>{error&&<div className="errorBanner">{error}</div>}{plugins.map(p=><button className={`pluginCard ${selected?.plugin_id===p.plugin_id?"selected":""}`} key={p.plugin_id} onClick={()=>pick(p)}><div><strong>{p.name}</strong><small>{p.protocol||p.plugin_type} · v{p.version}</small></div><span className={`pluginStatus ${p.enabled?p.status.toLowerCase():"disabled"}`}>{p.enabled?p.status:"DISABLED"}</span><dl><dt>Messages</dt><dd>{p.metrics?.messages_received??0}</dd><dt>Entities</dt><dd>{p.metrics?.entities_active??0}</dd><dt>Errors</dt><dd>{p.metrics?.parse_errors??0}</dd></dl></button>)}</section><section className="adminDetail">{!selected?<div className="empty"><div>◫</div>Select a plugin</div>:<><div className="panelTitle">PLUGIN DETAILS</div><h2>{selected.name}</h2><div className="tags"><span>{selected.plugin_type}</span><span>{selected.protocol}</span><span>{selected.status}</span></div>

 <section><h3>Connection</h3>
  <label>Input mode<select value={mode} onChange={e=>setForm({...form,input_mode:e.target.value})}><option value="replay">Replay</option><option value="udp">UDP server</option><option value="tcp">TCP server</option><option value="websocket">WebSocket</option></select></label>
  {mode==="replay"&&<label>Replay interval (seconds)<input type="number" step="0.1" value={form.replay_interval_s??1.5} onChange={e=>setForm({...form,replay_interval_s:Number(e.target.value)})}/></label>}
  {mode==="udp"&&<div className="configGrid"><label>Bind host<input value={form.udp_host??"0.0.0.0"} onChange={e=>setForm({...form,udp_host:e.target.value})}/></label><label>UDP port<input type="number" value={form.udp_port??10110} onChange={e=>setForm({...form,udp_port:Number(e.target.value)})}/></label></div>}
  {mode==="tcp"&&<div className="configGrid"><label>Server host<input value={form.tcp_host??"127.0.0.1"} onChange={e=>setForm({...form,tcp_host:e.target.value})}/></label><label>TCP port<input type="number" value={form.tcp_port??10110} onChange={e=>setForm({...form,tcp_port:Number(e.target.value)})}/></label></div>}
  {mode==="websocket"&&<>
   <label>Provider<select value={form.websocket_provider??"aisstream"} onChange={e=>setForm({...form,websocket_provider:e.target.value})}><option value="aisstream">AISStream.io</option><option value="generic">Generic WebSocket</option></select></label>
   <label>WebSocket URL<input value={form.websocket_url??"wss://stream.aisstream.io/v0/stream"} onChange={e=>setForm({...form,websocket_url:e.target.value})}/></label>
   {(form.websocket_provider??"aisstream")==="aisstream"?<>
    <label>API key<input type="password" value={form.websocket_api_key??""} onChange={e=>setForm({...form,websocket_api_key:e.target.value})}/></label>
    <label>Bounding boxes (JSON)<textarea value={JSON.stringify(form.bounding_boxes??[[[40.9,-71.8],[41.9,-70.8]]],null,2)} onChange={e=>setForm({...form,bounding_boxes:toJson(e.target.value,form.bounding_boxes)})}/></label>
    <label>Message types (JSON array)<textarea value={JSON.stringify(form.filter_message_types??["PositionReport"],null,2)} onChange={e=>setForm({...form,filter_message_types:toJson(e.target.value,form.filter_message_types)})}/></label>
    <label>MMSI filter (JSON array, optional)<textarea value={JSON.stringify(form.filter_mmsi??[],null,2)} onChange={e=>setForm({...form,filter_mmsi:toJson(e.target.value,form.filter_mmsi)})}/></label>
   </>:<label>Subscription JSON<textarea value={JSON.stringify(form.generic_subscription_json??{},null,2)} onChange={e=>setForm({...form,generic_subscription_json:toJson(e.target.value,form.generic_subscription_json)})}/></label>}
  </>}
  <button className="primary" disabled={saving} onClick={save}>{saving?"Saving…":"Save and reconnect"}</button>
 </section>

 <section><h3>Metrics</h3><pre>{JSON.stringify(selected.metrics,null,2)}</pre></section><div className="adminActions"><button className={selected.enabled?"danger":"primary"} onClick={toggle}>{selected.enabled?"Disable":"Enable"}</button><button className="quiet" onClick={()=>pick(selected)}>Refresh logs</button></div><section><h3>Logs</h3><div className="logList">{logs.length?logs.map(l=><div className="logRow" key={l.log_id}><strong>{l.level}</strong><span>{l.message}</span><small>{l.created_at}</small></div>):<small>No plugin logs yet.</small>}</div></section></>}</section></div></div>
}
