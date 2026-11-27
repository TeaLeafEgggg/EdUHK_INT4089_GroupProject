#include <cassert>
#include <cstdint>
#include <sstream>
#include <string>

std::uint32_t clockMs = 0;
unsigned long millis() { return clockMs; }
struct SerialStub {
  std::ostringstream output;
  void begin(int) {}
  template <class T> void print(T value) { output << value; }
  template <class T> void println(T value) { output << value << '\n'; }
} Serial;

#include "../countdown_test/countdown_test.ino"

int main() {
  clockMs = 100;
  setup();
  loop();
  assert(Serial.output.str().find("Remaining: 60 s") != std::string::npos);
  clockMs = 29100;
  loop();
  assert(Serial.output.str().find("30-second reminder") == std::string::npos);
  clockMs = 31100;  // A skipped update must not lose the reminder.
  loop();
  assert(Serial.output.str().find("30-second reminder") != std::string::npos);
  const auto afterReminder = Serial.output.str();
  loop();
  assert(Serial.output.str() == afterReminder);
  clockMs = 60100;
  loop();
  assert(Serial.output.str().find("Remaining: 0 s") != std::string::npos);
  assert(Serial.output.str().find("60-second alarm point") != std::string::npos);
  const auto finishedOutput = Serial.output.str();
  clockMs = 120100;
  loop();
  assert(Serial.output.str() == finishedOutput);
}
