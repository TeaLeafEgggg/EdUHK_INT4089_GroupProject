"""Exercise the actual Uno sketch at simulated hardware boundaries; no devices used."""
from pathlib import Path
import subprocess
import tempfile

source = Path(__file__).resolve().parents[1] / "fridge_switch/fridge_switch.ino"
fake = r'''
#pragma once
#include <cstdint>
#include <string>
#define F(x) x
#define HIGH 1
#define LOW 0
#define INPUT_PULLUP 2
#define OUTPUT 1
#define LED_BUILTIN 13
uint32_t ticks = 0;
int contact = LOW, buzzer = LOW, led = LOW, ledMode = 0;
unsigned long millis() { return ticks; }
int digitalRead(int) { return contact; }
void digitalWrite(int pin, int value) { if (pin == 3) buzzer = value; if (pin == LED_BUILTIN) led = value; }
void pinMode(int pin, int mode) { if (pin == LED_BUILTIN) ledMode = mode; }
struct Log {
  std::string text;
  std::string input;
  void begin(int) {}
  void print(const char* value) { text += value; }
  void println(unsigned long value) { text += std::to_string(value) + "\n"; }
  void println(const char* value) { text += std::string(value) + "\n"; }
  int available() { return input.size(); }
  int read() { char next = input.front(); input.erase(0, 1); return next; }
} Serial;
struct SoftwareSerial : Log { SoftwareSerial(int, int) {} };
'''
main = r'''
#include <cassert>
#include <iostream>
#include "fridge_switch.ino"
int main() {
  setup();
  assert(ledMode == OUTPUT && led == HIGH);
  assert(espLink.text == "D:C\n" && buzzer == LOW);
  assert(Serial.text == "W:60\nM:0\nB:IDLE\nD:C\n");
  // A 20 ms bounce must not create an opening.
  ticks = 100; contact = HIGH; loop();
  assert(led == HIGH);
  ticks = 120; contact = LOW; loop();
  ticks = 200; loop();
  assert(espLink.text == "D:C\n");
  contact = HIGH; ticks = 300; loop();
  ticks = 350; loop();
  assert(led == LOW);
  assert(doorOpen && espLink.text == "D:C\nD:O\n");
  ticks = 30349; loop();
  assert(Serial.text.find("D:30\n") == std::string::npos && buzzer == LOW);
  ticks = 30350; loop();
  assert(Serial.text.substr(Serial.text.size()-5) == "D:30\n" && buzzer == LOW);
  ticks = 60349; loop();
  assert(buzzer == LOW);
  ticks = 60350; loop();
  assert(buzzer == HIGH && buzzerActive);
  assert(Serial.text.find("B:BUZZING\nD:30\n") != std::string::npos);
  ticks = 60550; loop();
  assert(buzzer == LOW); // Distinct non-blocking pulse.
  contact = LOW; ticks = 61350; loop();
  assert(buzzer == HIGH);
  ticks = 61400; loop();
  assert(!doorOpen && buzzer == LOW && led == HIGH);
  assert(espLink.text.substr(espLink.text.size()-4) == "D:C\n");
  assert(Serial.text.substr(Serial.text.size()-4) == "D:C\n");
  // Snapshots recover state; elapsed arithmetic works across a 32-bit wrap.
  ticks = UINT32_MAX-1000; contact = HIGH; loop();
  ticks = UINT32_MAX-950; loop();
  ticks = 100; loop();
  assert(doorOpen && buzzer == LOW); // Wrap alone must not trigger the alarm.
  ticks = 59049; loop();
  assert(doorOpen && buzzer == HIGH);
  contact = LOW; ticks = 59100; loop();
  ticks = 59150; loop();
  assert(!doorOpen && buzzer == LOW);

  Serial.input = "B:600\nB:0\nB:61\nB:x\nB:";
  ticks = 60000; loop();
  assert(!manualPending && buzzer == LOW);
  Serial.input = "5\n"; ticks = 60001; loop();
  assert(manualPending && buzzer == LOW);
  Serial.input = "B:2\n"; ticks = 62000; loop();
  ticks = 65000; loop();
  assert(manualPending && buzzer == LOW && Serial.text.find("B:DONE\n") == std::string::npos);
  ticks = 65001; loop();
  assert(!manualPending && buzzer == HIGH && Serial.text.find("B:DONE\n") != std::string::npos);
  ticks = 65201; loop();
  assert(buzzer == LOW);
  ticks = 66001; loop();
  assert(buzzer == HIGH);
  ticks = 67999; loop(); assert(manualSounding);
  ticks = 68001; loop();
  assert(!manualSounding && buzzer == LOW && !buzzerActive);
  assert(Serial.text.substr(Serial.text.size()-11) == "B:IDLE\nD:C\n");

  Serial.input = "B:5\n"; ticks = UINT32_MAX-2000; loop();
  ticks = 2998; loop();
  assert(manualPending && buzzer == LOW);
  ticks = 2999; loop();
  assert(!manualPending && buzzer == HIGH);
  ticks = 13000; loop();
  Serial.input = "W:10\nW:9\nW:61\n"; contact = HIGH;
  ticks = 14000; loop(); ticks = 14050; loop();
  ticks = 24049; loop(); assert(!buzzerActive);
  ticks = 24050; loop(); assert(buzzerActive && buzzer == HIGH);
  ticks = 44050; loop(); assert(buzzerActive && buzzer == HIGH);
  Serial.input = "M:1\nB:1\n"; loop(); assert(muted && !manualPending && !buzzerActive && buzzer == LOW);
  setup(); assert(muted && led == LOW);
  ticks += 60001; loop(); assert(!buzzerActive);
  Serial.input = "M:0\n"; loop(); assert(!muted && buzzerActive);
  contact = LOW; loop(); ticks += 51; loop(); assert(!buzzerActive);
  std::cout << "PASS: Uno switch timing, 60 s door buzzer, 5 s manual alarm, and clock wrap\n";
}
'''
with tempfile.TemporaryDirectory() as folder:
    work = Path(folder)
    (work / "EEPROM.h").write_text("struct { unsigned char value=255; int length(){return 1024;} unsigned char read(int){return value;} void update(int,unsigned char n){value=n;} } EEPROM;")
    (work / "SoftwareSerial.h").write_text(fake)
    (work / "fridge_switch.ino").write_text(source.read_text())
    (work / "check.cpp").write_text(main)
    subprocess.run(["c++", "-std=c++17", "-I", str(work), str(work / "check.cpp"),
                    "-o", str(work / "check")], check=True)
    subprocess.run([str(work / "check")], check=True)
