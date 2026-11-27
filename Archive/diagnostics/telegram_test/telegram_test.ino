#include <ESP8266WiFi.h>
#include <WiFiClientSecure.h>
#include <UniversalTelegramBot.h>
#include <time.h>
#include <cstring>
#include "secrets.h"

BearSSL::X509List telegramCertificate(TELEGRAM_CERTIFICATE_ROOT);
BearSSL::WiFiClientSecure secureClient;
UniversalTelegramBot bot(BOT_TOKEN, secureClient);

void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.println();
  Serial.println(F("Kitchen assistant: ESP8266 Telegram test"));

  if (!WIFI_SSID[0] || !BOT_TOKEN[0] || !CHAT_ID[0] ||
      strcmp(WIFI_SSID, "YOUR_WIFI_NAME") == 0 ||
      strcmp(WIFI_PASSWORD, "YOUR_WIFI_PASSWORD") == 0 ||
      strcmp(BOT_TOKEN, "YOUR_BOT_TOKEN") == 0 ||
      strcmp(CHAT_ID, "YOUR_CHAT_ID") == 0) {
    Serial.println(F("Fill in secrets.h, upload again, then press RESET."));
    return;
  }

  WiFi.persistent(false);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.println(F("Connecting to Wi-Fi (up to 45 seconds)..."));
  unsigned long started = millis();
  while (WiFi.status() != WL_CONNECTED) {
    if (millis() - started >= 45000UL) {
      Serial.print(F("Wi-Fi status code: "));
      Serial.println(WiFi.status());
      int networks = WiFi.scanNetworks();
      if (networks < 0) {
        Serial.println(F("Hotspot scan failed; visibility is unknown."));
      } else {
        bool visible = false;
        for (int i = 0; i < networks; ++i) {
          if (WiFi.SSID(i) == WIFI_SSID) visible = true;
        }
        Serial.println(visible ? F("Configured hotspot visible: YES") : F("Configured hotspot visible: NO"));
      }
      WiFi.scanDelete();
      Serial.println(F("Wi-Fi timeout. Check 2.4 GHz network and credentials; press RESET to retry."));
      return;
    }
    delay(250);
  }
  Serial.println(F("Wi-Fi connected."));

  configTime(0, 0, "pool.ntp.org", "time.nist.gov");
  Serial.println(F("Synchronising clock for HTTPS (up to 30 seconds)..."));
  started = millis();
  while (time(nullptr) < 1704067200) {
    if (millis() - started >= 30000UL) {
      Serial.println(F("Clock timeout. Check internet/NTP access; press RESET to retry."));
      return;
    }
    delay(250);
  }
  secureClient.setTrustAnchors(&telegramCertificate);
  secureClient.setTimeout(15000);

  Serial.println(F("Sending one Telegram test message..."));
  StaticJsonDocument<256> payload;
  payload["chat_id"] = CHAT_ID;
  payload["text"] = "Kitchen assistant: ESP8266 Telegram connection test successful.";
  // The high-level sendMessage retries; make one request to avoid duplicate sends.
  String response = bot.sendPostToTelegram(bot.buildCommand("sendMessage"), payload.as<JsonObject>());
  bool sent = bot.checkForOkResponse(response);
  secureClient.stop();
  if (sent) {
    Serial.println(F("PASS: Telegram accepted the test message. Check your private chat."));
  } else {
    Serial.println(F("FAILED: No success confirmation. Check internet, token, chat ID and TLS certificate."));
    Serial.println(F("Check the chat before pressing RESET: an unconfirmed send may still have arrived."));
  }
}

void loop() {
  delay(10);
}
