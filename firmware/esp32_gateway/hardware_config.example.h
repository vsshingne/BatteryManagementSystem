#pragma once
// Copy to hardware_config.h and fill these from the actual board/wiring plan.
// No UART pin, baud, or electrical assumptions are embedded in the sketch.
#define ESU_WIFI_SSID "configure-me"
#define ESU_WIFI_PASSWORD "configure-me"
#define ESU_API_URL "http://192.168.1.10:8000/api/ingest"
#define ESU_DEVICE_ID "ESP32_01"
#define ESU_INGEST_TOKEN ""
// Define these after checking the exact ESP32 variant and STM32 design:
// #define ESU_UART_RX_PIN <selected GPIO>
// #define ESU_UART_TX_PIN <selected GPIO>
// #define ESU_UART_BAUD <agreed baud>
// #define ESU_UART_PORT <UART peripheral index for selected ESP32 variant>
// #define ESU_UART_FORMAT <agreed Arduino UART framing constant>
#define ESU_UART_TIMEOUT_MS 1500
#define ESU_HTTP_TIMEOUT_MS 5000
#define ESU_MAX_LINE_BYTES 4096
