"""Run both real countdown/link sketches against simulated hardware boundaries."""
from pathlib import Path
import subprocess
import tempfile
from telegram_test_check import fake_hardware

root = Path(__file__).resolve().parents[1]
uno = root / "uno_countdown_link" / "uno_countdown_link.ino"
gateway = root / "countdown_gateway" / "countdown_gateway.ino"
assert uno.is_file() and gateway.is_file(), "Countdown/link sketches not implemented"

serial_stub = r'''
#pragma once
#include "fake_hardware.h"
#include <deque>
#define D5 14
struct SoftwareSerial {
  std::deque<int> incoming;
  std::string outgoing;
  SoftwareSerial(int, int) {}
  void begin(unsigned long) {}
  void println(const char* value) { outgoing += std::string(value) + "\r\n"; }
  int available() { return incoming.size(); }
  int read() { int value = incoming.front(); incoming.pop_front(); return value; }
  void receive(const std::string& bytes) { for (unsigned char c : bytes) incoming.push_back(c); }
};
'''

http_stub = r'''
#pragma once
#include "fake_hardware.h"
#include <cassert>
#define HTTP_CODE_OK 200
inline bool invalidJson = false, apiRejected = false;
inline int responseCode = 200;
struct HTTPClient {
  bool contentTypeSet = false;
  void setTimeout(int) {}
  bool begin(BearSSL::WiFiClientSecure&, const String& url) {
    assert(url == "https://api.telegram.org/bottest-token/sendMessage");
    return true;
  }
  void addHeader(const char* name, const char* value) {
    contentTypeSet = std::string(name) == "Content-Type" && std::string(value) == "application/json";
  }
  int POST(const String& body) {
    assert(contentTypeSet);
    ++sends;
    StaticJsonDocument<256> payload;
    assert(!deserializeJson(payload, body));
    destination = payload["chat_id"].as<std::string>();
    message = payload["text"].as<std::string>();
    return sendOk ? responseCode : 500;
  }
  String getString() {
    if (invalidJson) return "not JSON";
    if (apiRejected) return "{\"ok\":false}";
    return String("{\"ok\":true,\"result\":{\"text\":\"") + std::string(3000, 'x') + "\"}}";
  }
  void end() {}
};
'''

uno_main = r'''
#include <cassert>
#include <iostream>
#include "fake_hardware.h"
#include "SoftwareSerial.h"
#include "uno_countdown_link.ino"
int main(int argc, char** argv) {
  if (std::string(argv[1]) == "rollover") ticks = ULONG_MAX - 1000;
  unsigned long initial = ticks;
  setup();
  assert(espLink.outgoing == "START\r\n");
  loop();
  assert(Serial.output.str().find("Remaining: 60 s") != std::string::npos);
  ticks = initial + 29999; loop();
  assert(espLink.outgoing == "START\r\n");
  ticks = initial + 31000; loop();
  assert(espLink.outgoing == "START\r\nCOUNTDOWN_30\r\n");
  for (int i = 0; i < 10; ++i) loop();
  assert(espLink.outgoing == "START\r\nCOUNTDOWN_30\r\n");
  ticks = initial + 61000; loop();
  assert(Serial.output.str().find("Remaining: 0 s") != std::string::npos);
  const auto afterFinish = Serial.output.str();
  ticks = initial + 120000; loop();
  assert(Serial.output.str() == afterFinish);
  assert(espLink.outgoing == "START\r\nCOUNTDOWN_30\r\n");
  setup();
  ticks += 30000; loop();
  assert(espLink.outgoing == "START\r\nCOUNTDOWN_30\r\nSTART\r\nCOUNTDOWN_30\r\n");
  std::cout << "PASS: Uno " << argv[1] << '\n';
}
'''

