# Energy Supervisory Unit (ESU)

Real-Time Battery Monitoring & SOC Estimation  
Walchand College of Engineering, Sangli · Department of Electronics Engineering

A React/TypeScript dashboard and FastAPI gateway for the ATtiny1604 → STM32 → Raspberry Pi battery monitoring pipeline. STM32 remains the source of SOC and battery status. The application has no charge/discharge control endpoints or UART write commands.

## Start on your Windows laptop

Prerequisites: Python 3.11+ and Node.js 22 LTS with npm. Run from the project root in PowerShell:

```powershell
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
cd frontend
npm ci
npm run build
cd ..
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000**. FastAPI serves both the production dashboard and its API. Default mode is **DEMO**; values and events are prominently marked simulated. No hardware is needed. Use Ctrl+C to stop.

For Linux setup and automatic startup, follow [Raspberry Pi deployment](docs/raspberry_pi_setup.md).

## Dashboard

- **Overview:** SOC gauge, operating mode, runtime when supplied, parameter cards, four rolling charts, connection status and active notifications.
- **Live Analytics:** selectable 1/5/15/60-minute windows and voltage/current comparison with independent axes. The in-browser buffer starts when the page opens and retains up to 3,600 samples for one hour; no invented backfill.
- **Battery History:** SQLite records filtered by source and optional local date/time bounds. Statistics, graphs and CSV cover the most recent 10,000 matching records at most. The table displays the latest 200 of that selection. Narrow the date range for older records. Export uses the last loaded filters.
- **Alerts & Events:** most recent 500 events for the configured mode, with active/resolved state, source, severity and acknowledgement. Acknowledgement does not clear a fault.
- **System Information:** gateway, serial, STM32 and WebSocket status; configuration and rejected-packet count.

All server timestamps are UTC; the browser displays them in the viewer's local timezone. Last known values remain visible after a disconnect, marked stale. No-data is displayed as a dash, never zero SOC.

## Demo and hardware modes

Edit the root `.env`, then restart the backend. Settings are read at process startup, not from the browser.

```dotenv
MODE=demo
PERSIST_DEMO=false
DEMO_INTERVAL_SECONDS=1
DEMO_SEED=42
```

The deterministic simulator cycles through discharging, idle and charging over 240 samples, including a clearly simulated overtemperature event at samples 85–94. By default, demo measurements are **not stored**, and demo event history is in memory only. To exercise historical analytics, set `PERSIST_DEMO=true`, restart, wait for readings, select **Simulated** on Battery History and click **Load history**. Persisted demo records are tagged `source=demo` and never returned as hardware data.

For actual hardware:

```dotenv
MODE=live
SERIAL_PORT=/dev/ttyUSB0
BAUD_RATE=115200
PROTOCOL=jsonl
STALE_AFTER_SECONDS=5
```

Windows serial ports such as `COM3` and Pi direct UART `/dev/serial0` are also configurable. There is **no simulation fallback** in live mode. The port is retried after disconnection. A valid packet must arrive within the stale timeout; an open port alone is not a healthy connection. Select a timeout comfortably larger than the firmware's transmission interval. Run **one Uvicorn worker**, so only one process owns UART and the simulator.

See [the communication contract](docs/communication_protocol.md) before connecting firmware. JSONL is the implemented protocol; `PROTOCOL` selects the parser and rejects unsupported adapters at startup. Add a parser/transport adapter if the firmware chooses a different framing format. No assumption is made that firmware is finalized.

Optional voltage/current/temperature notification thresholds are disabled by default. Configure them for the actual battery in `.env` if needed. They generate separately labelled gateway notifications and never override STM32 status or SOC. Parser plausibility limits are broad data-validation bounds, **not battery protection thresholds**.

## Development

Start the backend as above. In a second terminal:

```powershell
cd frontend
npm run dev
```

Open the URL printed by Vite (normally http://localhost:5173). Vite proxies `/api` and `/ws` to port 8000, avoiding separate browser API configuration. `npm run preview` alone serves only static files; use FastAPI or the Vite development proxy for a complete application.

## Tests and production build

```powershell
cd backend
..\.venv\Scripts\python.exe -m pytest -q
cd ..\frontend
npm run build
```

Tests cover strict parsing, malformed/nonfinite/out-of-range input, bounded UART framing, mock serial reconnection, deterministic simulation, WebSocket updates, source isolation, persistence, CSV/time filters, stale communications, configured thresholds, fault preservation across restarts, notification acknowledgement and static serving.

A separate smoke check launches a real local server on a free port, serves the built UI, receives WebSocket updates, retrieves SQLite history and exports CSV, then stops its server:

```powershell
.\.venv\Scripts\python.exe scripts\smoke_check.py
```

## API

Interactive API schema: http://127.0.0.1:8000/docs

| Route | Purpose |
|---|---|
| `GET /api/health` | Gateway health and current communication state |
| `GET /api/system` | Mode, host, UART configuration, errors and last reception |
| `GET /api/latest` | Latest reading in current mode, or `null` |
| `GET /api/history` | `source`, timezone-aware `start`/`end`, `limit` (1–10,000) |
| `GET /api/export` | CSV with the same source/time/limit filters |
| `GET /api/alerts` | Current mode's event log; `limit` (1–500) |
| `POST /api/alerts/{id}/acknowledge` | Mark a notification acknowledged |
| `WS /ws/battery` | Measurement events and one-second status events |

`/latest` may contain stale data: consumers must consult connection status and timestamps. History defaults to the configured mode. Date ranges are inclusive, results are the newest matching rows returned in chronological order. Date inputs without a timezone are rejected.

## Project layout

```text
frontend/src/        React UI, charts, telemetry hook and API types
backend/app/         FastAPI, settings, validation, SQLite, UART, simulator
backend/tests/       Backend and serial integration tests
scripts/            Real-server smoke verification
docs/               Architecture, wire contract and Pi deployment
deploy/             systemd service template
.env.example        Runtime configuration template
```

This deployment targets a trusted local network. There is no user authentication; anyone with network access can view measurements and acknowledge notifications. No public hosting is configured. Hardware protection is not claimed by the dashboard. Disk retention is operator-managed; archive old SQLite data as needed. Physical STM32/Pi validation and browser visual inspection must be performed on the target devices.
