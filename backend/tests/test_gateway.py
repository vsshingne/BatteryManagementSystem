import asyncio
from datetime import datetime,timezone
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app

def config(path,**kw): return Settings(_env_file=None,database_path=str(path/'telemetry.sqlite3'),**kw)

def payload(*batteries): return {'device_id':'ESP32_TEST','timestamp':datetime.now(timezone.utc).isoformat(),'batteries':list(batteries)}
def battery(bid,**kw): return {'battery_id':bid,'voltage':12.4,'current':1.5,'temperature':29.5,'soc':85,'battery_status':'NORMAL',**kw}

def test_dual_battery_ingest_history_isolation_and_migration(tmp_path):
    db=tmp_path/'telemetry.sqlite3'
    # Simulate the previous schema and verify the safe migration assigns old rows to battery 1.
    import sqlite3
    c=sqlite3.connect(db);c.execute('CREATE TABLE measurements(id INTEGER PRIMARY KEY,timestamp TEXT NOT NULL,source TEXT NOT NULL,voltage REAL,current REAL,temperature REAL,soc REAL,battery_status TEXT,charging INTEGER,operating_mode TEXT,runtime_minutes REAL)');c.execute("INSERT INTO measurements(timestamp,source,voltage,current,temperature,soc,battery_status,charging,operating_mode) VALUES('2025-01-01T00:00:00+00:00','live',12,0,25,50,'NORMAL',0,'Idle')");c.commit();c.close()
    with TestClient(create_app(config(tmp_path,mode='live'),start_tasks=False)) as client:
        assert client.get('/api/latest').json()['battery_id']=='BATTERY_1'
        r=client.post('/api/ingest',json=payload(battery('BATTERY_1'),battery('BATTERY_2',voltage=11.9,soc=72)))
        assert r.status_code==202 and r.json()['accepted']==2
        assert client.get('/api/batteries').json()['BATTERY_2']['soc']==72
        assert len(client.get('/api/history?battery_id=BATTERY_1').json())==2
        hist=client.get('/api/history?battery_id=BATTERY_2').json()
        assert len(hist)==1 and hist[0]['voltage']==11.9
        assert hist[0]['timestamp'].endswith('+00:00')

def test_validation_and_partial_battery_update(tmp_path):
    with TestClient(create_app(config(tmp_path,mode='live'),start_tasks=False)) as client:
        assert client.post('/api/ingest',json=payload(battery('BATTERY_1'),battery('BATTERY_1'))).status_code==422
        assert client.post('/api/ingest',json=payload(battery('BATTERY_1',soc=101))).status_code==422
        assert client.post('/api/ingest',json=payload(battery('BATTERY_1',unknown=5))).status_code==422
        assert client.post('/api/ingest',json=payload(battery('BATTERY_1'))).status_code==202
        status=client.get('/api/system').json()
        assert status['batteries']['BATTERY_1']['connected']
        assert not status['batteries']['BATTERY_2']['connected']
        assert status['esp32_connected']

def test_battery_alerts_are_separate_and_websocket_tagged(tmp_path):
    with TestClient(create_app(config(tmp_path,mode='live'),start_tasks=False)) as client:
        with client.websocket_connect('/ws/battery') as ws:
            assert ws.receive_json()['type']=='status'
            r=client.post('/api/ingest',json=payload(battery('BATTERY_1',battery_status='OVERVOLTAGE'),battery('BATTERY_2')))
            assert r.status_code==202
            seen={}
            while len(seen)<2:
                event=ws.receive_json()
                if event['type']=='measurement':seen[event['data']['battery_id']]=event['data']
            assert set(seen)=={'BATTERY_1','BATTERY_2'}
        assert len(client.get('/api/alerts?battery_id=BATTERY_1').json())==1
        assert client.get('/api/alerts?battery_id=BATTERY_2').json()==[]

def test_demo_never_accepts_hardware_and_separates_simulated_data(tmp_path):
    with TestClient(create_app(config(tmp_path,mode='demo',demo_interval_seconds=.05))) as client:
        assert client.post('/api/ingest',json=payload(battery('BATTERY_1'))).status_code==409
        data=client.get('/api/batteries').json()
        assert data['BATTERY_1']['source']=='demo' and data['BATTERY_2']['source']=='demo'
        assert client.get('/api/history?source=live&battery_id=BATTERY_1').json()==[]

def test_delayed_reading_is_stored_but_not_reported_as_live(tmp_path):
    with TestClient(create_app(config(tmp_path,mode='live',stale_after_seconds=2),start_tasks=False)) as client:
        delayed={'device_id':'ESP32_TEST','timestamp':'2020-01-01T00:00:00Z','batteries':[battery('BATTERY_1')]}
        assert client.post('/api/ingest',json=delayed).status_code==202
        assert client.get('/api/system').json()['esp32_connected']
        assert not client.get('/api/system').json()['batteries']['BATTERY_1']['connected']
        assert len(client.get('/api/history?battery_id=BATTERY_1').json())==1
