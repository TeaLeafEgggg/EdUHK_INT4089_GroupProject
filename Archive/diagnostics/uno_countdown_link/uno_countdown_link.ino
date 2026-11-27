#include <SoftwareSerial.h>

// D8 is unused RX; D9 sends through the voltage divider to ESP8266 D5.
SoftwareSerial espLink(8, 9);
unsigned long startedAt;
int lastRemaining = -1;
bool reminderSent = false;
bool finished = false;

void setup() {
  Serial.begin(9600);
  espLink.begin(9600);
  startedAt = millis();
  lastRemaining = -1;
  reminderSent = false;
  finished = false;
  espLink.println("START");
  Serial.println(F("Countdown started. Press RESET to restart."));
}

void loop() {
  if (finished) return;
  unsigned long elapsed = millis() - startedAt;
  int remaining = elapsed >= 60000UL ? 0 : 60 - elapsed / 1000UL;
  if (remaining != lastRemaining) {
    Serial.print(F("Remaining: "));
    Serial.print(remaining);
    Serial.println(F(" s"));
    lastRemaining = remaining;
  }
  if (elapsed >= 30000UL && !reminderSent) {
    reminderSent = true;
    espLink.println("COUNTDOWN_30");
    Serial.println(F("30-second event sent to ESP8266."));
  }
  if (elapsed >= 60000UL) {
    finished = true;
    Serial.println(F("60-second endpoint. A local buzzer would start here."));
  }
}
