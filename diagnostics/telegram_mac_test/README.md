# Run VIK on this Mac

The bot uses the existing private bot token and chat ID from `~/.config/int4089/countdown_gateway/secrets.h` or `~/.config/int4089/telegram_test/secrets.h`. Python 3 and macOS are required. No third-party Python libraries are needed.

## Dashboard and physical fridge door

1. Connect the GPS-23L switch between Uno **D2** and **GND**. Connect the Grove buzzer signal to **D3**. The contact reads `LOW` with the magnet near it.
2. Upload `diagnostics/fridge_switch/fridge_switch.ino` using the **Arduino Uno** board profile. Connect the Uno to the Mac over USB, close Arduino Serial Monitor, and stop any previous Uno USB bridge or Telegram polling bot.
3. Double-click `StartFrontendDemo.command` at the project root. Click **Start Telegram Bot** in the opened browser. The page reports when the Uno starts sending switch events. Keep the launcher Terminal open. Click **Restart Telegram Bot** to stop and start the bot in one action, or **Terminate Telegram Bot** to leave it stopped.
4. Open the door. Telegram asks for the item name, fridge layer (Layer 1, 2, or 3), and expiry date in `YYYY-MM-DD` format. Send `/skip` at any entry question to discard the pending entry. Reopening the door repeats the current question for an unfinished entry and keeps any food name already entered.
5. Under **Current Status**, type a door warning delay from 0 to 30 seconds (whole number, decimal or fraction), then click **Apply**. The default is 5 actual seconds. The separate Buzzer slider sets how long the door must stay open before D3 starts pulsing: 10–60 seconds, default 60. It pulses until the door closes or **Mute buzzer** is applied. Muting also cancels pending manual alarms. **Enable buzzer** restores sound, including for a currently overdue open door. The Uno remembers mute across resets, and the Mac reapplies saved settings when connected.
6. Send **`/alarm`** in the private Telegram chat to start the manual buzzer demo. The bot displays a **30-second** setting, and the updated Uno sketch waits **5 actual seconds** before pulsing D3 for three seconds. The Uno reports completion to the bot. This manual alarm also works with the door closed. Connect the Grove buzzer and upload the updated `fridge_switch.ino` before the live demo.

The dashboard looks for one `/dev/cu.usbmodem*` device. For an Uno on a different port, run `python3 diagnostics/telegram_mac_test/fridge_mac_test.py --door-port /dev/cu.YOUR_PORT` from the project root. Use a single polling bot per Telegram token.

## Current Status page

For live door status alone, keep the tested D2-to-GND wiring and the InputPullupSerial sketch at 9600 baud. Close Arduino Serial Monitor and open **Current Status**. A single-line `0` means **Closed** (magnet near) and `1` means **Open** (magnet away). The integrated fridge sketch also works and adds Uno buzzer support.

Click **Current Status** at the top of the control dashboard to switch pages in the same browser tab. Click **Bot Controls** to switch back. The page reads the Uno door switch even when the bot is stopped. Start the Telegram bot to send food prompts and door warnings. Current Status displays the latest ambient temperature from the ESP8266. Start the NFC gateway and scan a tag to update the latest ingredient name, tag ID and scan time.

The Buzzer card shows `buzzing` throughout an active pulse sequence and `idle` between alarms. The Uno reports both over USB.

The page refreshes once a second and labels old door and temperature readings as last seen. The temperature alert helper can use the same readings while this page's launcher owns the ESP8266 port.

## NFC demonstration from the dashboard

1. Connect the Mac and iPhone to the same local network, or connect the Mac to the iPhone’s Personal Hotspot.
2. Open `StartFrontendDemo.command`. Under **NFC Gateway**, click **Start NFC Gateway** and wait for **Running**.
3. Click **Copy NFC URL** and paste it into the iPhone Shortcut’s **Get Contents of URL** action. Keep the existing `POST` method, `X-NFC-Key` header and JSON `item_id` field. The gateway uses the existing settings under `~/.config/int4089/nfc_gateway`.
4. The dashboard updates **Current Mac Wi-Fi IP** and the NFC URL when the address changes. Click **Restart NFC Gateway**, wait for **Running**, then copy the new URL.
5. Click **Terminate NFC Gateway** to stop receiving scans. The dashboard stays open so you can start the gateway again.

To check the connection from the iPhone, open the displayed address in Safari with `/health` at the end instead of `/nfc`. A successful check shows `"ok": true`. Keep the launcher Terminal open while using the gateway.

## Temperature alerts from the ESP8266

The ESP8266 reads ambient temperature from the MLX90614. While the dashboard and Telegram bot are running, the bot sends a warning above the saved **Current Status** temperature threshold (default 55 °C, adjustable from 20 to 90 °C), even when Current Status is closed. The standalone `sensor_alerts.py` can send alerts independently and uses `--temperature-threshold 30` as its fallback when no dashboard temperature threshold has been saved. It takes priority for sending temperature warnings while it runs. The dashboard accepts ambient readings from both the current sketch and older sketches.

