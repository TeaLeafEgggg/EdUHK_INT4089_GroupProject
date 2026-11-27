// Uno R3: sensor S -> A0, + -> 3.3V, - -> GND.
// D6 -> 330 ohm (or 1 kOhm) resistor -> LED long leg; short leg -> GND.
// Serial Monitor (9600 baud): c at the lower water level, w at the warning level.

const int ledPin = 6;
int clearReading = -1;
int warningReading = -1;
bool ledOn = false;

void setup() {
  pinMode(ledPin, OUTPUT);
  Serial.begin(9600);
  digitalWrite(ledPin, HIGH);
  delay(1000);
  digitalWrite(ledPin, LOW);
  Serial.println(F("Water + LED test: send c at the clear level, then w at the warning level."));
}

void loop() {
  int total = 0;
  for (int sample = 0; sample < 8; ++sample) {
    total += analogRead(A0);
    delay(10);
  }
  int reading = total / 8;

  while (Serial.available()) {
    int command = Serial.read();
    if (command == 'c') {
      clearReading = reading;
      Serial.print(F("Clear point saved: "));
    } else if (command == 'w') {
      warningReading = reading;
      Serial.print(F("Warning point saved: "));
    } else {
      continue;
    }
    Serial.println(reading);
    ledOn = false;
    if (clearReading == warningReading) {
      Serial.println(F("Both readings are the same. Re-record at two distinct water levels."));
    }
  }

  bool calibrated = clearReading >= 0 && warningReading >= 0 && clearReading != warningReading;
  if (!calibrated) {
    ledOn = false;
  } else {
    bool rises = warningReading > clearReading;
    if (rises ? reading >= warningReading : reading <= warningReading) ledOn = true;
    else if (rises ? reading <= clearReading : reading >= clearReading) ledOn = false;
  }
  digitalWrite(ledPin, ledOn ? HIGH : LOW);
  Serial.print(F("Water reading: "));
  Serial.print(reading);
  Serial.println(!calibrated ? F(" | Set c and w") : (ledOn ? F(" | LED ON") : F(" | LED OFF")));
  // shortcut: blocking sampling for this bench test; schedule it in the combined Uno sketch.
  delay(170);
}
