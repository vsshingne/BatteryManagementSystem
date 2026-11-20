import asyncio, csv, io, secrets
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect, Header
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from .config import Settings
from .gateway import Gateway, BATTERY_IDS
from .models import Alert, IngestPayload, Measurement

def create_app(settings: Settings|None=None,start_tasks=True):
    settings=settings or Settings()
    @asynccontextmanager
    async def lifespan(app):
        g=Gateway(settings); app.state.gateway=g
        tasks=[asyncio.create_task(g.monitor())]
        if settings.mode=='demo' and start_tasks: tasks.append(asyncio.create_task(g.produce()))
        try: yield
        finally:
            for task in tasks: task.cancel()
            await asyncio.gather(*tasks,return_exceptions=True); g.close()
    app=FastAPI(title='Energy Supervisory Unit',version='2.0.0',lifespan=lifespan)
    @app.exception_handler(RequestValidationError)
    async def validation_error(request:Request,exc:RequestValidationError):
        if request.url.path=='/api/ingest' and hasattr(request.app.state,'gateway'):
            request.app.state.gateway.error('Rejected invalid ESP32 payload')
        return JSONResponse(status_code=422,content=jsonable_encoder({'detail':exc.errors()}))
    def gw(request): return request.app.state.gateway
    @app.get('/api/health')
    @app.get('/api/system')
    async def system(request:Request): return gw(request).status()
    @app.get('/api/batteries',response_model=dict[str,Measurement|None])
    async def batteries(request:Request): return gw(request).latest
    @app.get('/api/latest',response_model=Measurement|None)
    async def latest(request:Request,battery_id:Literal['BATTERY_1','BATTERY_2']='BATTERY_1'): return gw(request).latest[battery_id]
    def norm(dt):
        if dt is None:return None
        if dt.tzinfo is None: raise HTTPException(422,'Timestamps must include a timezone.')
        return dt.astimezone(timezone.utc).isoformat(timespec='milliseconds')
    def rows(request,source,battery_id,start,end,limit):
        a,b=norm(start),norm(end)
        if a and b and a>b: raise HTTPException(422,'start must be before end')
        return gw(request).db.history(source or settings.mode,a,b,limit,battery_id)
    @app.get('/api/history',response_model=list[Measurement])
    async def history(request:Request,source:Literal['demo','live']|None=None,battery_id:Literal['BATTERY_1','BATTERY_2']='BATTERY_1',start:datetime|None=None,end:datetime|None=None,limit:int=Query(1000,ge=1,le=10000)):
        return rows(request,source,battery_id,start,end,limit)
    @app.get('/api/export')
    async def export(request:Request,source:Literal['demo','live']|None=None,battery_id:Literal['BATTERY_1','BATTERY_2']='BATTERY_1',start:datetime|None=None,end:datetime|None=None,limit:int=Query(10000,ge=1,le=10000)):
        result=rows(request,source,battery_id,start,end,limit); out=io.StringIO(newline='')
        writer=csv.DictWriter(out,fieldnames=list(Measurement.model_fields)); writer.writeheader(); writer.writerows(r.model_dump() for r in result)
        return Response(out.getvalue(),media_type='text/csv',headers={'Content-Disposition':f'attachment; filename="{battery_id.lower()}-{source or settings.mode}.csv"'})
    @app.get('/api/alerts',response_model=list[Alert])
    async def alerts(request:Request,battery_id:Literal['BATTERY_1','BATTERY_2']|None=None,limit:int=Query(500,ge=1,le=500)):
        return gw(request).events.alert_history(settings.mode,limit,battery_id)
    @app.post('/api/alerts/{alert_id}/acknowledge')
    async def acknowledge(request:Request,alert_id:int):
        if not gw(request).events.acknowledge(alert_id,settings.mode): raise HTTPException(404,'Alert not found')
        return {'acknowledged':True}
    @app.post('/api/ingest',status_code=202)
    async def ingest(request:Request,payload:IngestPayload,authorization:str|None=Header(default=None)):
        if settings.mode!='live': raise HTTPException(409,'ESP32 ingestion is disabled in demo mode; set MODE=live.')
        if settings.ingest_token and not secrets.compare_digest(authorization or '',f'Bearer {settings.ingest_token}'):
            raise HTTPException(401,'Invalid ingestion credentials')
        try: accepted=await gw(request).accept(payload.device_id,payload.batteries,payload.timestamp)
        except Exception as exc:
            gw(request).error(type(exc).__name__); raise HTTPException(503,'Reading could not be stored') from exc
        return {'accepted':len(accepted),'device_id':payload.device_id,'received_at':accepted[0].timestamp}
    @app.websocket('/ws/battery')
    async def socket(ws:WebSocket):
        origin=ws.headers.get('origin')
        if origin and origin.rstrip('/') not in {f"http://{ws.headers.get('host')}",f"https://{ws.headers.get('host')}"}:
            await ws.close(code=1008); return
        await ws.accept(); g=ws.app.state.gateway
        try:
            await ws.send_json({'type':'status','data':g.status()})
            for reading in g.latest.values():
                if reading: await ws.send_json({'type':'measurement','data':reading.model_dump()})
            g.manager.clients.add(ws)
            while True: await ws.receive_text()
        except WebSocketDisconnect: pass
        finally:g.manager.clients.discard(ws)
    dist=Path(settings.frontend_dist)
    if (dist/'assets').is_dir():app.mount('/assets',StaticFiles(directory=dist/'assets'),name='assets')
    @app.get('/')
    async def index():
        if not (dist/'index.html').is_file():raise HTTPException(503,'Build frontend first: cd frontend && npm run build')
        return FileResponse(dist/'index.html')
    return app

app=create_app()
