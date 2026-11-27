#include <cassert>
#include <iostream>
#include "../fridge_gateway/FridgeState.h"

int main() {
  using namespace fridge;
  const int64_t now = 1800000000;
  State state;
  assert(begin(state, now));
  assert(!canAnswer(state, true, 101)); // No question has been delivered yet.
  state.promptId = 100;
  assert(!canAnswer(state, false, 101));
  assert(!canAnswer(state, true, 99) && !canAnswer(state, true, 100));
  assert(canAnswer(state, true, 101));
  assert(!begin(state, now+10)); // Opening again must not overwrite pending food.
  assert(!accept(state, "/list") && !accept(state, "/cancel"));
  assert(!accept(state, "") && !accept(state, "a\nb"));
  assert(accept(state, "Milk"));
  assert(state.promptId == 0 && !canAnswer(state, true, 102));
  assert(state.stage == EXPIRY && !begin(state, now+20));
  assert(!accept(state, "/remove 1"));
  assert(!accept(state, "2026-02-29"));
  assert(!accept(state, "2026-11-31"));
  assert(!accept(state, "26-12-01"));
  assert(validDate("2028-02-29") && !validDate("2100-02-29"));
  assert(validDate("2000-02-29") && !validDate("2026-00-01"));
  assert(!validDate("2026-01-00") && !validDate("2026-13-01"));
  // Simulated durable reload of a pending conversation.
  State restored = state;
  assert(restored.stage == EXPIRY && !strcmp(restored.pending.name, "Milk"));
  assert(accept(restored, "2026-12-01"));
  assert(restored.stage == IDLE && restored.count == 1);
  assert(!canAnswer(restored, true, 999));
  assert(restored.foods[0].storedAt == now);
  assert(!due(restored.foods[0], now-1));
  assert(!due(restored.foods[0], now+WEEK)); // Strictly more than a week.
  assert(due(restored.foods[0], now+WEEK+1));
  restored.foods[0].notified = true;
  assert(!due(restored.foods[0], now+WEEK*2));
  Food unknownClock;
  assert(!due(unknownClock, now));
  while (restored.count < CAPACITY) {
    assert(begin(restored, now));
    assert(accept(restored, "Rice") && accept(restored, "2026-12-02"));
  }
  assert(!begin(restored, now));
  assert(!remove(restored, 0) && !remove(restored, CAPACITY+1));
  assert(remove(restored, 1));
  assert(!strcmp(restored.foods[0].name, "Rice"));
  assert(begin(restored, now));
  assert(!remove(restored, 1));
  std::cout << "PASS: gated conversation, real dates/leap years, pending recovery, 7-day boundary, one-off reminders, capacity and removal\n";
}
