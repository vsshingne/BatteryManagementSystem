import { useEffect, useState } from 'react';
import { api } from './api';
import type { BatteryId, Reading, System } from './types';
const ids:BatteryId[]=['BATTERY_1','BATTERY_2'];
export function useTelemetry() {
 const [latest,setLatest]=useState<Record<BatteryId,Reading|null>>({BATTERY_1:null,BATTERY_2:null});
 const [readings,setReadings]=useState<Record<BatteryId,Reading[]>>({BATTERY_1:[],BATTERY_2:[]});
 const [system,setSystem]=useState<System|null>(null); const [socketOpen,setSocketOpen]=useState(false); const [backendOnline,setBackendOnline]=useState(false); const [now,setNow]=useState(Date.now());
 useEffect(()=>{let disposed=false;let socket:WebSocket|undefined;let retry:ReturnType<typeof setTimeout>;let generation=0;
  const receive=(r:Reading)=>{if(!ids.includes(r.battery_id))return;setLatest(old=>({...old,[r.battery_id]:r}));setReadings(old=>({...old,[r.battery_id]:[...old[r.battery_id].filter(x=>x.timestamp!==r.timestamp&&Date.parse(x.timestamp)>Date.now()-3600000),r].sort((a,b)=>Date.parse(a.timestamp)-Date.parse(b.timestamp)).slice(-3600)}));};
  const refresh=async()=>{try{const s=await api<System>('/system');if(!disposed){setSystem(s);setBackendOnline(true)}}catch{if(!disposed)setBackendOnline(false)}};
  const connect=()=>{socket=new WebSocket(`${location.protocol==='https:'?'wss:':'ws:'}//${location.host}/ws/battery`);socket.onopen=()=>{if(!disposed){setSocketOpen(true);void refresh()}};socket.onmessage=e=>{if(disposed)return;try{const m=JSON.parse(e.data);if(m.type==='measurement'){generation++;receive(m.data)}if(m.type==='status'){setSystem(m.data);setBackendOnline(true)}}catch{/* ignore malformed server frames */}};socket.onclose=()=>{if(!disposed){setSocketOpen(false);retry=setTimeout(connect,2000)}};socket.onerror=()=>socket?.close()};
  const start=async()=>{await refresh();const n=generation;try{const data=await api<Record<BatteryId,Reading|null>>('/batteries');if(!disposed&&generation===n)ids.forEach(id=>{if(data[id])receive(data[id]!)})}catch{/* status poll reports backend outage */}};
  void start();connect();const health=setInterval(refresh,5000),tick=setInterval(()=>setNow(Date.now()),1000);return()=>{disposed=true;clearInterval(health);clearInterval(tick);clearTimeout(retry);socket?.close()};
 },[]);
 const stale=(id:BatteryId)=>{const r=latest[id],conn=system?.batteries[id];return !r||!backendOnline||!socketOpen||!conn?.connected||r.source!==system?.mode||now-Date.parse(r.timestamp)>(system?.stale_after_seconds??10)*1000};
 return {latest,readings,system,socketOpen,backendOnline,stale,now};
}
