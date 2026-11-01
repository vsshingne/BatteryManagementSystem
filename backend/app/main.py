import asyncio
import csv
import io
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from .config import Settings
from .gateway import Gateway
from .models import Alert, Measurement


def create_app(settings: Settings | None = None, start_tasks: bool = True):
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app):
        gateway = Gateway(settings)
        app.state.gateway = gateway
        tasks = [asyncio.create_task(gateway.produce()), asyncio.create_task(gateway.monitor())] if start_tasks else []
        try:
            yield
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            gateway.close()

    app = FastAPI(title='Energy Supervisory Unit', version='1.0.0', lifespan=lifespan)

    def gateway(request: Request) -> Gateway:
        return request.app.state.gateway

    @app.get('/api/health')
    @app.get('/api/system')
    async def health(request: Request):
        return gateway(request).status()

    @app.get('/api/latest', response_model=Measurement | None)
    async def latest(request: Request):
        return gateway(request).latest

    def normalize(value: datetime | None):
        if value is None:
            return None
        if value.tzinfo is None:
            raise HTTPException(422, 'Timestamps must include a timezone (e.g. Z or +05:30).')
        return value.astimezone(timezone.utc).isoformat(timespec='milliseconds')

    def query_history(request, source, start, end, limit):
        first, last = normalize(start), normalize(end)
        if first and last and first > last:
            raise HTTPException(422, 'start must be before end')
        return gateway(request).db.history(source or settings.mode, first, last, limit)

    @app.get('/api/history', response_model=list[Measurement])
    async def history(request: Request, source: Literal['demo', 'live'] | None = None, start: datetime | None = None, end: datetime | None = None, limit: int = Query(1000, ge=1, le=10000)):
        return query_history(request, source, start, end, limit)

    @app.get('/api/export')
    async def export(request: Request, source: Literal['demo', 'live'] | None = None, start: datetime | None = None, end: datetime | None = None, limit: int = Query(10000, ge=1, le=10000)):
        rows = query_history(request, source, start, end, limit)
        output = io.StringIO(newline='')
        writer = csv.DictWriter(output, fieldnames=list(Measurement.model_fields))
        writer.writeheader()
        writer.writerows(r.model_dump() for r in rows)
        return Response(output.getvalue(), media_type='text/csv', headers={'Content-Disposition': f'attachment; filename="esu-{source or settings.mode}.csv"'})

    @app.get('/api/alerts', response_model=list[Alert])
    async def alerts(request: Request, limit: int = Query(500, ge=1, le=500)):
        return gateway(request).events.alert_history(settings.mode, limit)

    @app.post('/api/alerts/{alert_id}/acknowledge')
    async def acknowledge(request: Request, alert_id: int):
        # This endpoint writes only a notification flag in SQLite.
        if not gateway(request).events.acknowledge(alert_id, settings.mode):
            raise HTTPException(404, 'Alert not found')
        return {'acknowledged': True}

    @app.websocket('/ws/battery')
    async def battery_socket(websocket: WebSocket):
        # Same-origin browser access. Non-browser clients may omit Origin.
        origin = websocket.headers.get('origin')
        if origin and origin.rstrip('/') not in {f'http://{websocket.headers.get("host")}', f'https://{websocket.headers.get("host")}'}:
            await websocket.close(code=1008)
            return
        await websocket.accept()
        g = websocket.app.state.gateway
        try:
            await websocket.send_json({'type': 'status', 'data': g.status()})
            if g.latest:
                await websocket.send_json({'type': 'measurement', 'data': g.latest.model_dump()})
            g.manager.clients.add(websocket)
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            g.manager.clients.discard(websocket)

    dist = Path(settings.frontend_dist)
    if (dist / 'assets').is_dir():
        app.mount('/assets', StaticFiles(directory=dist / 'assets'), name='assets')

    @app.get('/')
    async def index():
        if not (dist / 'index.html').is_file():
            raise HTTPException(503, 'Build frontend first: cd frontend && npm run build')
        return FileResponse(dist / 'index.html')

    return app


app = create_app()
