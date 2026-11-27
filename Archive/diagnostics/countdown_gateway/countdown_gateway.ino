#include <ESP8266WiFi.h>
#include <WiFiClientSecure.h>
#include <ESP8266HTTPClient.h>
#include <ArduinoJson.h>
#include <TelegramCertificate.h>
#include <SoftwareSerial.h>
#include <time.h>
#include <cstring>
#include "secrets.h"

// Use D5/GPIO14 so the USB serial connection remains available for uploads/logs.
SoftwareSerial eventInput(D5, -1);
BearSSL::X509List telegramCertificate(TELEGRAM_CERTIFICATE_ROOT);
BearSSL::WiFiClientSecure secureClient;
char eventLine[24];
size_t eventLength = 0;
bool discardLine = false;
bool reminderHandled = false;

void handleEvent(const char* event) {
  if (strcmp(event, "START") == 0) {
    reminderHandled = false;
    Serial.println(F("New Uno countdown started."));
    return;
  }
  if (strcmp(event, "COUNTDOWN_30") != 0) {
    if (event[0]) Serial.println(F("Unknown event ignored."));
    return;
  }
  if (reminderHandled) {
    Serial.println(F("Duplicate reminder ignored."));
    return;
  }
  reminderHandled = true;
  if (WiFi.status() != WL_CONNECTED || time(nullptr) < 1704067200) {
    Serial.println(F("SKIPPED: Network/clock not ready. Restore ESP readiness, then reset the Uno."));
    return;
  }
  Serial.println(F("Uno 30-second event received. Sending Telegram alert..."));
  StaticJsonDocument<256> payload;
  payload["chat_id"] = CHAT_ID;
  payload["text"] = "Countdown test: 30 seconds elapsed on the Arduino Uno.";
  String body;
  serializeJson(payload, body);
  HTTPClient request;
  request.setTimeout(15000);
  bool sent = false;
  int httpStatus = -1;
  if (request.begin(secureClient, String("https://api.telegram.org/bot") + BOT_TOKEN + "/sendMessage")) {
    request.addHeader("Content-Type", "application/json");
    // Make one request and read its complete body, including delayed TCP fragments.
    httpStatus = request.POST(body);
    if (httpStatus == HTTP_CODE_OK) {
      StaticJsonDocument<64> filter;
      filter["ok"] = true;
      StaticJsonDocument<64> result;
      DeserializationError error = deserializeJson(result, request.getString(), DeserializationOption::Filter(filter));
      sent = !error && result["ok"].is<bool>() && result["ok"].as<bool>();
    }
  }
  request.end();
  secureClient.stop();
  Serial.print(F("Telegram HTTP status: "));
  Serial.println(httpStatus);
  Serial.println(sent ? F("PASS: Telegram accepted the Uno countdown alert.") :
                        F("FAILED: Delivery unconfirmed. Check the chat before resetting the Uno."));
}

void setup() {
  Serial.begin(115200);
  eventInput.begin(9600);
  delay(200);
  Serial.println();
  Serial.println(F("Kitchen assistant: Uno countdown gateway"));
  secureClient.setTrustAnchors(&telegramCertificate);
  secureClient.setTimeout(15000);
  if (!WIFI_SSID[0] || !BOT_TOKEN[0] || !CHAT_ID[0] ||
      strcmp(WIFI_SSID, "YOUR_WIFI_NAME") == 0 ||
      strcmp(WIFI_PASSWORD, "YOUR_WIFI_PASSWORD") == 0 ||
      strcmp(BOT_TOKEN, "YOUR_BOT_TOKEN") == 0 ||
      strcmp(CHAT_ID, "YOUR_CHAT_ID") == 0) {
    Serial.println(F("Fill in secrets.h, then upload again."));
    return;
  }
  WiFi.persistent(false);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.println(F("Connecting to Wi-Fi (up to 45 seconds)..."));
  unsigned long started = millis();
  while (WiFi.status() != WL_CONNECTED) {
    if (millis() - started >= 45000UL) {
      Serial.println(F("Wi-Fi timeout. Restore the hotspot, then reset the ESP8266."));
      return;
    }
    delay(250);
  }
  Serial.println(F("Wi-Fi connected."));
  configTime(0, 0, "pool.ntp.org", "time.nist.gov");
  started = millis();
  while (time(nullptr) < 1704067200) {
    if (millis() - started >= 30000UL) {
      Serial.println(F("Clock timeout. Check internet access, then reset the ESP8266."));
      return;
    }
    delay(250);
  }
  // shortcut: reset the Uno after READY; add a handshake for unattended startup.
  Serial.println(F("READY: Waiting for Uno D9 through the divider to ESP D5. Reset the Uno now."));
}

void loop() {
  while (eventInput.available()) {
    int value = eventInput.read();
    if (value == '\r') continue;
    if (value == '\n') {
      if (!discardLine) {
        eventLine[eventLength] = '\0';
        handleEvent(eventLine);
      }
      eventLength = 0;
      discardLine = false;
    } else if (!discardLine) {
      if (value < 32 || value > 126 || eventLength >= sizeof(eventLine) - 1) {
        discardLine = true;
      } else {
        eventLine[eventLength++] = char(value);
      }
    }
  }
  delay(1);
}
