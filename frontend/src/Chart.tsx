import { ResponsiveContainer, AreaChart, Area, CartesianGrid, XAxis, YAxis, Tooltip, Legend } from 'recharts';
import type { Reading } from './types';
export const parameters = [
  { key: 'voltage', label: 'Battery voltage', unit: 'V', color: '#5b9cff', digits: 2 },
  { key: 'current', label: 'Battery current', unit: 'A', color: '#35d6b5', digits: 2 },
  { key: 'temperature', label: 'Cell temperature', unit: '°C', color: '#f2b965', digits: 1 },
  { key: 'soc', label: 'State of charge', unit: '%', color: '#a49bff', digits: 1 },
] as const;
export type Parameter = typeof parameters[number];
export function Chart({ readings, parameter, comparison = false }: { readings: Reading[]; parameter: Parameter; comparison?: boolean }) {
  const data = readings.map(r => ({ ...r, time: Date.parse(r.timestamp) }));
  if (!data.length) return <div className="chart-empty"><span className="empty-wave">∿</span>Waiting for measurements<span>Readings will appear here as they arrive.</span></div>;
  return <ResponsiveContainer width="100%" height={210}><AreaChart data={data} margin={{ top: 16, right: comparison ? 12 : 18, left: 0, bottom: 0 }}>
    <defs><linearGradient id={`fill-${parameter.key}-${comparison}`} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={parameter.color} stopOpacity={0.19}/><stop offset="100%" stopColor={parameter.color} stopOpacity={0}/></linearGradient></defs>
    <CartesianGrid stroke="#26303f" strokeDasharray="3 5" vertical={false}/>
    <XAxis dataKey="time" type="number" domain={['dataMin', 'dataMax']} tickFormatter={v => new Date(v).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })} stroke="#738197" tickLine={false} axisLine={false} minTickGap={45} fontSize={10}/>
    <YAxis yAxisId="left" width={48} domain={parameter.key === 'soc' ? [0,100] : ['auto','auto']} tickFormatter={v => `${Number(v).toFixed(1)}`} stroke="#738197" tickLine={false} axisLine={false} fontSize={10} unit={comparison ? 'V' : undefined}/>
    {comparison && <YAxis yAxisId="right" orientation="right" width={48} stroke="#35d6b5" fontSize={10} unit="A"/>}
    <Tooltip contentStyle={{ background: '#141e2c', border: '1px solid #334154', borderRadius: 8, fontSize: 12 }} labelFormatter={v => new Date(Number(v)).toLocaleString()} formatter={(v, name) => [`${Number(v).toFixed(2)} ${name === 'Current' ? 'A' : parameter.unit}`, name]}/>
    <Area yAxisId="left" type="monotone" dataKey={parameter.key} name={comparison ? 'Voltage' : parameter.label} stroke={parameter.color} strokeWidth={2} fill={`url(#fill-${parameter.key}-${comparison})`} isAnimationActive={false} dot={data.length === 1}/>
    {comparison && <><Area yAxisId="right" type="monotone" dataKey="current" name="Current" stroke="#35d6b5" fill="transparent" strokeWidth={2} isAnimationActive={false}/><Legend/></>}
  </AreaChart></ResponsiveContainer>;
}
