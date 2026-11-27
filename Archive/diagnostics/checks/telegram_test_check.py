"""Run the real sketch with simulated Wi-Fi/TLS/Telegram boundaries; sends nothing."""
from pathlib import Path
import subprocess
import tempfile

sketch = Path(__file__).resolve().parents[1] / "telegram_test" / "telegram_test.ino"
assert sketch.is_file(), "Telegram test sketch has not been implemented"

fake_hardware = r'''
#pragma once
#include <cstdint>
#include <climits>
#include <cstring>
#include <sstream>
#include <string>
#include <map>
#include <ctime>
#define F(value) value
#define WIFI_STA 1
#define WL_CONNECTED 3
inline unsigned long ticks = 0;
inline bool wifiAvailable = true, clockAvailable = true, sendOk = true;
inline bool partialResponse = false;
inline bool trusted = false, clockStarted = false;
inline int wifiCalls = 0, sends = 0;
inline int scanCount = 1, scanCalls = 0;
inline std::string destination, message;
inline unsigned long millis() { return ticks; }
inline void delay(unsigned long ms) { ticks += ms; }
inline time_t fakeTime(time_t*) { return clockAvailable && clockStarted ? 1800000000 : 0; }
inline void configTime(long, int, const char*, const char*) { clockStarted = true; }
struct SerialType {
  std::ostringstream output;
  void begin(int) {}
  void println() { output << '\n'; }
  template<class T> void println(T value) { output << value << '\n'; }
  template<class T> void print(T value) { output << value; }
};
inline SerialType Serial;
struct WiFiType {
  void persistent(bool) {}
  void mode(int) {}
  void begin(const char*, const char*) { ++wifiCalls; }
  int status() { return wifiAvailable ? WL_CONNECTED : 0; }
  int scanNetworks() { ++scanCalls; return scanCount; }
  std::string SSID(int) { return "test-network"; }
  void scanDelete() {}
};
inline WiFiType WiFi;
namespace BearSSL {
struct X509List { X509List(const char*) {} };
struct WiFiClientSecure {
  void setTrustAnchors(X509List*) { trusted = true; }
  void setTimeout(unsigned long) {}
  void stop() {}
};
}
inline const char* TELEGRAM_CERTIFICATE_ROOT = "test trust anchor";
using String = std::string;
#ifdef INT4089_REAL_JSON
#include <ArduinoJson.h>
#else
using JsonObject = std::map<std::string, const char*>;
template<int Capacity> struct StaticJsonDocument {
  JsonObject values;
  const char*& operator[](const char* key) { return values[key]; }
  template<class T> T as() { return values; }
};
struct UniversalTelegramBot {
  UniversalTelegramBot(const char*, BearSSL::WiFiClientSecure&) {}
  // The real high-level send retries after failure; keep this regression trap.
  bool sendMessage(const char* chat, const char* text, const char*) {
    sends += sendOk ? 1 : 2; destination = chat; message = text;
    return sendOk;
  }
  String buildCommand(const char* method) { return String("bot-test/") + method; }
  String sendPostToTelegram(const String& command, JsonObject payload) {
    if (command != "bot-test/sendMessage") throw "Wrong Telegram method";
    ++sends; destination = payload["chat_id"]; message = payload["text"];
    return sendOk ? (partialResponse ? "{\"ok\":" : "ok") : "";
  }
  bool checkForOkResponse(const String& response) { return response == "ok"; }
};
#endif
'''

test_main = r'''
#include <cassert>
#include <iostream>
#include "fake_hardware.h"
#define time fakeTime
#include "telegram_test.ino"
#undef time
int main(int argc, char** argv) {
  std::string scenario = argv[1];
  if (scenario == "wifi-timeout") wifiAvailable = false;
  if (scenario == "clock-timeout") clockAvailable = false;
  if (scenario == "send-failure") sendOk = false;
  if (scenario == "wifi-rollover") { ticks = ULONG_MAX - 1000; wifiAvailable = false; }
  if (scenario == "hotspot-hidden") { wifiAvailable = false; scanCount = 0; }
  if (scenario == "scan-failure") { wifiAvailable = false; scanCount = -2; }
  unsigned long started = ticks;
  setup();
  unsigned long elapsed = ticks - started;
  for (int i = 0; i < 100; ++i) loop();
  std::string log = Serial.output.str();
  if (scenario == "placeholder") {
    assert(wifiCalls == 0 && sends == 0);
    assert(log.find("secrets.h") != std::string::npos);
  } else if (scenario == "wifi-timeout" || scenario == "wifi-rollover" ||
             scenario == "hotspot-hidden" || scenario == "scan-failure") {
    assert(sends == 0 && !clockStarted);
    assert(elapsed >= 45000 && elapsed <= 46000);
    assert(log.find("Wi-Fi timeout") != std::string::npos);
    assert(scanCalls == 1);
    const char* diagnostic = scanCount < 0 ? "Hotspot scan failed" :
        scanCount == 0 ? "Configured hotspot visible: NO" : "Configured hotspot visible: YES";
    assert(log.find(diagnostic) != std::string::npos);
  } else if (scenario == "clock-timeout") {
    assert(sends == 0);
    assert(elapsed >= 30000 && elapsed <= 31000);
    assert(log.find("Clock timeout") != std::string::npos);
  } else {
    assert(sends == 1 && trusted && clockStarted);
    assert(destination == "123456789");
    assert(message.find("Kitchen assistant") != std::string::npos);
    assert(log.find(sendOk ? "PASS" : "FAILED") != std::string::npos);
  }
  assert(log.find("test-token") == std::string::npos);
  assert(log.find("test-password") == std::string::npos);
  std::cout << "PASS: " << scenario << '\n';
}
'''

def main():
    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory)
        (work / "fake_hardware.h").write_text(fake_hardware)
        for header in ("ESP8266WiFi.h", "WiFiClientSecure.h", "UniversalTelegramBot.h"):
            (work / header).write_text('#include "fake_hardware.h"\n')
        (work / "telegram_test.ino").write_text(sketch.read_text())
        (work / "check.cpp").write_text(test_main)
        for placeholder in (False, True):
            ssid = "YOUR_WIFI_NAME" if placeholder else "test-network"
            (work / "secrets.h").write_text(
                f'const char* WIFI_SSID = "{ssid}";\n'
                'const char* WIFI_PASSWORD = "test-password";\n'
                'const char* BOT_TOKEN = "test-token";\n'
                'const char* CHAT_ID = "123456789";\n'
            )
            subprocess.run(["c++", "-std=c++17", "-I", str(work), str(work / "check.cpp"),
                            "-o", str(work / "check")], check=True)
            scenarios = ["placeholder"] if placeholder else [
                "success", "wifi-timeout", "clock-timeout", "send-failure", "wifi-rollover",
                "hotspot-hidden", "scan-failure"
            ]
            for scenario in scenarios:
                subprocess.run([str(work / "check"), scenario], check=True, timeout=5)


if __name__ == "__main__":
    main()
