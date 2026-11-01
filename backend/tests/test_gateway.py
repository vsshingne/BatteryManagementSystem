import asyncio
import csv
import io
import json
import time

import pytest
import serial
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.main import create_app
from app.models import Packet
from app.serial_reader import LineFramer, parse_packet, read_serial
from app.simulator import Simulator

PAYLOAD = dict(voltage=3.92, current=.84, temperature=31.0, soc=78.0, battery_status='NORMAL', charging=False)


def settings(tmp_path, **kw):
    return Settings(_env_file=None, database_path=str(tmp_path / 'test.sqlite3'), **kw)


def inject(client, **kw):
    client.portal.call(client.app.state.gateway.accept, Packet(**(PAYLOAD | kw)))


@pytest.mark.parametrize('changes', [dict(soc=101), dict(soc=-1), dict(voltage='3.92'), dict(charging='false'), dict(current=True), dict(temperature=float('nan')), dict(current=float('inf')), dict(battery_status='MADE_UP'), dict(unexpected=123), dict(operating_mode='Charging', charging=False)])
def test_reject_bad_packets(changes):
    with pytest.raises((ValidationError, ValueError)):
        parse_packet(json.dumps(PAYLOAD | changes).encode())


@pytest.mark.parametrize('line', [b'{oops}', b'\xff', b'{}', b'[]', b'null'])
def test_reject_malformed(line):
    with pytest.raises((ValidationError, ValueError, UnicodeError)):
        parse_packet(line)


def test_authoritative_soc_and_optional_fields():
    packet = parse_packet(json.dumps(PAYLOAD).encode())
    assert packet.soc == 78
    assert packet.runtime_minutes is None
    assert packet.operating_mode is None
    with pytest.raises(ValueError):
        parse_packet(b'{}', 'unsupported')


def test_fragmentation_and_oversize_recovery():
    framer = LineFramer(8)
    assert list(framer.feed(b'{"a":')) == []
    assert list(framer.feed(b'1}\r\n')) == [b'{"a":1}\r']
    assert list(framer.feed(b'x' * 100)) == [None]
    assert len(framer.buffer) == 0
    assert list(framer.feed(b'\n{}\n')) == [b'{}']


def test_demo_ws_updates_not_persisted(tmp_path):
    app = create_app(settings(tmp_path, demo_interval_seconds=.05))
    with TestClient(app) as client:
        with client.websocket_connect('/ws/battery') as ws:
            assert ws.receive_json()['type'] == 'status'
            samples = []
            while len(samples) < 2:
                message = ws.receive_json()
                if message['type'] == 'measurement':
                    samples.append(message['data'])
            assert all(s['source'] == 'demo' for s in samples)
            assert samples[0]['timestamp'] != samples[1]['timestamp']
        assert client.get('/api/health').json()['connected'] is True
        assert client.get('/api/system').json()['serial_open'] is False
        assert client.get('/api/latest').json()['source'] == 'demo'
        assert client.get('/api/history').json() == []
        inject(client, battery_status='SENSOR_ERROR')
        assert client.get('/api/alerts').json()[0]['source'] == 'demo'
        assert app.state.gateway.db.alert_history('demo') == []


def test_history_filters_csv_and_source_isolation(tmp_path):
    config = settings(tmp_path, mode='demo', persist_demo=True)
    with TestClient(create_app(config, start_tasks=False)) as client:
        inject(client, soc=42.7)
        sample = client.get('/api/latest').json()
        assert sample['soc'] == 42.7
        assert sample['operating_mode'] == 'Discharging'
        assert client.get('/api/history', params={'start':sample['timestamp'], 'end':sample['timestamp']}).json()[0]['soc'] == 42.7
        assert client.get('/api/history?source=live').json() == []
        assert client.get('/api/history?limit=0').status_code == 422
        assert client.get('/api/history?source=bogus').status_code == 422
        assert client.get('/api/history?start=2026-01-01T00:00:00').status_code == 422
        assert client.get('/api/history?start=2030-01-01T00:00:00Z&end=2020-01-01T00:00:00Z').status_code == 422
        result = client.get('/api/export?source=demo')
        assert result.headers['content-type'].startswith('text/csv')
        assert list(csv.DictReader(io.StringIO(result.text)))[0]['soc'] == '42.7'
    with TestClient(create_app(settings(tmp_path, mode='live'), start_tasks=False)) as client:
        assert client.get('/api/latest').json() is None
        inject(client, soc=23.45)
        assert len(client.get('/api/history?source=live').json()) == 1
        assert client.get('/api/history?source=demo').json()[0]['soc'] == 42.7
    with TestClient(create_app(settings(tmp_path, mode='live'), start_tasks=False)) as client:
        assert client.get('/api/latest').json()['soc'] == 23.45
        assert client.get('/api/health').json()['stale'] is True


