import { useEffect, useMemo, useRef, useState } from "react";
import maplibregl, { Map, Marker, MapMouseEvent } from "maplibre-gl";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000";
const WS = import.meta.env.VITE_WS_URL || "ws://localhost:8000";

type Entity = {
  entity_id: string;
  revision: number;
  template: string;
  is_live: boolean;
  components: Record<string, any>;
  component_provenance?: Record<string, any>;
  updated_at?: string;
};

type Task = {
  task_id: string;
  description: string;
  specification: Record<string, any>;
  assigned_agent_id: string;
  queue_position: number;
  status: string;
  progress: number;
  status_message?: string;
};

function nameOf(entity: Entity) {
  return entity.components?.aliases?.name || entity.entity_id;
}

function isFused(entity: Entity) {
  return entity.components?.ontology?.track_type === "FUSED";
}

function markerClass(entity: Entity) {
  if (entity.template === "ASSET") return "marker asset";
  if (isFused(entity)) return "marker fused";
  return "marker track";
}

export default function App() {
  const mapContainer = useRef<HTMLDivElement>(null);
  const mapRef = useRef<Map | null>(null);
  const markers = useRef<Record<string, Marker>>({});
  const [entities, setEntities] = useState<Entity[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [selected, setSelected] = useState<Entity | null>(null);
  const [selectedAssetId, setSelectedAssetId] = useState("asset-alpha");
  const [filter, setFilter] = useState("");
  const [connected, setConnected] = useState(false);
  const [contextPoint, setContextPoint] = useState<{lat:number;lon:number}|null>(null);

  const loadSnapshot = async () => {
    const [entitiesResponse, tasksResponse] = await Promise.all([
      fetch(`${API}/api/v1/entities`),
      fetch(`${API}/api/v1/tasks`)
    ]);
    if (entitiesResponse.ok) setEntities(await entitiesResponse.json());
    if (tasksResponse.ok) setTasks(await tasksResponse.json());
  };

  useEffect(() => {
    loadSnapshot();
  }, []);

  useEffect(() => {
    if (!mapContainer.current || mapRef.current) return;
    const map = new maplibregl.Map({
      container: mapContainer.current,
      style: {
        version: 8,
        sources: {
          osm: {
            type: "raster",
            tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
            tileSize: 256,
            attribution: "© OpenStreetMap contributors"
          }
        },
        layers: [{id:"osm",type:"raster",source:"osm"}]
      },
      center: [-71.305, 41.498],
      zoom: 12
    });
    map.addControl(new maplibregl.NavigationControl(), "bottom-right");
    map.on("contextmenu", (event: MapMouseEvent) => {
      setContextPoint({lat:event.lngLat.lat, lon:event.lngLat.lng});
    });
    mapRef.current = map;
  }, []);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let reconnect: number | undefined;
    const connect = () => {
      socket = new WebSocket(`${WS}/api/v1/stream`);
      socket.onopen = () => {
        setConnected(true);
        socket?.send("subscribe");
      };
      socket.onmessage = event => {
        const message = JSON.parse(event.data);
        const data = message.data;
        if (message.type.startsWith("entity.") && data) {
          const entity: Entity = data.entity || data;
          if (entity.entity_id) {
            setEntities(previous => {
              const found = previous.some(x => x.entity_id === entity.entity_id);
              return found
                ? previous.map(x => x.entity_id === entity.entity_id ? entity : x)
                : [entity, ...previous];
            });
            setSelected(previous =>
              previous?.entity_id === entity.entity_id ? entity : previous
            );
          }
        }
        if (message.type.startsWith("task.") && data?.task_id) {
          setTasks(previous => {
            const found = previous.some(x => x.task_id === data.task_id);
            return found
              ? previous.map(x => x.task_id === data.task_id ? data : x)
              : [...previous, data];
          });
        }
      };
      socket.onclose = () => {
        setConnected(false);
        reconnect = window.setTimeout(connect, 1500);
      };
      socket.onerror = () => socket?.close();
    };
    connect();
    return () => {
      if (reconnect) window.clearTimeout(reconnect);
      socket?.close();
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    for (const entity of entities) {
      const location = entity.components?.location;
      if (location?.latitude == null || location?.longitude == null) continue;
      let marker = markers.current[entity.entity_id];
      if (!marker) {
        const element = document.createElement("button");
        element.className = markerClass(entity);
        element.title = nameOf(entity);
        element.onclick = () => {
          setSelected(entity);
          if (entity.template === "ASSET") setSelectedAssetId(entity.entity_id);
        };
        marker = new maplibregl.Marker({element})
          .setLngLat([location.longitude, location.latitude])
          .addTo(map);
        markers.current[entity.entity_id] = marker;
      } else {
        marker.setLngLat([location.longitude, location.latitude]);
        marker.getElement().className = markerClass(entity);
        marker.getElement().onclick = () => {
          setSelected(entity);
          if (entity.template === "ASSET") setSelectedAssetId(entity.entity_id);
        };
      }
    }

    const routeFeatures = tasks
      .filter(task => !["STATUS_DONE_OK","STATUS_DONE_NOT_OK","STATUS_CANCELED"].includes(task.status))
      .map(task => {
        const asset = entities.find(x => x.entity_id === task.assigned_agent_id);
        const assetLoc = asset?.components?.location;
        const objective = task.specification?.objective;
        let target: [number, number] | null = null;
        if (objective?.type === "POINT") {
          target = [objective.position.longitude, objective.position.latitude];
        } else if (objective?.type === "ENTITY") {
          const targetEntity = entities.find(x => x.entity_id === objective.entity_id);
          const targetLoc = targetEntity?.components?.location;
          if (targetLoc) target = [targetLoc.longitude, targetLoc.latitude];
        }
        if (!assetLoc || !target) return null;
        return {
          type: "Feature",
          properties: {task_id:task.task_id},
          geometry: {
            type: "LineString",
            coordinates: [[assetLoc.longitude, assetLoc.latitude], target]
          }
        };
      })
      .filter(Boolean);

    const collection = {type:"FeatureCollection",features:routeFeatures} as GeoJSON.FeatureCollection;
    const source = map.getSource("task-routes") as maplibregl.GeoJSONSource | undefined;
    if (source) {
      source.setData(collection);
    } else if (map.isStyleLoaded()) {
      map.addSource("task-routes", {type:"geojson",data:collection});
      map.addLayer({
        id:"task-routes",
        type:"line",
        source:"task-routes",
        paint:{"line-width":2,"line-dasharray":[2,2],"line-color":"#72dfff"}
      });
    }
  }, [entities, tasks]);

  const assets = useMemo(
    () => entities.filter(entity => entity.template === "ASSET"),
    [entities]
  );
  const visibleEntities = useMemo(() => {
    const query = filter.toLowerCase();
    return entities.filter(entity =>
      !query ||
      entity.entity_id.toLowerCase().includes(query) ||
      nameOf(entity).toLowerCase().includes(query) ||
      entity.template.toLowerCase().includes(query)
    );
  }, [entities, filter]);

  const createTask = async (payload: any) => {
    const response = await fetch(`${API}/api/v1/tasks`, {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify(payload)
    });
    if (!response.ok) {
      alert(await response.text());
      return;
    }
    const created: Task = await response.json();
    setTasks(previous =>
      previous.some(task => task.task_id === created.task_id)
        ? previous
        : [...previous, created]
    );
    setContextPoint(null);
  };

  const navigateToContext = async () => {
    if (!contextPoint) return;
    await createTask({
      description:"Navigate to operator-selected point",
      specification:{
        type:"opengrid.tasks.v1.Navigate",
        objective:{
          type:"POINT",
          position:{latitude:contextPoint.lat,longitude:contextPoint.lon}
        },
        parameters:{speed_mps:3,arrival_radius_m:20}
      },
      assigned_agent_id:selectedAssetId,
      created_by:"operator-ui"
    });
  };

  const investigateSelected = async () => {
    if (!selected || selected.template !== "TRACK") return;
    await createTask({
      description:`Investigate ${nameOf(selected)}`,
      specification:{
        type:"opengrid.tasks.v1.Investigate",
        objective:{type:"ENTITY",entity_id:selected.entity_id},
        parameters:{speed_mps:3,standoff_m:50}
      },
      assigned_agent_id:selectedAssetId,
      created_by:"operator-ui"
    });
  };

  return (
    <div className="shell">
      <header>
        <div className="brand"><span>△</span> OPENGRID</div>
        <div className={connected ? "connection online" : "connection"}>
          <i/>{connected ? "LIVE" : "RECONNECTING"}
        </div>
      </header>

      <aside className="left">
        <div className="panelTitle">WORLD</div>
        <input
          value={filter}
          onChange={event => setFilter(event.target.value)}
          placeholder="Search entities"
        />
        <div className="entityList">
          {visibleEntities.map(entity => (
            <button
              key={entity.entity_id}
              className={`entityRow ${selected?.entity_id === entity.entity_id ? "selected" : ""}`}
              onClick={() => {
                setSelected(entity);
                if (entity.template === "ASSET") setSelectedAssetId(entity.entity_id);
              }}
            >
              <span className={`entityGlyph ${entity.template.toLowerCase()} ${isFused(entity) ? "fused" : ""}`}/>
              <span>
                <strong>{nameOf(entity)}</strong>
                <small>
                  {entity.components?.ontology?.platform_type || entity.template}
                  {isFused(entity) ? " · FUSED" : ""} · rev {entity.revision}
                </small>
              </span>
            </button>
          ))}
        </div>

        <div className="panelTitle tasksTitle">TASK QUEUES</div>
        <div className="taskList">
          {tasks.map(task => (
            <div className="taskRow" key={task.task_id}>
              <div>
                <strong>#{task.queue_position} {task.specification?.type?.split(".").pop()}</strong>
                <small>{task.assigned_agent_id}</small>
              </div>
              <span className={task.status}>{Math.round((task.progress || 0)*100)}%</span>
              <div className="progress"><i style={{width:`${(task.progress || 0)*100}%`}}/></div>
              <small>{task.status_message || task.status}</small>
            </div>
          ))}
        </div>
      </aside>

      <main ref={mapContainer}>
        {contextPoint && (
          <div className="contextMenu">
            <strong>Send asset here</strong>
            <select value={selectedAssetId} onChange={event => setSelectedAssetId(event.target.value)}>
              {assets.map(asset => <option key={asset.entity_id} value={asset.entity_id}>{nameOf(asset)}</option>)}
            </select>
            <button onClick={navigateToContext}>Queue Navigate</button>
            <button className="quiet" onClick={() => setContextPoint(null)}>Cancel</button>
          </div>
        )}
      </main>

      <aside className="right">
        {!selected ? (
          <div className="empty"><div>⌖</div>Select an entity</div>
        ) : (
          <>
            <div className="panelTitle">ENTITY</div>
            <h2>{nameOf(selected)}</h2>
            <div className="tags">
              <span>{selected.template}</span>
              {selected.components?.ontology?.platform_type && <span>{selected.components.ontology.platform_type}</span>}
              {isFused(selected) && <span>FUSED</span>}
            </div>

            {selected.template === "TRACK" && (
              <section>
                <h3>Tasking</h3>
                <select value={selectedAssetId} onChange={event => setSelectedAssetId(event.target.value)}>
                  {assets.map(asset => <option key={asset.entity_id} value={asset.entity_id}>{nameOf(asset)}</option>)}
                </select>
                <button className="primary" onClick={investigateSelected}>Investigate with selected asset</button>
              </section>
            )}

            <section>
              <h3>Identity</h3>
              <dl>
                <dt>ID</dt><dd>{selected.entity_id}</dd>
                <dt>Revision</dt><dd>{selected.revision}</dd>
                <dt>Source</dt><dd>{selected.components?.provenance?.source_system || "—"}</dd>
              </dl>
            </section>

            <section>
              <h3>Location</h3>
              <dl>
                <dt>Latitude</dt><dd>{selected.components?.location?.latitude?.toFixed?.(6) || "—"}</dd>
                <dt>Longitude</dt><dd>{selected.components?.location?.longitude?.toFixed?.(6) || "—"}</dd>
                <dt>Heading</dt><dd>{selected.components?.location?.heading_degrees ?? "—"}°</dd>
                <dt>Speed</dt><dd>{selected.components?.location?.speed_mps ?? "—"} m/s</dd>
              </dl>
            </section>

            {selected.template === "ASSET" && (
              <>
                <section>
                  <h3>Capabilities available now</h3>
                  <div className="chips">
                    {(selected.components?.capabilities?.available || []).map((capability:any) =>
                      <span key={capability.name}>{capability.name}</span>
                    )}
                  </div>
                </section>
                <section>
                  <h3>Limits and resources</h3>
                  <pre>{JSON.stringify({
                    limits:selected.components?.limits,
                    resources:selected.components?.resources,
                    equipment:selected.components?.equipment
                  }, null, 2)}</pre>
                </section>
              </>
            )}

            {isFused(selected) && (
              <section className="fusionBox">
                <h3>Fusion</h3>
                <dl>
                  <dt>Confidence</dt><dd>{selected.components?.provenance?.confidence}</dd>
                  <dt>Separation</dt><dd>{selected.components?.fusion?.separation_m} m</dd>
                </dl>
                {(selected.components?.relationships?.derived_from || []).map((id:string) =>
                  <code key={id}>{id}</code>
                )}
              </section>
            )}

            <section>
              <h3>Components</h3>
              <pre>{JSON.stringify(selected.components, null, 2)}</pre>
            </section>
          </>
        )}
      </aside>
    </div>
  );
}
