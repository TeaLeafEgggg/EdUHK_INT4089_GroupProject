#include <ESP8266WiFi.h>
#include <WiFiClientSecure.h>
#include <ESP8266HTTPClient.h>
#include <ArduinoJson.h>
#include <TelegramCertificate.h>
#include <SoftwareSerial.h>
#include <LittleFS.h>
#include <time.h>
#include "FridgeState.h"
#include "secrets.h"

SoftwareSerial eventInput(D5, -1);
BearSSL::X509List certificate(TELEGRAM_CERTIFICATE_ROOT);
BearSSL::WiFiClientSecure secureClient;
fridge::State state;
bool storageReady = false, doorKnown = false, doorOpen = false;
bool doorWarningSent = false;
unsigned long openedAt = 0, lastPoll = 0, lastReminder = 0, lastPrompt = 0;
unsigned long lastDoorAttempt = 0;
char line[24];
unsigned lineSize = 0;
bool discardLine = false;

bool networkReady() {
  return WiFi.status() == WL_CONNECTED && time(nullptr) >= 1704067200;
}

void writeFood(JsonObject object, const fridge::Food& food) {
  object["name"] = food.name;
  object["expiry"] = food.expiry;
  object["storedAt"] = food.storedAt;
  object["notified"] = food.notified;
}

bool saveState() {
  DynamicJsonDocument doc(6144);
  doc["version"] = 1;
  doc["stage"] = int(state.stage);
  doc["offset"] = state.offset;
  doc["promptId"] = state.promptId;
  writeFood(doc.createNestedObject("pending"), state.pending);
  JsonArray foods = doc.createNestedArray("foods");
  for (unsigned i = 0; i < state.count; ++i) writeFood(foods.createNestedObject(), state.foods[i]);
  File file = LittleFS.open("/fridge.tmp", "w");
  bool ok = file && !doc.overflowed() && serializeJson(doc, file) == measureJson(doc);
  if (file) { file.flush(); file.close(); }
  // LittleFS rename replaces the destination atomically; keep the prior file on failure.
  ok = ok && LittleFS.rename("/fridge.tmp", "/fridge.json");
  if (!ok) {
    storageReady = false;  // Do not acknowledge more input after an unsaved change.
    Serial.println(F("STORAGE ERROR: bot paused; local Uno alarm still runs."));
  }
  return ok;
}

bool readFood(JsonObject object, fridge::Food& food, bool complete) {
  const char* name = object["name"];
  const char* expiry = object["expiry"];
  if (!name || !expiry || strlen(name) > 64 || strlen(expiry) > 10 ||
      !object["storedAt"].is<int64_t>() || !object["notified"].is<bool>()) return false;
  if (complete && (!name[0] || !fridge::validDate(expiry))) return false;
  strcpy(food.name, name);
  strcpy(food.expiry, expiry);
  food.storedAt = object["storedAt"].as<int64_t>();
  food.notified = object["notified"].as<bool>();
  return food.storedAt >= 0;
}

bool loadState() {
  if (!LittleFS.exists("/fridge.json")) return saveState();
  File file = LittleFS.open("/fridge.json", "r");
  DynamicJsonDocument doc(6144);
  if (!file || deserializeJson(doc, file) || doc["version"] != 1 ||
      !doc["stage"].is<int>() || !doc["foods"].is<JsonArray>() ||
      !doc["offset"].is<int64_t>() || !doc["promptId"].is<int64_t>()) return false;
  int stage = doc["stage"];
  if (stage < fridge::IDLE || stage > fridge::EXPIRY || doc["foods"].size() > fridge::CAPACITY) return false;
  state.stage = fridge::Stage(stage);
  state.offset = doc["offset"];
  state.promptId = doc["promptId"];
  if (state.offset < 0 || state.promptId < 0 || !readFood(doc["pending"], state.pending, false)) return false;
  for (JsonObject food : doc["foods"].as<JsonArray>())
    if (!readFood(food, state.foods[state.count++], true)) return false;
  if (state.stage != fridge::IDLE && state.count == fridge::CAPACITY) return false;
  return state.stage != fridge::EXPIRY || state.pending.name[0];
}

