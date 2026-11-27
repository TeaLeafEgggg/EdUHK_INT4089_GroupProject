#pragma once
#include <stdint.h>
#include <string.h>

// Shared with the offline check; no Arduino or network dependencies.
namespace fridge {
constexpr unsigned CAPACITY = 16;
constexpr int64_t WEEK = 7LL * 24 * 60 * 60;
enum Stage { IDLE, NAME, EXPIRY };
struct Food {
  char name[65] = {};
  char expiry[11] = {};
  int64_t storedAt = 0;
  bool notified = false;
};
struct State {
  Stage stage = IDLE;
  Food pending;
  Food foods[CAPACITY];
  unsigned count = 0;
  int64_t offset = 0;
  int64_t promptId = 0;
};
inline bool validDate(const char* text) {
  if (strlen(text) != 10 || text[4] != '-' || text[7] != '-') return false;
  for (int i = 0; i < 10; ++i)
    if (i != 4 && i != 7 && (text[i] < '0' || text[i] > '9')) return false;
  int year = (text[0]-'0')*1000 + (text[1]-'0')*100 + (text[2]-'0')*10 + text[3]-'0';
  int month = (text[5]-'0')*10 + text[6]-'0';
  int day = (text[8]-'0')*10 + text[9]-'0';
  if (year < 2000 || year > 2099 || month < 1 || month > 12) return false;
  const int days[] = {31,28,31,30,31,30,31,31,30,31,30,31};
  int maximum = days[month-1] + (month == 2 && year % 4 == 0);
  return day >= 1 && day <= maximum;
}
inline bool begin(State& state, int64_t now) {
  if (state.stage != IDLE || state.count >= CAPACITY) return false;
  state.pending = Food{};
  state.pending.storedAt = now;
  state.stage = NAME;
  state.promptId = 0;
  return true;
}
inline bool accept(State& state, const char* text) {
  if (!text[0] || text[0] == '/') return false;
  if (state.stage == NAME) {
    if (strlen(text) > 64) return false;
    for (const unsigned char* p = (const unsigned char*)text; *p; ++p)
      if (*p < 32 || *p == 127) return false;
    strcpy(state.pending.name, text);
    state.stage = EXPIRY;
    state.promptId = 0;
    return true;
  }
  if (state.stage != EXPIRY || !validDate(text) || state.count >= CAPACITY) return false;
  strcpy(state.pending.expiry, text);
  state.foods[state.count++] = state.pending;
  state.pending = Food{};
  state.stage = IDLE;
  state.promptId = 0;
  return true;
}
inline bool canAnswer(const State& state, bool targetPrivateChat, int64_t messageId) {
  return targetPrivateChat && state.stage != IDLE && state.promptId > 0 && messageId > state.promptId;
}
inline bool due(const Food& food, int64_t now) {
  return !food.notified && food.storedAt > 0 && now > food.storedAt && now - food.storedAt > WEEK;
}
inline bool remove(State& state, unsigned number) {
  if (state.stage != IDLE || number == 0 || number > state.count) return false;
  for (unsigned i = number; i < state.count; ++i) state.foods[i-1] = state.foods[i];
  state.foods[--state.count] = Food{};
  return true;
}
}  // namespace fridge
