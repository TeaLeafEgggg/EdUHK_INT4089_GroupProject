# Fridge food records and Telegram reminders

This is a **new standalone fridge prototype** for the existing Uno → ESP8266 connection. It is prepared separately from the working countdown diagnostics. It has not been uploaded or physically tested. It does not incorporate the water sensor, RFID or other project functions; merge those only after this fridge test passes.

## Agreed behaviour

1. A debounced opening of the magnetic contact starts one pending food entry.
2. Telegram asks for the food name, then its expiry date in `YYYY-MM-DD` format. Real calendar dates from 2000 to 2099 are accepted; past expiry dates are allowed and recorded as entered.
3. Both answers are required. `/start`, `/list`, `/add`, `/remove` and other normal bot actions cannot bypass an unfinished entry. Closing/reopening the contact does not reset or duplicate it. There is no cancel/skip command in this version.
4. Once saved, the record contains its food name, expiry date and storage-start timestamp. A reminder is due **strictly more than seven elapsed 24-hour days after storage starts**, regardless of expiry date. It is normally checked within the next minute while connected. Multiple due items are sent one per minute. A successfully confirmed reminder is sent only once per record.
5. Door alarms continue while answers are pending: a Telegram warning after 30 seconds continuously open, and a local Grove buzzer pulse after 60 seconds. Closing the door stops the local alarm. Neither these warnings nor storage reminders are blocked by the conversation.

Example:

```text
Bot: Fridge opened. What food are you putting in?
User: Milk
Bot: What is the expiry date for Milk? Send YYYY-MM-DD.
User: 2026-12-01
Bot: Saved food and expiry date...

[More than seven days after that opening]
Bot: Storage reminder: Milk has been in the fridge for more than 7 days.
     Recorded expiry date: 2026-12-01.
```

The expiry date is stored/displayed as a date, without a time zone conversion. The seven-day timer uses elapsed UTC seconds and is independent of the Mac's clock/time zone. An item added on 22 November at 14:00 Hong Kong time becomes due just after 29 November at 14:00 Hong Kong time.

## Boards and wiring

| Device | Sketch | Profile |
|---|---|---|
| Uno R3 | `../fridge_switch/fridge_switch.ino` | `arduino:avr:uno` |
| ESP8266 NodeMCU | `fridge_gateway.ino` plus `FridgeState.h` | `esp8266:esp8266:nodemcuv2` |
| ESP8266, first-use storage preparation only | `../fridge_storage_init/fridge_storage_init.ino` | Same ESP8266 profile/flash partition |

Use the existing **Uno D9 → three-resistor divider → ESP D5** connection documented in [the countdown test](../../docs/countdown-telegram-test.md). Keep a common ground and power the boards through their own USB inputs. Do not connect Uno D9 directly to ESP D5.

With power disconnected, connect the confirmed passive magnetic contact between **Uno D2 and GND**. This sketch assumes magnet near/door closed = contact connected/LOW; magnet far/door open = disconnected/HIGH. Invert `digitalRead(...) == HIGH` in both occurrences if your tested contact behaves oppositely. Connect the Grove buzzer to **D3**. Uno D8 is reserved and left unconnected. This firmware must not be uploaded to an existing integrated build without checking all pin assignments.

## Prepare and run

1. Keep the configured bot token and chat ID in their existing private location. Copy the new gateway folder to a private, unsynchronised location yourself, then create `secrets.h` there from `secrets.example.h` using the existing verified credentials. Do not put real credentials into the shared course folder. The target must be your **private** bot chat. No new bot is needed.
2. Open that bot chat in Telegram and press Start if needed. The Mac app is only a client: the ESP8266 must be powered and connected to Wi-Fi/internet for prompts and reminders; the Mac app does not need to stay open. Telegram must permit notifications if you want an alert outside the chat.
3. Use ESP8266 core **3.1.2**, the installed **ArduinoJson 7.4.3**, and **UniversalTelegramBot 1.3.0** (for its certificate header). The gateway uses the ESP8266 HTTP client directly, rather than the UniversalTelegramBot message parser. TLS certificate validation stays enabled.
4. Select a flash layout with LittleFS space and preserve that layout on later uploads. On a fresh board only, upload `fridge_storage_init`, open Serial Monitor at **115200**, and type `INITIALISE EMPTY FRIDGE` followed by Enter. This explicitly **erases the filesystem**. Never run this initialiser on a board containing food records. The main gateway refuses to auto-format a failed/corrupt filesystem.
5. Upload the privately configured gateway to ESP8266 and the switch sketch to Uno. ESP logs use **115200 baud**; Uno logs use **9600 baud**. No firmware has been flashed as part of preparing these files.
6. Confirm Wi-Fi/time readiness. Close the contact, then open it. Answer the two questions in the existing Telegram chat. Use `/list` after completion to check the saved record.
7. When food is removed/consumed, use `/list` then `/remove NUMBER`. Numbers reflect the current list and shift after removal. `/add` records another item manually. The prototype holds **16 items**; when full, remove an existing item before adding another.