bool api(const char* method, JsonDocument& payload, JsonDocument& reply, JsonDocument& filter, String& response) {
  if (!networkReady()) return false;
  HTTPClient request;
  request.setTimeout(6000);
  if (!request.begin(secureClient, String("https://api.telegram.org/bot") + BOT_TOKEN + "/" + method)) return false;
  request.addHeader("Content-Type", "application/json");
  String body;
  serializeJson(payload, body);
  int status = request.POST(body);
  // Read the full body, then release TLS buffers before parsing.
  if (status == HTTP_CODE_OK) response = request.getString();
  request.end();
  secureClient.stop();
  bool ok = status == HTTP_CODE_OK &&
    !deserializeJson(reply, response, DeserializationOption::Filter(filter)) && reply["ok"] == true;
  if (!ok) Serial.println(F("Telegram request unconfirmed; check network/webhook/other pollers."));
  return ok;
}

int64_t sendText(const String& text, bool question = false) {
  DynamicJsonDocument payload(4608);
  payload["chat_id"] = CHAT_ID;
  payload["text"] = text;
  if (question) {
    payload["reply_markup"]["force_reply"] = true;
    payload["reply_markup"]["selective"] = true;
  }
  StaticJsonDocument<192> reply, filter;
  filter["ok"] = true;
  filter["result"]["message_id"] = true;
  String response;
  return api("sendMessage", payload, reply, filter, response) ? reply["result"]["message_id"].as<int64_t>() : 0;
}

String question() {
  if (state.stage == fridge::NAME)
    return "Fridge opened. What food are you putting in? Send its name (up to 64 UTF-8 bytes). Please finish this entry before other bot commands.";
  return String("What is the expiry date for ") + state.pending.name + "? Send YYYY-MM-DD, for example 2026-12-01. This is required to finish the entry.";
}

void prompt() {
  lastPrompt = millis();
  int64_t id = sendText(question(), true);
  if (id) { state.promptId = id; saveState(); }
}

void beginEntry() {
  if (state.stage != fridge::IDLE) return;
  if (!fridge::begin(state, networkReady() ? int64_t(time(nullptr)) : 0)) return;
  saveState();
}

void handleEvent(const char* event) {
  bool open = strcmp(event, "D:O") == 0;
  if (!open && strcmp(event, "D:C") != 0) return;
  if (!doorKnown || open != doorOpen) {
    doorKnown = true;
    doorOpen = open;
    doorWarningSent = false;
    if (open) { openedAt = millis(); if (storageReady) beginEntry(); }
  }
}

void readEvents() {
  while (eventInput.available()) {
    int value = eventInput.read();
    if (value == '\r') continue;
    if (value == '\n') {
      if (!discardLine) { line[lineSize] = 0; handleEvent(line); }
      lineSize = 0;
      discardLine = false;
    } else if (!discardLine) {
      if (value < 32 || value > 126 || lineSize == sizeof(line)-1) discardLine = true;
      else line[lineSize++] = char(value);
    }
  }
}

String normalCommand(const String& text) {
  if (text == "/add") {
    if (state.count == fridge::CAPACITY) return "Food list full (16 items). Use /remove NUMBER first.";
    beginEntry();
    return "";
  }
  if (text == "/list") {
    String result = "Food in the fridge:\n";
    for (unsigned i = 0; i < state.count; ++i) {
      result += String(i+1) + ". " + state.foods[i].name + " | expiry " + state.foods[i].expiry + "\n";
    }
    return state.count ? result : "No food recorded.";
  }
  if (text.startsWith("/remove ")) {
    String number = text.substring(8);
    bool digits = number.length() > 0 && number.length() <= 2;
    for (unsigned i = 0; i < number.length(); ++i) digits &= number[i] >= '0' && number[i] <= '9';
    if (digits && fridge::remove(state, number.toInt())) return "Removed. Use /list for the updated item numbers.";
    return "Use /list, then /remove NUMBER for food that has been taken out.";
  }
  if (state.count == fridge::CAPACITY) return "Food list full (16 items). Use /list then /remove NUMBER before adding food.";
  return "Open the fridge to record food, or use /add. Send /list to view food; /remove NUMBER when food is taken out. Reminders are sent once per item after more than 7 days of storage.";
}

