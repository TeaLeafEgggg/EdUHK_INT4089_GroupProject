#include <LittleFS.h>

// Separate, deliberate first-use step. NEVER upload to a board with food records.
void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.println(F("First-use fridge storage initialiser."));
  Serial.println(F("Type INITIALISE EMPTY FRIDGE then Enter to erase and initialise LittleFS."));
  Serial.println(F("Do not proceed if this board already contains food records."));
}
void loop() {
  if (!Serial.available()) return;
  String command = Serial.readStringUntil('\n');
  command.trim();
  if (command != "INITIALISE EMPTY FRIDGE") return;
  Serial.println(LittleFS.format() ? F("Initialised. Upload fridge_gateway now.") : F("FAILED: LittleFS format unsuccessful."));
}