Only this gateway should poll this bot. Another running bot process using `getUpdates`, or an existing webhook, can prevent replies from reaching it. This code does not delete webhooks automatically.

## Persistence and limits

- Food records, pending questions, question message IDs, reminder flags and Telegram update position are saved with LittleFS temporary-file/atomic-rename writes. A normal power cycle resumes the pending entry and retains food/reminder state. A filesystem write failure pauses bot processing and requires diagnosis/restart; Uno local alarms remain independent.
- A reply must come from the configured private chat and have a message ID newer than the question for the current stage. Old queued messages cannot fill a newly started question. Photos and other non-text replies do not complete an entry. Names can contain UTF-8 text but are limited to 64 **bytes**, so the number of Chinese characters is lower than 64.
- Storage time begins when ESP receives the opening event. If clock sync is unavailable then, it starts when a valid network clock returns. This can undercount an offline interval. There is no battery-backed clock and no inference of which food was actually placed inside.
- Further openings while an entry is pending are ignored for food registration. Use `/add` after completing it for extra foods. Every opening while idle asks for a food entry, even if you only take something out; that follows the requested mandatory-answer flow and may be inconvenient in everyday use.
- Board-to-board snapshots recover the current door state but do not retain every door movement during power loss, rapid changes or a lengthy HTTPS operation. An already-open door starts a new timer when a board restarts. Uno sensing/beeps remain independent of network delays.
- HTTPS/polling takes time, so Telegram responses and the 30-second remote warning may be delayed. Network loss delays delivery until reconnection; local 60-second beeps continue. Prompts retry at intervals of at least 10 seconds, door warnings at least 30 seconds, and storage reminders at least one minute. A network timeout can mean Telegram accepted a message despite an unconfirmed response, so a retry or a power cut between delivery and saving can cause a duplicate. Exactly-once delivery is not promised.
- Expiry-specific reminders are not enabled: the selected rule is **stored over seven days**. This prototype does not assess whether food is safe to eat.

## Validation

Run from the project root:

```sh
c++ -std=c++17 diagnostics/checks/fridge_state_check.cpp -o /tmp/fridge-state-check
/tmp/fridge-state-check
python3 diagnostics/checks/fridge_switch_check.py
```

The state check covers required-answer gating, question-message ordering/private-chat eligibility, duplicate starts, invalid dates/leap years, pending-state copying, the strict seven-day boundary, reminder suppression, capacity and removal. Copying a state in this test does **not** validate real flash persistence. The switch check executes the actual Uno sketch with simulated digital I/O and clock, covering contact bounce, snapshots, the local warning and clock wrap. Neither check sends Telegram messages.

Observed on 22 November 2026: both offline checks passed. The gateway and storage initialiser compiled for `esp8266:esp8266:nodemcuv2` with ESP8266 core 3.1.2 and ArduinoJson 7.4.3; the switch sketch compiled for `arduino:avr:uno` with AVR core 1.8.8. Gateway compilation used placeholder credentials. No upload, live Telegram request, real flash recovery test or seven-day physical run was performed.

Physical checks still required: open/close contact; finish questions; try commands/invalid dates mid-entry; power-cycle between answers and after completion; verify `/list`; verify an actual Telegram reminder using a deliberately shortened `WEEK` value in a separately labelled test build, then restore seven days; disconnect Wi-Fi and confirm the local buzzer still works. Also verify first-use formatting, real flash recovery, certificate validation and Telegram delivery on the boards.

References: [Telegram Bot API: getUpdates and sendMessage](https://core.telegram.org/bots/api), [Telegram step-by-step reply interface](https://core.telegram.org/bots/api#forcereply), [ESP8266 3.1.2 filesystem](https://arduino-esp8266.readthedocs.io/en/3.1.2/filesystem.html).