def test_alert_lifecycle_ack_does_not_change_protection(tmp_path):
    with TestClient(create_app(settings(tmp_path), start_tasks=False)) as client:
        inject(client, battery_status='OVERVOLTAGE')
        inject(client, battery_status='OVERVOLTAGE')
        alerts = client.get('/api/alerts').json()
        assert len(alerts) == 1  # repeated fault is one event
        alert_id = alerts[0]['id']
        assert client.post(f'/api/alerts/{alert_id}/acknowledge').json()['acknowledged']
        assert client.get('/api/latest').json()['battery_status'] == 'OVERVOLTAGE'
        assert client.get('/api/alerts').json()[0]['resolved_at'] is None
        inject(client)
        assert client.get('/api/alerts').json()[0]['resolved_at'] is not None
        assert client.post('/api/alerts/999/acknowledge').status_code == 404


def test_stale_and_thresholds_are_explicit(tmp_path):
    with TestClient(create_app(settings(tmp_path, mode='live', voltage_high=3.9), start_tasks=False)) as client:
        g = client.app.state.gateway
        g.serial_open = True
        inject(client)
        assert client.get('/api/health').json()['connected']
        assert client.get('/api/alerts').json()[0]['code'] == 'THRESHOLD_OVERVOLTAGE'
        g.last_valid_monotonic = time.monotonic() - 10
        g.started = time.monotonic() - 10
        client.portal.call(g.sync_alerts)
        assert client.get('/api/health').json()['stale']
        assert any(a['code'] == 'GATEWAY_COMMUNICATION_FAILURE' for a in client.get('/api/alerts').json())
        assert client.get('/api/latest').json()['soc'] == PAYLOAD['soc']
        inject(client)
        comm = next(a for a in client.get('/api/alerts').json() if a['code'] == 'GATEWAY_COMMUNICATION_FAILURE')
        assert comm['resolved_at'] is not None


def test_restart_does_not_clear_unconfirmed_hardware_fault(tmp_path):
    config = settings(tmp_path, mode='live')
    with TestClient(create_app(config, start_tasks=False)) as client:
        inject(client, battery_status='SENSOR_ERROR')
    with TestClient(create_app(config, start_tasks=False)) as client:
        client.portal.call(client.app.state.gateway.sync_alerts)
        assert client.get('/api/alerts').json()[0]['resolved_at'] is None
        inject(client)
        assert client.get('/api/alerts').json()[0]['resolved_at'] is not None


def test_no_live_fallback_when_serial_missing(tmp_path, monkeypatch):
    def missing(**kwargs):
        raise serial.SerialException('mock device unavailable')
    # default function argument is patched via the gateway's imported reader
    from app import gateway
    original = read_serial
    async def reader(s, packet, port, error):
        await original(s, packet, port, error, serial_factory=missing)
    monkeypatch.setattr(gateway, 'read_serial', reader)
    with TestClient(create_app(settings(tmp_path, mode='live'))) as client:
        with client.websocket_connect('/ws/battery') as ws:
            status = ws.receive_json()['data']
            assert status['mode'] == 'live'
            assert not status['connected']
        assert client.get('/api/latest').json() is None
        assert client.get('/api/history').json() == []


def test_mock_serial_reconnect_fragment_parse_and_recover(tmp_path):
    async def scenario():
        attempts, received, errors, states = [], [], [], []
        done = asyncio.Event()
        line = json.dumps(PAYLOAD).encode() + b'\n'
        class MockSerial:
            in_waiting = 1
            def __init__(self):
                self.chunks = iter([b'not-json\n', line[:12], line[12:]])
                self.closed = False
            def read(self, n):
                return next(self.chunks, b'')
            def close(self):
                self.closed = True
        mock = MockSerial()
        def factory(**kwargs):
            attempts.append(kwargs)
            if len(attempts) == 1:
                raise serial.SerialException('unplugged')
            return mock
        async def receive(packet):
            received.append(packet)
            done.set()
        task = asyncio.create_task(read_serial(settings(tmp_path, mode='live', serial_port='MOCK-UART', baud_rate=57600, reconnect_seconds=.01), receive, states.append, lambda message, rejected: errors.append((message, rejected)), serial_factory=factory))
        try:
            await asyncio.wait_for(done.wait(), timeout=3)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        assert len(received) == 1 and received[0].soc == 78
        assert len(errors) == 2
        assert errors[0][1] is False and errors[1][1] is True
        assert attempts[-1]['port'] == 'MOCK-UART' and attempts[-1]['baudrate'] == 57600
        assert True in states and states[-1] is False and mock.closed
    asyncio.run(scenario())


def test_simulation_deterministic_and_all_modes():
    a, b = Simulator(42), Simulator(42)
    samples = [a.next() for _ in range(240)]
    assert samples == [b.next() for _ in range(240)]
    assert {s.operating_mode for s in samples} == {'Charging', 'Discharging', 'Idle'}
    assert any(s.battery_status == 'OVERTEMPERATURE' for s in samples)


def test_static_build_and_api_not_swallowed(tmp_path):
    dist = tmp_path / 'dist'
    (dist / 'assets').mkdir(parents=True)
    (dist / 'index.html').write_text('<html>ESU</html>')
    (dist / 'assets' / 'app.js').write_text('console.log("ESU")')
    with TestClient(create_app(settings(tmp_path, frontend_dist=str(dist)), start_tasks=False)) as client:
        assert client.get('/').status_code == 200
        assert client.get('/assets/app.js').status_code == 200
        assert client.get('/api/unknown').status_code == 404
