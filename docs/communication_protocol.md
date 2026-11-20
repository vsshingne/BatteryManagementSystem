# STM32 to ESP32 JSONL contract

The ESP32 sketch is a Wi-Fi transport bridge. The selected STM32 UART output must emit one UTF-8 JSON object per line with a `batteries` array. Exact UART pins, baud, logic levels, and cadence must be agreed from the actual boards and firmware; this repository does not assume those electrical settings.

```json
{"batteries":[{"battery_id":"BATTERY_1","voltage":12.4,"current":1.5,"temperature":29.5,"soc":85,"battery_status":"NORMAL","operating_mode":"Discharging"},{"battery_id":"BATTERY_2","voltage":12.1,"current":0.8,"temperature":30.2,"soc":72,"battery_status":"NORMAL","operating_mode":"Charging"}]}
```

Required per battery: `battery_id` (`BATTERY_1` or `BATTERY_2`), finite numeric voltage (0–1000 V), current (−10,000–10,000 A), temperature (−100–250 °C), and SOC (0–100%). Status defaults to `NORMAL` and accepts `NORMAL`, `WARNING`, `OVERVOLTAGE`, `UNDERVOLTAGE`, `OVERCURRENT`, `OVERTEMPERATURE`, `SENSOR_ERROR`, or `COMMUNICATION_FAILURE`. `operating_mode` accepts `Charging`, `Discharging`, or `Idle`; alternatively provide boolean `charging`. Optional `runtime_minutes` is a finite nonnegative STM32 estimate. These broad bounds validate transport data and are not protection thresholds.

The ESP32 wraps the battery array as:

```json
{"device_id":"ESP32_01","batteries":[{"battery_id":"BATTERY_1","voltage":12.4,"current":1.5,"temperature":29.5,"soc":85,"battery_status":"NORMAL","operating_mode":"Discharging"}]}
```

It posts this JSON to `/api/ingest`. `timestamp` is optional; the backend timestamps reception in UTC when absent. Optional bearer authentication is controlled by `INGEST_TOKEN`. Live ingest only works with `MODE=live`; demo mode rejects hardware writes. HTTP success is 202. Validation errors return 422, unauthorized senders 401, demo mode 409, and storage failures 503. The ESP32 retries on subsequent input frames after communication failures.

Install ArduinoJson 7 in Arduino IDE, copy `firmware/esp32_gateway/hardware_config.example.h` to `hardware_config.h`, and configure Wi-Fi, API URL, device ID, UART peripheral, pins, baud, framing and timeouts. For a receive-only link, wire STM32 UART TX to the configured ESP32 UART RX and connect the boards' grounds. Leave ESP32 TX disconnected unless a return channel is intentionally designed. Verify the specific board logic levels and input tolerances; use a suitable level translator if required and power each board from its specified supply. Values must come from the actual design, not the example. The dashboard cannot verify physical wiring or SOC calibration.
