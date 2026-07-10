import hashlib,json
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings

def loc(c):
    x=c.get('location') or {}; a=x.get('latitude'); o=x.get('longitude')
    return (float(a),float(o)) if a is not None and o is not None else None

def source(c): return str((c.get('provenance') or {}).get('source_system') or 'unknown')
def fused_id(ids): return 'fused-'+hashlib.sha256('|'.join(sorted(ids)).encode()).hexdigest()[:16]

async def correlate_track(db:AsyncSession,entity_id:str,components:dict):
    p=loc(components)
    if not p: return None
    lat,lon=p; src=source(components)
    r=await db.execute(text("""
      SELECT entity_id,components,ST_Distance(geom::geography,ST_SetSRID(ST_Point(:lon,:lat),4326)::geography) distance_m
      FROM entities_current WHERE is_live=TRUE AND template='TRACK' AND entity_id<>:eid
      AND updated_at>NOW()-(:age||' seconds')::interval
      AND COALESCE(components->'provenance'->>'source_system','unknown')<>:src
      AND geom IS NOT NULL AND ST_DWithin(geom::geography,ST_SetSRID(ST_Point(:lon,:lat),4326)::geography,:gate)
      ORDER BY distance_m LIMIT 1
    """),{'lat':lat,'lon':lon,'eid':entity_id,'src':src,'age':settings.fusion_max_age_s,'gate':settings.fusion_gate_m})
    c=r.mappings().first()
    if not c: return None
    op=loc(c['components'])
    if not op: return None
    ids=sorted([entity_id,c['entity_id']]); fid=fused_id(ids); d=float(c['distance_m']); score=max(0,1-d/settings.fusion_gate_m)
    flat=(lat+op[0])/2; flon=(lon+op[1])/2
    fc={'aliases':{'name':f'Fused track {fid[-6:]}'},'ontology':{'template':'FUSED_TRACK','specific_type':'CORRELATED_CONTACT'},'location':{'latitude':flat,'longitude':flon},'mil_view':{'disposition':'UNKNOWN'},'provenance':{'source_system':'commongrid-fusion','algorithm':'nearest-neighbor-v0','confidence':round(score,3)},'relationships':{'derived_from':ids},'fusion':{'association_score':round(score,3),'separation_m':round(d,2),'gate_m':settings.fusion_gate_m}}
    await db.execute(text("""
      INSERT INTO entities_current(entity_id,revision,is_live,template,components,geom,source_update_time)
      VALUES(:id,1,TRUE,'FUSED_TRACK',CAST(:c AS JSONB),ST_SetSRID(ST_Point(:lon,:lat),4326),NOW())
      ON CONFLICT(entity_id) DO UPDATE SET revision=entities_current.revision+1,components=EXCLUDED.components,geom=EXCLUDED.geom,updated_at=NOW(),source_update_time=NOW()
    """),{'id':fid,'c':json.dumps(fc),'lat':flat,'lon':flon})
    await db.execute(text("""
      INSERT INTO fusion_associations(fused_entity_id,source_entity_ids,algorithm,score,details)
      VALUES(:id,CAST(:s AS JSONB),'nearest-neighbor-v0',:score,CAST(:d AS JSONB))
      ON CONFLICT(fused_entity_id) DO UPDATE SET source_entity_ids=EXCLUDED.source_entity_ids,score=EXCLUDED.score,details=EXCLUDED.details,updated_at=NOW()
    """),{'id':fid,'s':json.dumps(ids),'score':score,'d':json.dumps({'distance_m':d})})
    return {'fused_entity_id':fid,'source_entity_ids':ids,'score':score}
