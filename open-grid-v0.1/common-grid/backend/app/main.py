import json
from contextlib import asynccontextmanager
from uuid import UUID
from fastapi import FastAPI,Depends,HTTPException,Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.db import get_db
from app.events import event_bus
from app.fusion import correlate_track
from app.models import EntityUpsert,TaskCreate,TaskStatusUpdate

@asynccontextmanager
async def lifespan(app):
    await event_bus.connect(); yield; await event_bus.close()
app=FastAPI(title='CommonGrid API',version='0.1.0',lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=settings.cors_origin_list,allow_credentials=True,allow_methods=['*'],allow_headers=['*'])
@app.get('/health')
async def health(): return {'status':'ok'}
def template(c): return str((c.get('ontology') or {}).get('template') or 'UNKNOWN').upper()
def point(c):
    x=c.get('location') or {}; a=x.get('latitude'); o=x.get('longitude')
    return (float(a),float(o)) if a is not None and o is not None else None

@app.put('/api/v1/entities/{entity_id}')
async def upsert(entity_id:str,body:EntityUpsert,db:AsyncSession=Depends(get_db)):
    if entity_id!=body.entity_id: raise HTTPException(400,'Path and body entity IDs differ')
    t=template(body.components); p=point(body.components)
    r=await db.execute(text("""
      INSERT INTO entities_current(entity_id,revision,is_live,template,expiry_time,components,geom,source_update_time)
      VALUES(:id,1,:live,:t,:exp,CAST(:c AS JSONB),CASE WHEN :hp THEN ST_SetSRID(ST_Point(:lon,:lat),4326) ELSE NULL END,NOW())
      ON CONFLICT(entity_id) DO UPDATE SET revision=entities_current.revision+1,is_live=EXCLUDED.is_live,template=EXCLUDED.template,expiry_time=EXCLUDED.expiry_time,components=EXCLUDED.components,geom=EXCLUDED.geom,updated_at=NOW(),source_update_time=NOW()
      RETURNING entity_id,revision,is_live,template,expiry_time,components,created_at,updated_at
    """),{'id':entity_id,'live':body.is_live,'t':t,'exp':body.expiry_time,'c':json.dumps(body.components),'hp':p is not None,'lat':p[0] if p else 0,'lon':p[1] if p else 0})
    e=dict(r.mappings().one())
    await db.execute(text("""INSERT INTO entity_events(entity_id,revision,event_type,changed_components,payload,source_time) VALUES(:id,:rev,:typ,:chg,CAST(:p AS JSONB),NOW())"""),{'id':entity_id,'rev':e['revision'],'typ':'UPSERT' if body.is_live else 'DELETE','chg':list(body.components.keys()),'p':json.dumps(body.model_dump(mode='json'))})
    fr=await correlate_track(db,entity_id,body.components) if body.is_live and t=='TRACK' else None
    await db.commit(); await event_bus.publish(f'entities.{entity_id}.updated',e)
    if fr: await event_bus.publish('fusion.association.updated',fr)
    return {'entity':e,'fusion':fr}

@app.get('/api/v1/entities')
async def entities(template_filter:str|None=Query(None,alias='template'),live_only:bool=True,limit:int=Query(500,ge=1,le=5000),db:AsyncSession=Depends(get_db)):
    clauses=['1=1']; params={'limit':limit}
    if template_filter: clauses.append('template=:t'); params['t']=template_filter.upper()
    if live_only: clauses.append('is_live=TRUE')
    r=await db.execute(text(f"SELECT entity_id,revision,is_live,template,expiry_time,components,created_at,updated_at FROM entities_current WHERE {' AND '.join(clauses)} ORDER BY updated_at DESC LIMIT :limit"),params)
    return [dict(x) for x in r.mappings()]

@app.get('/api/v1/entities/{entity_id}')
async def entity(entity_id:str,db:AsyncSession=Depends(get_db)):
    r=await db.execute(text('SELECT entity_id,revision,is_live,template,expiry_time,components,created_at,updated_at FROM entities_current WHERE entity_id=:id'),{'id':entity_id}); e=r.mappings().first()
    if not e: raise HTTPException(404,'Entity not found')
    return dict(e)

@app.get('/api/v1/entities/{entity_id}/events')
async def history(entity_id:str,db:AsyncSession=Depends(get_db)):
    r=await db.execute(text('SELECT * FROM entity_events WHERE entity_id=:id ORDER BY revision DESC LIMIT 1000'),{'id':entity_id}); return [dict(x) for x in r.mappings()]

@app.post('/api/v1/tasks')
async def create_task(body:TaskCreate,db:AsyncSession=Depends(get_db)):
    r=await db.execute(text("""INSERT INTO tasks(task_type,description,assigned_agents,objective_entity_id,parameters,state,created_by) VALUES(:t,:d,CAST(:a AS JSONB),:o,CAST(:p AS JSONB),'SENT',:b) RETURNING *"""),{'t':body.task_type,'d':body.description,'a':json.dumps(body.assigned_agents),'o':body.objective_entity_id,'p':json.dumps(body.parameters),'b':body.created_by}); task=dict(r.mappings().one()); await db.commit(); await event_bus.publish(f"tasks.{task['task_id']}.created",task); return task
@app.get('/api/v1/tasks')
async def tasks(db:AsyncSession=Depends(get_db)):
    r=await db.execute(text('SELECT * FROM tasks ORDER BY updated_at DESC LIMIT 1000')); return [dict(x) for x in r.mappings()]
@app.post('/api/v1/tasks/{task_id}/status')
async def task_status(task_id:UUID,body:TaskStatusUpdate,db:AsyncSession=Depends(get_db)):
    r=await db.execute(text('UPDATE tasks SET state=:s,progress=:p,status_message=:m,updated_at=NOW() WHERE task_id=:id RETURNING *'),{'id':task_id,'s':body.state.value,'p':body.progress,'m':body.message}); task=r.mappings().first()
    if not task: raise HTTPException(404,'Task not found')
    task=dict(task); await db.commit(); await event_bus.publish(f'tasks.{task_id}.status',task); return task
@app.get('/api/v1/fusion/associations')
async def associations(db:AsyncSession=Depends(get_db)):
    r=await db.execute(text('SELECT * FROM fusion_associations ORDER BY updated_at DESC LIMIT 1000')); return [dict(x) for x in r.mappings()]