void poll() {
  StaticJsonDocument<256> payload;
  payload["offset"] = state.offset;
  payload["limit"] = 1;
  payload["timeout"] = 1;
  payload["allowed_updates"][0] = "message";
  StaticJsonDocument<384> filter;
  filter["ok"] = true;
  JsonObject wanted = filter["result"].createNestedObject();
  wanted["update_id"] = true;
  wanted["message"]["message_id"] = true;
  wanted["message"]["chat"]["id"] = true;
  wanted["message"]["chat"]["type"] = true;
  wanted["message"]["text"] = true;
  StaticJsonDocument<1024> reply;
  String body;
  if (!api("getUpdates", payload, reply, filter, body) || !reply["result"].is<JsonArray>()) return;
  for (JsonObject update : reply["result"].as<JsonArray>()) {
    if (!update["update_id"].is<int64_t>()) continue;
    int64_t next = update["update_id"].as<int64_t>() + 1;
    if (next <= state.offset) continue;
    String response;
    JsonObject message = update["message"];
    String chat = message["chat"]["id"].as<String>();
    if (chat == CHAT_ID && message["chat"]["type"] == "private") {
      String text = message["text"] | "";
      text.trim();
      if (state.stage != fridge::IDLE) {
        // Never consume messages sent before this stage's actual question.
        if (fridge::canAnswer(state, true, message["message_id"].as<int64_t>())) {
          if (fridge::accept(state, text.c_str())) {
            if (state.stage == fridge::IDLE) response = "Saved food and expiry date. I will remind you once it has been stored for more than 7 days. You can use other bot commands now.";
          } else response = state.stage == fridge::NAME ? "Please send a food name (1-64 UTF-8 bytes). Other commands must wait." : "Please send a real date in YYYY-MM-DD format. Other commands must wait.";
        }
      } else response = normalCommand(text);
    }
    state.offset = next;
    // Release incoming message storage before another TLS request on the ESP.
    reply.clear();
    body = String();
    if (!storageReady || !saveState()) return;
    if (response.length()) sendText(response);
    return;  // limit=1; do not advance an iterator after clearing its document.
  }
}

void reminders() {
  // One delivery per scan avoids flooding when several items become due together.
  for (unsigned i = 0; i < state.count; ++i) {
    if (!fridge::due(state.foods[i], time(nullptr))) continue;
    String text = String("Storage reminder: ") + state.foods[i].name + " has been in the fridge for more than 7 days. Recorded expiry date: " + state.foods[i].expiry + ".";
    if (sendText(text)) { state.foods[i].notified = true; saveState(); }
    return;
  }
}

void setup() {
  Serial.begin(115200);
  eventInput.begin(9600);
  Serial.println(F("Fridge food gateway: D5 event input, private Telegram chat."));
  if (!WIFI_SSID[0] || !BOT_TOKEN[0] || !CHAT_ID[0] ||
      String(WIFI_SSID) == "YOUR_WIFI_NAME" || String(BOT_TOKEN) == "YOUR_BOT_TOKEN" ||
      String(CHAT_ID) == "YOUR_CHAT_ID" || CHAT_ID[0] == '-') {
    Serial.println(F("Set credentials and a private chat ID in secrets.h."));
    return;
  }
  // Avoid silently formatting existing records if mounting fails.
  LittleFSConfig config;
  config.setAutoFormat(false);
  LittleFS.setConfig(config);
  storageReady = LittleFS.begin();
  if (storageReady) storageReady = loadState();
  if (!storageReady) {
    Serial.println(F("Filesystem unavailable/invalid. Initialise LittleFS explicitly for first use; do not erase existing food records."));
    return;
  }
  secureClient.setTrustAnchors(&certificate);
  secureClient.setTimeout(6000);
  WiFi.persistent(false);
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  configTime(0, 0, "pool.ntp.org", "time.nist.gov");
  Serial.println(F("Waiting for network/time without blocking local Uno alarms."));
}

void loop() {
  readEvents();
  if (!storageReady || !networkReady()) { delay(1); return; }
  if (state.stage != fridge::IDLE && state.pending.storedAt == 0) {
    state.pending.storedAt = time(nullptr);
    if (!saveState()) return;
  }
  // Normal bot commands are gated; door warnings and storage reminders are independent.
  if (doorOpen && !doorWarningSent && millis()-openedAt >= 30000UL && millis()-lastDoorAttempt >= 30000UL) {
    lastDoorAttempt = millis();
    doorWarningSent = sendText("Fridge door has been open for at least 30 seconds. Please close it.") > 0;
    readEvents();
  }
  if (storageReady && state.stage != fridge::IDLE && state.promptId == 0 &&
      (lastPrompt == 0 || millis()-lastPrompt >= 10000UL)) prompt();
  if (millis()-lastPoll >= 3000UL && storageReady) { lastPoll = millis(); poll(); }
  readEvents();
  if (millis()-lastReminder >= 60000UL && storageReady) { lastReminder = millis(); reminders(); }
  delay(1);
}
