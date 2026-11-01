"""Verify real HTTP/static/SQLite/WebSocket integration, then stop our server."""
import asyncio
import json
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time

import httpx
import uvicorn
from websockets.asyncio.client import connect

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

from app.config import Settings
from app.main import create_app


async def stream(port):
    async with connect(f'ws://127.0.0.1:{port}/ws/battery', origin=f'http://127.0.0.1:{port}') as ws:
        readings = []
        while len(readings) < 2:
            event = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            if event['type'] == 'measurement':
                readings.append(event['data'])
        assert readings[0]['timestamp'] != readings[1]['timestamp']
        assert all(r['source'] == 'demo' for r in readings)
        print('PASS: real WebSocket delivers changing, labelled demo measurements')


def main():
    assert (ROOT / 'frontend' / 'dist' / 'index.html').exists(), 'Run npm run build first'
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix='esu-smoke-') as temp:
        settings = Settings(_env_file=None, mode='demo', persist_demo=True, demo_interval_seconds=.1, database_path=str(Path(temp) / 'smoke.sqlite3'))
        server = uvicorn.Server(uvicorn.Config(create_app(settings), host='127.0.0.1', port=port, log_level='warning'))
        worker = threading.Thread(target=server.run, daemon=True)
        worker.start()
        try:
            with httpx.Client(base_url=f'http://127.0.0.1:{port}', timeout=3) as client:
                for _ in range(80):
                    try:
                        if client.get('/api/health').status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    if not worker.is_alive():
                        raise RuntimeError('Server exited before ready')
                    time.sleep(.1)
                else:
                    raise RuntimeError('Server readiness timeout')
                index = client.get('/')
                assert index.status_code == 200 and 'ESU' in index.text
                import re
                for asset in re.findall(r'(?:src|href)="(/assets/[^\"]+)"', index.text):
                    assert client.get(asset).status_code == 200
                print('PASS: compiled frontend and assets served by FastAPI')
                asyncio.run(stream(port))
                history = client.get('/api/history?source=demo').json()
                assert len(history) >= 2 and all(r['source'] == 'demo' for r in history)
                assert client.get('/api/history?source=live').json() == []
                csv = client.get('/api/export?source=demo')
                assert csv.status_code == 200 and 'soc' in csv.text and 'demo' in csv.text
                print('PASS: SQLite history, source isolation and CSV export')
        finally:
            server.should_exit = True
            worker.join(timeout=10)
            assert not worker.is_alive(), 'Server did not stop cleanly'


if __name__ == '__main__':
    main()