## Simulate the conversation without an Uno

1. From the project folder, run `/usr/bin/python3 diagnostics/telegram_mac_test/fridge_mac_test.py`. Keep Terminal open and the Mac awake and online.
2. The Terminal prints the bot's `https://t.me/...` address after checking the connection. Open that chat in Telegram. VIK sends its welcome message on launch and when you send `/start`.
3. Send **`/open`**. This simulates the fridge switch opening.
4. Reply with a food name, such as **Milk**, then choose **Layer 1**, **Layer 2**, or **Layer 3**.
5. Reply with a real expiry date, such as **2026-12-01**. Other normal bot commands wait until all three answers are complete or you send **`/skip`**. Old messages sent before the relevant question are ignored.
6. Send **`/test_expiry`**. The bot previews the two-day expiry reminder for the newest saved item. It should arrive within about 15 seconds while the connection works. The item stays eligible for its automatic reminder.
7. Use **`/list`**, **`/edit NUMBER`**, **`/delete NUMBER`**, or **`/open`** when an entry is finished. Press **Ctrl+C** in Terminal to stop.

## Edit and organise the list

| Command | Action |
|---|---|
| `/list` | Show foods by expiry date, earliest first; expired items appear first |
| `/list added` | Show foods in the order they were added, oldest first |
| `/list name` | Sort names alphabetically (ASCII case-insensitive) |
| `/list 2` or `/list added 2` | Show another page, ten items per page |
| `/view 3` | Show item #3's name, expiry, added time and reminder status |
| `/edit 3` | Choose name or expiry, then answer the bot's next question |
| `/rename 3 Fresh milk` | Change item #3's name directly |
| `/expiry 3 2026-12-10` | Change item #3's expiry date directly |
| `/edit 3 name Fresh milk` | Alternative direct name edit |
| `/edit 3 expiry 2026-12-10` | Alternative direct expiry-date edit |
| `/delete 3` or `/remove 3` | Delete only item #3 |
| `/cancel` | Leave an interactive edit without changing the record |
| `/skip` | Discard the current new food entry at any entry question |
| `/test_expiry` | Preview the two-day expiry reminder for the newest saved item |
| `/help` | Show available commands |

Visible item numbers are **consecutive list positions**, starting at #1 with no gaps. If you delete the only item and add another, the new item is #1. If you delete the first of three items, the remaining items become #1 and #2. Commands such as `/edit 1`, `/view 1` and `/delete 1` target item #1 in the most recently selected list order. Sorting, adding, deleting or editing can change these positions, so refresh the list and use its current numbers. Page two starts at #11; `/list 2` keeps the most recently selected sort. `/list` by itself switches back to earliest expiry first.

Changing an expiry date updates the item's position in the default list and the day its reminder is due. For equal expiry dates, the older-added item appears first, with a consistent tie-breaker. Dates must be real dates in `YYYY-MM-DD` format. Edits preserve the storage-start time. Added times are displayed in Hong Kong time. Permanent internal database keys are retained to keep records, reminders and unfinished edits attached to the correct food.

New food entries require all three answers to save. `/skip` discards a pending new entry and `/cancel` leaves an existing item's edit unchanged. Unfinished edits resume after restarting the bot. Existing databases are upgraded automatically at startup and keep saved food and unfinished entries. Old storage reminders do not affect whether an expiry reminder is due. On upgrading an existing non-empty list from permanent IDs, the bot requires `/list` before numbered commands so you can see the new numbers. Stop the old bot with **Ctrl+C** before starting this updated script.

VIK sends the automatic expiry reminder on the Hong Kong calendar date two days before expiry. For example, an item expiring on 1 December is due for a reminder on 29 November. The bot checks every ten seconds while running and records a successful reminder against the item's expiry date. Keep the bot running and online that day to receive it. Dates in 2000–2099 are accepted. Food names are limited to 64 UTF-8 bytes, matching the separate ESP8266 prototype.

Food records, unfinished entries, message positions and reminder flags are stored in a private SQLite database at `~/.config/int4089/fridge_mac_test/test_food.sqlite3`. Close and reopen the launcher to resume. The Mac bot must remain running to send Telegram messages. The uploaded Uno sketch controls the local buzzer independently. Records in the Mac database are separate from the ESP8266 gateway's storage.

Only one process may poll this bot. Stop other bot test programs first. The launcher detects a second local runner and refuses to remove an existing webhook automatically. First-ever startup discards old queued bot messages to avoid treating them as test commands; normal restarts retain the saved update position. Use a dedicated test bot if old queued messages need to remain available to another application. Network timeouts can cause duplicate outbound messages after retries or a crash; exactly-once delivery is not guaranteed.

From the project root, run the offline checks with `python3 -m unittest discover -s diagnostics/telegram_mac_test -v`. They cover the expiry reminder date, the test preview, saved records, editing, list order and database upgrades.
