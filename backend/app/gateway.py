import asyncio
import platform
import socket
import time

from .database import Database
from .models import Measurement, Packet, utcnow
from .serial_reader import read_serial
from .simulator import Simulator
from .websocket_manager import WebSocketManager


class Gateway:
    def __init__(self, settings):
        self.settings = settings
        self.db = Database(settings.database_path)
        # Non-persisted demo readings AND alerts live only in memory.
        self.events = Database(':memory:') if settings.mode == 'demo' and not settings.persist_demo else self.db
        self.latest = self.db.latest(settings.mode) if settings.mode == 'live' or settings.persist_demo else None
        self.last_valid_monotonic = None
        self.serial_open = False
        self.rejected_packets = 0
        self.last_error = None
        self.manager = WebSocketManager()
        # Retain unresolved battery events across restart until a fresh packet
        # reports recovery; loss of telemetry is not evidence of recovery.
        self.battery_alerts: dict[str, tuple[str, str]] = {
            a.code: (a.severity, a.description)
            for a in self.events.alert_history(settings.mode)
            if a.resolved_at is None and a.code != 'GATEWAY_COMMUNICATION_FAILURE'
        }
        self.started = time.monotonic()

    @property
    def connected(self):
        return self.last_valid_monotonic is not None and time.monotonic() - self.last_valid_monotonic < self.settings.stale_after_seconds and (self.settings.mode == 'demo' or self.serial_open)

    def status(self):
        return dict(backend='ok', mode=self.settings.mode, connected=self.connected, stale=not self.connected, serial_open=self.serial_open, last_received=self.latest.timestamp if self.latest else None, serial_port=self.settings.serial_port, baud_rate=self.settings.baud_rate, protocol=self.settings.protocol, stale_after_seconds=self.settings.stale_after_seconds, hostname=socket.gethostname(), platform=platform.platform(), persist_demo=self.settings.persist_demo, rejected_packets=self.rejected_packets, last_error=self.last_error)

    def set_port(self, opened):
        self.serial_open = opened

    def error(self, message, rejected):
        self.last_error = message
        if rejected:
            self.rejected_packets += 1

    async def accept(self, packet: Packet):
        fields = packet.model_dump()
        fields['operating_mode'] = packet.operating_mode or ('Charging' if packet.charging else 'Idle' if packet.current == 0 else 'Discharging')
        reading = Measurement(**fields, timestamp=utcnow(), source=self.settings.mode)
        if self.settings.mode == 'live' or self.settings.persist_demo:
            self.db.store(reading)
        self.latest = reading
        self.last_valid_monotonic = time.monotonic()
        self.last_error = None
        active = {}
        if reading.battery_status != 'NORMAL':
            origin = 'Simulator' if reading.source == 'demo' else 'STM32'
            severity = 'warning' if reading.battery_status == 'WARNING' else 'critical'
            active[reading.battery_status] = (severity, f'{origin} reported {reading.battery_status.replace("_", " ").lower()}.')
        thresholds = [
            ('voltage', self.settings.voltage_high, lambda a,b: a > b, 'OVERVOLTAGE'),
            ('voltage', self.settings.voltage_low, lambda a,b: a < b, 'UNDERVOLTAGE'),
            ('current', self.settings.current_high, lambda a,b: abs(a) > b, 'OVERCURRENT'),
            ('temperature', self.settings.temperature_high, lambda a,b: a > b, 'OVERTEMPERATURE'),
        ]
        for field, threshold, test, code in thresholds:
            if threshold is not None and test(getattr(reading, field), threshold):
                active[f'THRESHOLD_{code}'] = ('warning', f'Configured gateway threshold: {field}={getattr(reading, field)}; limit={threshold}. Notification only.')
        self.battery_alerts = active
        self.sync_alerts()
        await self.manager.broadcast({'type': 'measurement', 'data': reading.model_dump()})

    def sync_alerts(self):
        active = dict(self.battery_alerts)
        if not self.connected and time.monotonic() - self.started >= self.settings.stale_after_seconds:
            active['GATEWAY_COMMUNICATION_FAILURE'] = ('critical', 'Gateway has no fresh valid telemetry. Battery condition and hardware protection are unconfirmed.')
        self.events.update_alerts(self.settings.mode, active)

    async def produce(self):
        if self.settings.mode == 'demo':
            simulator = Simulator(self.settings.demo_seed)
            while True:
                await self.accept(simulator.next())
                await asyncio.sleep(self.settings.demo_interval_seconds)
        else:
            await read_serial(self.settings, self.accept, self.set_port, self.error)

    async def monitor(self):
        while True:
            self.sync_alerts()
            await self.manager.broadcast({'type': 'status', 'data': self.status()})
            await asyncio.sleep(1)

    def close(self):
        if self.events is not self.db:
            self.events.close()
        self.db.close()
