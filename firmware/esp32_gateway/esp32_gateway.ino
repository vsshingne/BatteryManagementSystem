// ESP32 transport bridge: STM32 JSONL -> Wi-Fi HTTP POST -> FastAPI.
// Install ArduinoJson 7. Set every value in hardware_config.h from the actual design.
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include "hardware_config.h"

#if !defined(ESU_UART_BAUD) || !defined(ESU_UART_RX_PIN) || !defined(ESU_UART_TX_PIN) || !defined(ESU_UART_PORT) || !defined(ESU_UART_FORMAT)
#error "Set UART peripheral, baud, pins and framing in hardware_config.h after checking the board and wiring"
#endif

HardwareSerial stm32(ESU_UART_PORT);
String lineBuffer;
unsigned long lastByteMs = 0;

void connectWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;
  WiFi.mode(WIFI_STA);
  WiFi.begin(ESU_WIFI_SSID, ESU_WIFI_PASSWORD);
  const unsigned long started = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - started < ESU_HTTP_TIMEOUT_MS) delay(100);
}

bool forwardReading(const String& stmJson) {
  JsonDocument input;
  if (deserializeJson(input, stmJson) || !input["batteries"].is<JsonArray>()) return false;
  JsonDocument output;
  output["device_id"] = ESU_DEVICE_ID;
  // Omit device time; backend adds an ISO UTC reception timestamp.
  output["batteries"] = input["batteries"];
  String body;
  serializeJson(output, body);
  connectWiFi();
  if (WiFi.status() != WL_CONNECTED) return false;
  HTTPClient http;
  http.setTimeout(ESU_HTTP_TIMEOUT_MS);
  if (!http.begin(ESU_API_URL)) return false;
  http.addHeader("Content-Type", "application/json");
  if (strlen(ESU_INGEST_TOKEN) > 0) http.addHeader("Authorization", String("Bearer ") + ESU_INGEST_TOKEN);
  const int status = http.POST(body);
  http.end();
  return status >= 200 && status < 300;
}

void setup() {
  lineBuffer.reserve(ESU_MAX_LINE_BYTES);
  // Pin numbers and framing are from the configuration header / board design.
  stm32.begin(ESU_UART_BAUD, ESU_UART_FORMAT, ESU_UART_RX_PIN, ESU_UART_TX_PIN);
  connectWiFi();
}

void loop() {
  while (stm32.available()) {
    const char c = static_cast<char>(stm32.read());
    lastByteMs = millis();
    if (c == '\n') {
      if (lineBuffer.length() > 0) {
        (void)forwardReading(lineBuffer); // next incoming frame retries after any network failure
        lineBuffer = "";
      }
    } else if (lineBuffer.length() < ESU_MAX_LINE_BYTES) {
      if (c != '\r') lineBuffer += c;
    } else {
      lineBuffer = ""; // Drop an overlong frame through the next newline.
    }
  }
  if (lineBuffer.length() > 0 && millis() - lastByteMs > ESU_UART_TIMEOUT_MS) lineBuffer = "";
  if (WiFi.status() != WL_CONNECTED) connectWiFi();
  delay(2);
}
