import asyncio, platform, socket, time
from datetime import datetime, timezone
from datetime import timezone
from .database import Database
from .models import Measurement, BatteryPacket, utcnow
from .simulator import Simulator
from .websocket_manager import WebSocketManager

BATTERY_IDS = ('BATTERY_1','BATTERY_2')

class Gateway:
    def __init__(self, settings):
        self.settings=settings; self.db=Database(settings.database_path)
        self.events=Database(':memory:') if settings.mode=='demo' and not settings.persist_demo else self.db
        self.latest=self.db.latest_all(settings.mode) if settings.mode=='live' or settings.persist_demo else {bid:None for bid in BATTERY_IDS}
        self.last_valid={bid:None for bid in BATTERY_IDS}; self.last_device_time=None; self.device_id=None
        self.rejected_packets=0; self.last_error=None; self.manager=WebSocketManager(); self.started=time.monotonic()
        self.battery_alerts={bid:{} for bid in BATTERY_IDS}
        for bid in BATTERY_IDS:
            self.battery_alerts[bid]={a.code:(a.severity,a.description) for a in self.events.alert_history(settings.mode,battery_id=bid) if a.resolved_at is None and a.code!='GATEWAY_COMMUNICATION_FAILURE'}

    def connected(self, battery_id=None):
        now=time.monotonic()
        if battery_id: return self.last_valid[battery_id] is not None and now-self.last_valid[battery_id]<self.settings.stale_after_seconds
        return self.last_device_time is not None and now-self.last_device_time<self.settings.stale_after_seconds

    def status(self):
        now=time.monotonic()
        batteries={bid:{'connected':self.connected(bid),'stale':not self.connected(bid),'last_received':self.latest[bid].timestamp if self.latest.get(bid) else None} for bid in BATTERY_IDS}
        return dict(backend='ok',mode=self.settings.mode,device_id=self.device_id,esp32_connected=self.connected(),stale=not self.connected(),last_received=max((v['last_received'] for v in batteries.values() if v['last_received']),default=None),stale_after_seconds=self.settings.stale_after_seconds,hostname=socket.gethostname(),platform=platform.platform(),persist_demo=self.settings.persist_demo,rejected_packets=self.rejected_packets,last_error=self.last_error,batteries=batteries)

    def error(self, message): self.last_error=message; self.rejected_packets+=1

    async def accept(self, device_id, packets, timestamp=None):
        received=timestamp.astimezone(timezone.utc).isoformat(timespec='milliseconds') if timestamp else utcnow()
        sample_time=timestamp.astimezone(timezone.utc) if timestamp else datetime.now(timezone.utc)
        sample_fresh=abs((datetime.now(timezone.utc)-sample_time).total_seconds()) <= self.settings.stale_after_seconds
        self.device_id=device_id; self.last_device_time=time.monotonic(); self.last_error=None
        accepted=[]
        for packet in packets:
            bid=packet.battery_id
            mode=packet.operating_mode or ('Charging' if packet.charging is True else 'Idle' if packet.current==0 else 'Discharging')
            fields=packet.model_dump(); fields.update(charging=packet.charging if packet.charging is not None else mode=='Charging',operating_mode=mode)
            reading=Measurement(**fields,timestamp=received,source=self.settings.mode,device_id=device_id)
            if self.settings.mode=='live' or self.settings.persist_demo: self.db.store(reading)
            self.latest[bid]=reading
            # Delayed or clock-skewed samples remain available in history but never appear live.
            self.last_valid[bid]=time.monotonic() if sample_fresh else None
            accepted.append(reading)
            active={}
            if reading.battery_status!='NORMAL':
                severity='warning' if reading.battery_status=='WARNING' else 'critical'
                active[reading.battery_status]=(severity,f"STM32 reported {reading.battery_status.replace('_',' ').lower()}.")
            self.battery_alerts[bid]=active
            self.events.update_alerts(self.settings.mode,bid,active)
            await self.manager.broadcast({'type':'measurement','data':reading.model_dump()})
        self.sync_alerts()
        return accepted

    def sync_alerts(self):
        if time.monotonic()-self.started < self.settings.stale_after_seconds: return
        for bid in BATTERY_IDS:
            active=dict(self.battery_alerts[bid])
            if not self.connected(bid): active['GATEWAY_COMMUNICATION_FAILURE']=('critical','No fresh reading for this battery; its condition is unconfirmed.')
            self.events.update_alerts(self.settings.mode,bid,active)

    async def produce(self):
        if self.settings.mode=='demo':
            sims=[Simulator(self.settings.demo_seed),Simulator(self.settings.demo_seed+1)]
            while True:
                from .models import BatteryPacket
                packets=[]
                for bid,sim in zip(BATTERY_IDS,sims):
                    p=sim.next(); packets.append(BatteryPacket(battery_id=bid,**p.model_dump()))
                await self.accept('DEMO_DEVICE',packets)
                await asyncio.sleep(self.settings.demo_interval_seconds)

    async def monitor(self):
        while True:
            self.sync_alerts(); await self.manager.broadcast({'type':'status','data':self.status()}); await asyncio.sleep(1)
    def close(self):
        if self.events is not self.db:self.events.close()
        self.db.close()
