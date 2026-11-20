export type Source = 'demo'|'live';
export type BatteryId = 'BATTERY_1'|'BATTERY_2';
export type Reading = { id?:number; battery_id:BatteryId; device_id:string|null; timestamp:string; voltage:number; current:number; temperature:number; soc:number; charging:boolean; battery_status:string; operating_mode:string; runtime_minutes:number|null; source:Source };
export type BatteryConnection = { connected:boolean; stale:boolean; last_received:string|null };
export type System = { backend:string; mode:Source; device_id:string|null; esp32_connected:boolean; stale:boolean; last_received:string|null; stale_after_seconds:number; hostname:string; platform:string; persist_demo:boolean; rejected_packets:number; last_error:string|null; batteries:Record<BatteryId,BatteryConnection> };
export type Alert = { id:number; battery_id:BatteryId|null; code:string; severity:'normal'|'warning'|'critical'; description:string; timestamp:string; resolved_at:string|null; acknowledged:boolean; source:Source };
