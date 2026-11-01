# STM32 ↔ Raspberry Pi telemetry contract

This is the implemented, provisional contract. Agree units, sign convention, status vocabulary and cadence with the firmware team before hardware integration. Port and baud rate are runtime settings; the parser is isolated in `backend/app/serial_reader.py` for protocol changes.

## Transport and framing

- UART configured by `SERIAL_PORT` and `BAUD_RATE`, default `/dev/ttyUSB0` and `115200`.
- Current PySerial defaults: 8 data bits, no parity, one stop bit, no flow control. Modify the serial adapter if firmware uses other line settings.
- `PROTOCOL=jsonl`: one UTF-8 JSON object per line, terminated with LF (`\n`). CRLF is accepted. No multiline JSON.
- Maximum line size defaults to 4,096 bytes. Blank lines are ignored. Partial lines persist across read timeouts. Oversized lines are dropped through the next LF.
- Default serial read timeout: 0.5 s; reconnect delay: 2 s; stale timeout: 5 s.
- No gateway UART writes, command channel or protection controls.

Example packet (illustrative values, followed by an actual newline):

```json
{"voltage":3.92,"current":0.84,"temperature":31.0,"soc":78.0,"battery_status":"NORMAL","charging":false}
```

## Fields

| Field | Required | Type / accepted range | Meaning |
|---|---|---|---|
| `voltage` | Yes | JSON number, 0–1,000 | Battery voltage, V |
| `current` | Yes | JSON number, −10,000–10,000 | Battery current, A |
| `temperature` | Yes | JSON number, −100–250 | Sensor temperature, °C |
| `soc` | Yes | JSON number, 0–100 | STM32 SOC, %, passed through unchanged |
| `battery_status` | Yes | Enum below | STM32 supervisory status |
| `charging` | Yes | JSON boolean | `true` when charging |
| `operating_mode` | No | `Charging`, `Discharging`, `Idle` | Explicit STM32 display mode |
| `runtime_minutes` | No | Nonnegative finite number ≤1,000,000 or null | Optional firmware runtime estimate |

Accepted status values: `NORMAL`, `WARNING`, `OVERVOLTAGE`, `UNDERVOLTAGE`, `OVERCURRENT`, `OVERTEMPERATURE`, `SENSOR_ERROR`, `COMMUNICATION_FAILURE`.

Numbers encoded as strings, booleans in numeric fields, unknown keys, missing required fields, NaN/Infinity and values beyond the broad plausibility bounds are rejected. These ranges are validation limits, not protection thresholds. Update the schema deliberately when firmware adds fields; unknown fields are not silently accepted.

When supplied, `operating_mode` must agree with `charging`. Without it, `charging=true` displays Charging; otherwise exactly zero current displays Idle and nonzero current displays Discharging. Firmware should send an explicit mode to avoid near-zero sensor noise affecting the display. This is a display fallback only and does not affect battery decisions or SOC. The simulator uses positive current for discharge and negative current for charge. Confirm the hardware current sign convention; the gateway preserves the received sign.

Packets describe one battery status at a time. Extend the contract explicitly if firmware needs simultaneous fault flags. No MCU-origin timestamp, sequence number or checksum is currently defined; timestamps represent Pi reception. Add a versioned framing/validation adapter if integrity or sequence requirements change.

## Gateway output

Valid packets gain:

```json
{"timestamp":"2026-10-30T08:45:12.123+00:00","source":"live","id":123}
```

`id` is null for unsaved demo data. API measurements also include all normalized optional fields. A successful serial open does not make telemetry fresh: only an accepted packet resets the staleness timer. Invalid packets increment `rejected_packets`; serial errors and parse errors are exposed in `/api/system`. The error clears on the next accepted packet.

WebSocket events:

```json
{"type":"measurement","data":{"voltage":3.92,"current":0.84,"temperature":31.0,"soc":78.0,"battery_status":"NORMAL","charging":false,"operating_mode":"Discharging","runtime_minutes":null,"timestamp":"2026-10-30T08:45:12.123+00:00","source":"live","id":123}}
```

```json
{"type":"status","data":{"backend":"ok","mode":"live","connected":false,"stale":true}}
```

The second example abbreviates system fields. `connected=false` or `stale=true` means that any previous measurement is historical. Clients should also check timestamp age and their own socket connectivity.

## Parser verification without hardware

Run `python -m pytest -q` from `backend` in the virtual environment. The mock UART test verifies configured device and baud, a failed initial open, reconnect, malformed input, a valid packet split across reads, shutdown and closure. Other tests cover oversize-line recovery and ensure missing live hardware does not produce simulated readings.