gateway_main = r'''
#include <cassert>
#include <iostream>
#include "fake_hardware.h"
#define time fakeTime
#include "countdown_gateway.ino"
#undef time
void feed(const std::string& value) { eventInput.receive(value); loop(); }
int main(int argc, char** argv) {
  std::string scenario = argv[1];
  setup();
  assert(sends == 0);
  assert(Serial.output.str().find("READY") != std::string::npos);
  if (scenario == "normal-and-reset") {
    feed("START\r\nCOUNTDOWN_30\r\nCOUNTDOWN_30\r\n");
    assert(sends == 1);
    feed("START\nCOUNTDOWN_30\n"); assert(sends == 2);
  } else if (scenario == "fragmented") {
    feed("COUNTDOWN_3"); assert(sends == 0);
    feed("0\n"); assert(sends == 1);
  } else if (scenario == "malformed") {
    feed("UNKNOWN\n" + std::string(60, 'X') + "COUNTDOWN_30\n");
    feed(std::string("COUNTDOWN_30\0bad\n", 17));
    assert(sends == 0);
    feed("COUNTDOWN_30\n"); assert(sends == 1);
  } else if (scenario == "network-loss") {
    wifiAvailable = false; feed("COUNTDOWN_30\n"); assert(sends == 0);
    wifiAvailable = true; feed("COUNTDOWN_30\n"); assert(sends == 0);
    feed("START\nCOUNTDOWN_30\n"); assert(sends == 1);
  } else if (scenario == "clock-invalid") {
    clockAvailable = false; feed("COUNTDOWN_30\n"); assert(sends == 0);
    assert(Serial.output.str().find("SKIPPED") != std::string::npos);
    std::cout << "PASS: gateway clock-invalid\n";
    return 0;
  } else if (scenario == "send-failure") {
    sendOk = false; feed("COUNTDOWN_30\nCOUNTDOWN_30\n"); assert(sends == 1);
    assert(Serial.output.str().find("FAILED") != std::string::npos);
  } else if (scenario == "fragmented-response") {
    partialResponse = true; feed("COUNTDOWN_30\n"); assert(sends == 1);
    assert(Serial.output.str().find("PASS:") != std::string::npos);
  } else if (scenario == "invalid-json" || scenario == "api-rejected" || scenario == "http-error") {
    invalidJson = scenario == "invalid-json";
    apiRejected = scenario == "api-rejected";
    responseCode = scenario == "http-error" ? 500 : 200;
    feed("COUNTDOWN_30\nCOUNTDOWN_30\n"); assert(sends == 1);
    assert(Serial.output.str().find("FAILED") != std::string::npos);
  }
  for (int i = 0; i < 100; ++i) loop();
  assert(destination == "123456789");
  assert(message.find("30 seconds") != std::string::npos);
  assert(trusted && clockStarted);
  std::cout << "PASS: gateway " << scenario << '\n';
}
'''

with tempfile.TemporaryDirectory() as directory:
    work = Path(directory)
    (work / "fake_hardware.h").write_text(fake_hardware)
    for header in ("ESP8266WiFi.h", "WiFiClientSecure.h", "UniversalTelegramBot.h"):
        (work / header).write_text('#include "fake_hardware.h"\n')
    (work / "TelegramCertificate.h").write_text('#include "fake_hardware.h"\n')
    (work / "ESP8266HTTPClient.h").write_text(http_stub)
    (work / "SoftwareSerial.h").write_text(serial_stub)
    (work / "secrets.h").write_text(
        'const char* WIFI_SSID = "test-network";\n'
        'const char* WIFI_PASSWORD = "test-password";\n'
        'const char* BOT_TOKEN = "test-token";\n'
        'const char* CHAT_ID = "123456789";\n'
    )
    for source, main, scenarios in (
        (uno, uno_main, ("timing", "rollover")),
        (gateway, gateway_main, ("normal-and-reset", "fragmented", "malformed",
                                 "network-loss", "clock-invalid", "send-failure", "fragmented-response",
                                 "invalid-json", "api-rejected", "http-error")),
    ):
        (work / source.name).write_text(source.read_text())
        (work / "main.cpp").write_text(main)
        binary = work / "check"
        extra = []
        if source == gateway:
            json_include = Path.home() / "Documents/Arduino/libraries/ArduinoJson/src"
            assert json_include.is_dir(), "Install ArduinoJson 6.21.5 as described in the build guide"
            extra = ["-DINT4089_REAL_JSON", "-I", str(json_include)]
        subprocess.run(["c++", "-std=c++17", *extra, "-I", str(work), str(work / "main.cpp"),
                        "-o", str(binary)], check=True)
        for scenario in scenarios:
            subprocess.run([str(binary), scenario], check=True, timeout=5)
