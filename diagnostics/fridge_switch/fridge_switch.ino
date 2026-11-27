#include <SoftwareSerial.h>
#include <EEPROM.h>

// Passive contact: D2 to GND, closed with magnet near. See README before wiring.
const uint8_t DOOR_PIN = 2;
const uint8_t BUZZER_PIN = 3;
const uint32_t PHONE_DELAY = 30000UL;
uint32_t doorDelay = 60000UL;
const uint32_t MANUAL_DURATION = 3000UL;
const uint8_t MUTED_MARKER = 0xB7;
bool muted;
SoftwareSerial espLink(8, 9);  // Keep D8 free; D9 -> existing divider -> ESP D5.
bool sampledOpen, doorOpen, phoneDue;
uint32_t changedAt, openedAt, lastSnapshot, lastUsbSnapshot;
bool manualPending, manualSounding, buzzerActive;
uint32_t manualScheduledAt, manualDelay, manualSoundAt;
char buzzerCommand[7];
uint8_t buzzerCommandLength;
bool buzzerCommandOverflow;

void applyCommand(uint32_t now) {
  if (buzzerCommandOverflow || buzzerCommandLength < 3 || buzzerCommand[1] != ':') return;
  uint32_t value = 0;
  for (uint8_t i = 2; i < buzzerCommandLength; ++i) {
    char digit = buzzerCommand[i];
    if (digit < '0' || digit > '9') return;
    value = value * 10 + (digit - '0');
  }
  switch (buzzerCommand[0]) {
    case 'W':  // Seconds the door must remain open before buzzing.
      if (value >= 10 && value <= 60) doorDelay = value * 1000UL;
      break;
    case 'M':
      if (value <= 1) {
        muted = value == 1;
        EEPROM.update(EEPROM.length() - 1, muted ? MUTED_MARKER : 0);
        if (muted) {
          manualPending = false;
          manualSounding = false;
        }
      }
      break;
    case 'B':  // Manual countdown in seconds.
      if (!muted && !manualPending && value >= 1 && value <= 60) {
        manualScheduledAt = now;
        manualDelay = value * 1000UL;
        manualPending = true;
      }
      break;
  }
}

void readUsbCommands(uint32_t now) {
  while (Serial.available() > 0) {
    const char next = Serial.read();
    if (next == '\r') continue;
    if (next == '\n') {
      applyCommand(now);
      buzzerCommandLength = 0;
      buzzerCommandOverflow = false;
    } else if (buzzerCommandLength < sizeof buzzerCommand) {
      buzzerCommand[buzzerCommandLength++] = next;
    } else {
      buzzerCommandOverflow = true;
    }
  }
}

void report() {
  espLink.println(doorOpen ? "D:O" : "D:C");
}

void reportUsb(uint32_t now) {
  Serial.print(F("W:")); Serial.println(doorDelay / 1000UL);
  Serial.println(muted ? F("M:1") : F("M:0"));
  Serial.println(buzzerActive ? F("B:BUZZING") : F("B:IDLE"));
  Serial.println(!doorOpen ? "D:C" : phoneDue ? "D:30" : "D:O");
  lastUsbSnapshot = now;
}

void setup() {
  muted = EEPROM.read(EEPROM.length() - 1) == MUTED_MARKER;
  Serial.begin(9600);
  espLink.begin(9600);
  pinMode(DOOR_PIN, INPUT_PULLUP);
  pinMode(LED_BUILTIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW);
  sampledOpen = doorOpen = digitalRead(DOOR_PIN) == HIGH;
  digitalWrite(LED_BUILTIN, doorOpen ? LOW : HIGH);  // Magnet near: L on.
  changedAt = openedAt = lastSnapshot = millis();
  report();
  reportUsb(lastSnapshot);
}
void loop() {
  uint32_t now = millis();
  readUsbCommands(now);
  bool reading = digitalRead(DOOR_PIN) == HIGH;
  if (reading != sampledOpen) { sampledOpen = reading; changedAt = now; }
  const bool doorChanged = sampledOpen != doorOpen && now - changedAt >= 50UL;
  if (doorChanged) {
    doorOpen = sampledOpen;
    digitalWrite(LED_BUILTIN, doorOpen ? LOW : HIGH);
    if (doorOpen) openedAt = now;
    phoneDue = false;
    report();
  }
  // Snapshots let the ESP recover current door state after a restart/network wait.
  if (now - lastSnapshot >= 5000UL) { lastSnapshot = now; report(); }
  const uint32_t elapsed = now - openedAt;
  const bool phoneBecameDue = doorOpen && !phoneDue && elapsed >= PHONE_DELAY;
  if (phoneBecameDue) phoneDue = true;
  const bool doorAlarm = !muted && doorOpen && elapsed >= doorDelay;
  const bool doorPulse = doorAlarm && (elapsed - doorDelay) % 1000UL < 200UL;
  if (manualPending && now - manualScheduledAt >= manualDelay) {
    manualPending = false;
    manualSounding = true;
    manualSoundAt = now;
    Serial.println(F("B:DONE"));
  }
  const uint32_t manualElapsed = now - manualSoundAt;
  if (manualSounding && manualElapsed >= MANUAL_DURATION) manualSounding = false;
  const bool manualPulse = manualSounding && manualElapsed % 1000UL < 200UL;
  digitalWrite(BUZZER_PIN, doorPulse || manualPulse ? HIGH : LOW);
  const bool active = doorAlarm || manualSounding;
  if (active != buzzerActive || doorChanged || phoneBecameDue || now - lastUsbSnapshot >= 1000UL) {
    buzzerActive = active;
    reportUsb(now);
  }
}
