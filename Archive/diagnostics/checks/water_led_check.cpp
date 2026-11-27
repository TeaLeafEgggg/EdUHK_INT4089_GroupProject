#include <cassert>
#include <cstddef>
#include <string>

#define F(value) value
constexpr int A0 = 14, OUTPUT = 1, HIGH = 1, LOW = 0;
int sensorReading = 0;
bool ledLit = false;

void pinMode(int pin, int mode) { assert(pin == 6 && mode == OUTPUT); }
void digitalWrite(int pin, int value) { assert(pin == 6); ledLit = value == HIGH; }
int analogRead(int pin) { assert(pin == A0); return sensorReading; }
void delay(unsigned long) {}

struct SerialStub {
  std::string input;
  std::size_t position = 0;
  void begin(int baud) { assert(baud == 9600); }
  bool available() { return position < input.size(); }
  int read() { return input[position++]; }
  template<class T> void print(T) {}
  template<class T> void println(T) {}
} Serial;

#include "../water_led_test/water_led_test.ino"

void step(int value, const char* command, bool expected) {
  sensorReading = value;
  Serial.input = command;
  Serial.position = 0;
  loop();
  assert(ledLit == expected);
}

int main() {
  setup();
  step(400, "", false);       // Stay off until both points are captured.
  step(40, "c\r\n", false);
  step(120, "w\n", true);
  step(80, "", true);         // Keep the previous state between thresholds.
  step(40, "", false);
  step(80, "", false);
  step(120, "", true);
  step(120, "c\n", false);    // Identical points are not a valid calibration.

  step(300, "c\n", false);    // Handle sensors whose reading falls as water rises.
  step(180, "w\n", true);
  step(240, "", true);
  step(300, "", false);
  step(240, "", false);
  step(180, "", true);
}
