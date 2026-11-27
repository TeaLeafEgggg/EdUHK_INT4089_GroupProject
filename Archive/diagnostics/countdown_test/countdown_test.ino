unsigned long startedAt;
int lastRemaining = -1;
bool reminderPrinted = false;
bool finished = false;

void setup() {
  Serial.begin(9600);
  startedAt = millis();
  Serial.println("Countdown started. Press RESET to restart.");
}

void loop() {
  if (finished) return;

  unsigned long elapsed = millis() - startedAt;
  int remaining = elapsed >= 60000UL ? 0 : 60 - elapsed / 1000UL;

  if (remaining != lastRemaining) {
    Serial.print("Remaining: ");
    Serial.print(remaining);
    Serial.println(" s");
    lastRemaining = remaining;
  }

  if (elapsed >= 30000UL && !reminderPrinted) {
    Serial.println("30-second reminder: Telegram would be triggered here.");
    reminderPrinted = true;
  }

  if (elapsed >= 60000UL) {
    Serial.println("60-second alarm point: buzzer would start here.");
    finished = true;
  }
}
