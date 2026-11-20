# Energy Supervisory Unit

Responsive dual battery monitoring dashboard for the pipeline **ATtiny1604 sensing → STM32 processing/SOC/supervision → ESP32 UART/Wi-Fi bridge → FastAPI → React**. Each battery has isolated readings, freshness, history, charts and alerts. The gateway does not calculate SOC or claim physical protection.

## Run locally (PowerShell)

Prerequisites: Python 3.11+ and Node.js 20+. From the repository root:

```powershell
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
Push-Location frontend
npm ci
npm run build
Pop-Location
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000. Default `MODE=demo` runs an explicitly labelled dual simulator; no simulated value is presented as a hardware reading. Stop with Ctrl+C. For Vite hot reload, run the backend in one terminal and `cd frontend; npm run dev` in another.

## Modes

`MODE=demo` is development only. It creates two distinct demo sources and hardware ingest returns 409. Demo history is memory-only unless `PERSIST_DEMO=true`.

For the ESP32 link, configure `.env`:

```dotenv
MODE=live
STALE_AFTER_SECONDS=10
INGEST_TOKEN=replace-with-a-long-random-secret
```

Restart the backend after changing settings. Live mode does not synthesize readings. The ESP32 posts to `http://<backend-host>:8000/api/ingest`. Set its server URL, Wi-Fi credentials, bearer token, device ID, UART pins, UART baud and timeouts in `firmware/esp32_gateway/hardware_config.h` (copy the `.example.h`). UART pins and baud must match the actual board and firmware; no physical configuration has been assumed.

## ESP32 firmware and hardware

Install ArduinoJson 7, copy `firmware/esp32_gateway/hardware_config.example.h` to `hardware_config.h`, then configure the actual Wi-Fi/network and STM32/ESP32 UART settings. STM32 sends one JSONL line containing a `batteries` array. The sketch wraps it with `device_id` and HTTP POSTs to FastAPI.

For a receive-only telemetry link, connect **STM32 UART TX → configured ESP32 UART RX** and **STM32 GND ↔ ESP32 GND**. Leave ESP32 TX disconnected unless a separately designed return channel is required. Check both board datasheets and measure/confirm the STM32 TX logic level against the selected ESP32 input tolerance; add a suitable level translator when needed. Power each board from its specified supply. Configure UART pins, peripheral, baud, framing and timeouts only after confirming the exact board variants and STM32 firmware settings. Confirm the STM32 → ESP32 JSONL schema in `docs/communication_protocol.md` before wiring. Physical validation and SOC calibration remain outstanding until tested with the actual boards; SOC algorithm outputs remain the STM32's responsibility.

## Simulated ESP32 sender

With the backend running in `MODE=live`, use a second PowerShell terminal:

```powershell
$env:BMS_INGEST_URL = 'http://127.0.0.1:8000/api/ingest'
$env:BMS_INGEST_TOKEN = 'replace-with-a-long-random-secret'
.\.venv\Scripts\python.exe scripts\simulate_esp32.py
```

The sender posts clearly synthetic fixtures for both battery IDs. It exercises HTTP ingest only; it does not validate physical UART or Wi-Fi hardware. Omit `BMS_INGEST_TOKEN` when `INGEST_TOKEN` is unset.

## API

- `POST /api/ingest` validates ESP32 batch JSON; live mode only.
- `GET /api/system` and `/api/health` report ESP32 connectivity and per-battery freshness.
- `GET /api/batteries` returns both latest readings; `GET /api/latest?battery_id=BATTERY_1` returns one.
- `GET /api/history?battery_id=BATTERY_1&source=live` queries independent history; optional timezone-aware `start`, `end`, `limit`.
- `GET /api/export` exports filtered CSV; `GET /api/alerts?battery_id=BATTERY_2` returns battery-specific alerts.
- `POST /api/alerts/{id}/acknowledge` acknowledges only the event.
- `WS /ws/battery` broadcasts tagged measurement events and status updates.

Interactive schema: http://127.0.0.1:8000/docs. Existing single-battery SQLite rows are migrated to `BATTERY_1`; `BATTERY_2` remains empty until actual or demo data arrives.

## Verification

```powershell
Push-Location backend
..\.venv\Scripts\python.exe -m pytest -q
Pop-Location
Push-Location frontend
npm run build
Pop-Location
```

Tests cover dual ingest, strict validation, independent history/freshness, SQLite migration, battery-tagged WebSocket events and demo/live separation. Simulated tests do not constitute physical ESP32/STM32 integration testing.

## Configuration and deployment notes

`.env.example` lists backend settings. For local network access bind Uvicorn to the intended LAN interface; this dashboard has no user accounts. Do not expose it to the public internet without authentication and TLS. Run one backend worker. Database path defaults to `backend/data/esu.sqlite3`; manage retention and backups for your deployment.
