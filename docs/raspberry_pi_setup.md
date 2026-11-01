# Raspberry Pi deployment

Use Raspberry Pi OS with Python 3.11+ and Node.js 22 LTS. The Pi hosts the backend and production frontend; STM32 remains the controller. These instructions assume checkout `/home/pi/esu` and service account `pi`; substitute your actual username and absolute paths throughout.

## 1. Install and build

Install OS packages and a compatible Node.js release for your Pi's architecture. Check `node --version` and `npm --version` before building.

```bash
sudo apt update
sudo apt install python3-venv python3-pip
cd /home/pi/esu
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
cp .env.example .env
cd frontend
npm ci
npm run build
cd ..
```

The frontend can also be built on a laptop and `frontend/dist` copied to the Pi. Node is not required at runtime when the built files already exist. Install backend dependencies on the Pi itself; do not copy a Windows virtual environment.

## 2. Configure UART and mode

Start with `MODE=demo`. For the hardware stage, set:

```dotenv
MODE=live
SERIAL_PORT=/dev/ttyUSB0
BAUD_RATE=115200
PROTOCOL=jsonl
PERSIST_DEMO=false
STALE_AFTER_SECONDS=5
```

Use the baud rate agreed with the STM32 firmware. A stable `/dev/serial/by-id/...` path may be preferable for USB adapters. The serial reader requires receive permission:

```bash
sudo usermod -aG dialout pi
```

Log out and back in after changing groups. For a direct GPIO UART, configure the OS hardware UART and disable the login console on that UART through `sudo raspi-config`, reboot if requested, then set `SERIAL_PORT=/dev/serial0`. Confirm the chosen port is not owned by another service. Verify electrical compatibility and wiring against the actual Pi/STM32 boards before connecting; the software cannot detect wiring errors.

See [communication protocol](communication_protocol.md). A missing device leaves live mode disconnected and triggers a communication event; it never starts the simulator.

## 3. Run and access over Wi-Fi

```bash
cd /home/pi/esu
.venv/bin/python -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000
```

Find the Pi's local address with `hostname -I`. On another device connected to the same local network, open `http://<pi-ip>:8000`. Port 8000 must be allowed by any local firewall, and Wi-Fi client isolation must not block connections. The phone/laptop's `localhost` is not the Pi. FastAPI serves the built frontend and proxies are unnecessary.

This is a local-network deployment. Do not configure internet port forwarding for this unauthenticated dashboard. No public deployment is included. The backend exposes telemetry and notification acknowledgement, never charge/discharge control. If remote access becomes necessary, design authenticated access separately.

## 4. Run on boot using systemd

Review `deploy/esu.service` and replace every account/path placeholder as needed. Ensure the selected user owns the checkout and can write `backend/data`. Then:

```bash
sudo cp deploy/esu.service /etc/systemd/system/esu.service
sudo systemctl daemon-reload
sudo systemctl enable --now esu
sudo systemctl status esu
journalctl -u esu -f
```

The template loads `/home/pi/esu/.env`, starts a single worker and restarts the service on process failure. The program handles serial reconnect internally. Stop any manually launched backend before enabling the service. Do not use multiple Uvicorn workers or `--reload` in production; UART must have one owner.

After `.env` changes or a new frontend build:

```bash
sudo systemctl restart esu
```

## 5. Verification

```bash
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/latest
cd /home/pi/esu/backend
../.venv/bin/python -m pytest -q
```

In demo mode, confirm the DEMO banner, changing graphs and no STM32 connection claim. To test history, temporarily enable `PERSIST_DEMO=true`, restart, collect readings, and load the Simulated source. Return to the intended settings afterward.

In hardware mode, transmit agreed packets and confirm `source=live`, correct SOC passthrough, real values and timestamps. Disconnect UART: the UI must mark readings stale/disconnected and retain the last timestamp. Reconnect and confirm automatic recovery. Verify event acknowledgement changes only the notification flag. Check mobile layout from a second device. Automated tests do not replace this hardware acceptance test.

## 6. Storage and maintenance

Default database: `/home/pi/esu/backend/data/esu.sqlite3`. WAL sidecar files may exist while running. Set `DATABASE_PATH` to change it. All values are tagged by source. Monitor free space; there is no automatic deletion or retention policy. At one sample per second, records accumulate continuously.

For a straightforward consistent backup, stop the service before copying the database files, then restart it. Keep archives off the Pi's SD card. Rebuild the UI with `npm ci && npm run build` after frontend changes, reinstall Python dependencies when requirements change and restart the service. An empty history in default demo mode is expected because demo persistence is disabled.

Troubleshooting: inspect `/api/system` and `journalctl`; check dialout group membership, configured device, matching baud, newline framing and rejected-packet counts. Confirm the host clock is synchronized, since stored UTC timestamps and browser age checks depend on it.
