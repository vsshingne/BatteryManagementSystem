import { useEffect, useState } from 'react';
import { api } from './api';
import type { Reading, System } from './types';

export function useTelemetry() {
  const [latest, setLatest] = useState<Reading | null>(null);
  const [readings, setReadings] = useState<Reading[]>([]);
  const [system, setSystem] = useState<System | null>(null);
  const [socketOpen, setSocketOpen] = useState(false);
  const [backendOnline, setBackendOnline] = useState(false);
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    let disposed = false;
    let socket: WebSocket | undefined;
    let retry: ReturnType<typeof setTimeout>;
    let generation = 0;
    const receive = (r: Reading) => {
      setLatest(r);
      setReadings(old => [...old.filter(x => x.source === r.source && x.timestamp !== r.timestamp && Date.parse(x.timestamp) > Date.now() - 3600000), r].sort((a,b) => Date.parse(a.timestamp)-Date.parse(b.timestamp)).slice(-3600));
    };
    const refresh = async () => {
      try { const s = await api<System>('/system'); if (!disposed) { setSystem(s); setBackendOnline(true); } }
      catch { if (!disposed) setBackendOnline(false); }
    };
    const connect = () => {
      socket = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws/battery`);
      socket.onopen = () => { if (!disposed) { setSocketOpen(true); void refresh(); } };
      socket.onmessage = e => { if (disposed) return; const msg = JSON.parse(e.data); if (msg.type === 'measurement') { generation++; receive(msg.data); } if (msg.type === 'status') { setSystem(msg.data); setBackendOnline(true); } };
      socket.onclose = () => { if (!disposed) { setSocketOpen(false); retry = setTimeout(connect, 2000); } };
      socket.onerror = () => socket?.close();
    };
    const start = async () => {
      await refresh();
      const initialGeneration = generation;
      try { const r = await api<Reading | null>('/latest'); if (!disposed && r && generation === initialGeneration) receive(r); } catch { /* health poll indicates outage */ }
    };
    void start(); connect();
    const health = setInterval(refresh, 5000);
    const tick = setInterval(() => setNow(Date.now()), 1000);
    return () => { disposed = true; clearInterval(health); clearInterval(tick); clearTimeout(retry); socket?.close(); };
  }, []);
  const stale = !latest || !backendOnline || !socketOpen || !system?.connected || latest.source !== system.mode || now - Date.parse(latest.timestamp) > (system?.stale_after_seconds ?? 5) * 1000;
  return { latest, readings, system, socketOpen, backendOnline, stale, now };
}
