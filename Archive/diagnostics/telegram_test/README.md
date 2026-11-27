# ESP8266 → Telegram connection test

This standalone diagnostic sends one test message to your private Telegram chat each time the ESP8266 boots. It does not read sensors or reply to Telegram messages. Keep the Uno and all sensors disconnected during this test.

## 1. Open the configured local copy

EV prepared a copy outside the OneDrive course folder:

`/Users/oscarng/.config/int4089/telegram_test/telegram_test.ino`

Open that `.ino` in Arduino IDE. Its adjacent `secrets.h` contains the provided bot token and verified private chat ID. Enter your Wi-Fi name and password there, keeping the quotation marks. Use a 2.4 GHz network with ordinary password authentication, such as a home router or compatible phone hotspot. A campus network with a browser login or enterprise authentication will need a different setup. Do not post your Wi-Fi password in chat.

This repo contains the shareable sketch and a placeholder `secrets.example.h`. For another group member, copy this folder to a location outside shared/synchronised storage, rename `secrets.example.h` to `secrets.h`, and fill it in locally. `.gitignore` excludes `secrets.h` from Git; it does **not** stop OneDrive synchronisation. Firmware uploaded to the board also contains the credentials.

## 2. Install board support and libraries

In Arduino IDE:

1. Open Settings/Preferences. Add this under **Additional boards manager URLs**:

   `https://arduino.esp8266.com/stable/package_esp8266com_index.json`

2. In **Boards Manager**, install **esp8266 by ESP8266 Community**. This diagnostic targets core **3.1.2**.
3. In **Library Manager**, install **UniversalTelegramBot by Brian Lough**, version **1.3.0**, and **ArduinoJson by Benoit Blanchon**, version **6.21.5**. Select the listed ArduinoJson 6 version rather than assuming a different major version is compatible.

EV installed these exact versions on this Mac for verification. Restart Arduino IDE if they do not appear; another computer will need its own installation.

## 3. Connect and upload

1. Connect only the ESP8266 development board to your computer using a USB **data** cable. No breadboard wiring is needed.
2. Select the matching board under **Tools → Board → esp8266**:

   | Board in your hand | IDE board selection |
   |---|---|
   | NodeMCU ESP8266, including our photographed ESP-12F / CH340 board | NodeMCU 1.0 (ESP-12E Module) |
   | Wemos/LOLIN D1 mini ESP8266 | LOLIN(WEMOS) D1 R2 & mini |

3. Select its USB port under **Tools → Port**. Keep default board settings for the first test.
4. Click **Verify**, then **Upload**. This sketch belongs on the **ESP8266**, not the Uno.
5. Open Serial Monitor at **115200 baud** and press **RST/RESET** once. A short burst of unreadable boot text can appear before the sketch starts.

Expected Serial Monitor stages:

```text
Kitchen assistant: ESP8266 Telegram test
Connecting to Wi-Fi (up to 45 seconds)...
Wi-Fi connected.
Synchronising clock for HTTPS (up to 30 seconds)...
Sending one Telegram test message...
PASS: Telegram accepted the test message. Check your private chat.
```

Expected private Telegram message:

```text
Kitchen assistant: ESP8266 Telegram connection test successful.
```

Check actual receipt on your phone before recording a pass. The bot remains silent when you type to it; this diagnostic only sends the startup test. Every reset or power cycle repeats the test. There is no automatic resend after failure, so a network problem does not cause a message loop.

## Troubleshooting

| Symptom | Next check |
|---|---|
| `secrets.h: No such file` | Open the configured local copy, or create `secrets.h` beside the sketch from the example. |
| Missing ESP8266 headers | Install ESP8266 board support and select the ESP8266 board. |
| Missing UniversalTelegramBot / ArduinoJson | Install the libraries and versions above. |
| No USB port | Try a known data cable and USB port; identify the board's USB interface before selecting any driver. |
| Wi-Fi timeout | The diagnostic prints the Wi-Fi status and whether the configured hotspot is visible. If visibility is NO, check hotspot broadcasting, 2.4 GHz availability and the exact network name. If YES, recheck the password and compatible hotspot security. A scan failure means visibility is unknown. |
| Clock timeout | The board joined Wi-Fi but cannot synchronise time; check internet/NTP access. |
| Send failed | Check internet/Telegram access, current token, chat ID and that you started the bot. If Telegram's certificate chain changes, update the library's trusted certificate. Keep certificate validation enabled. |
| PASS but no phone alert | Open the actual bot chat and look for the message; check Telegram notification/mute settings separately. |

Network and clock waits are bounded; after a Wi-Fi timeout, the visibility scan takes additional time. The scan does not print passwords or nearby network names. HTTPS calls can still take several seconds. This is a connection diagnostic, not the final program for monitoring the Uno while a request is in progress.

## Verification

Verified on 5 November 2026 using core 3.1.2, UniversalTelegramBot 1.3.0 and ArduinoJson 6.21.5:

- The initial version compiled for NodeMCU and D1 mini with placeholder credentials. The updated visibility diagnostic compiled for the actual NodeMCU-style ESP-12F / CH340 board.
- All eight offline Telegram scenarios passed, including visible/missing hotspot and scan failure. The existing countdown check also passed during initial verification.
- The configured local sketch was uploaded on `/dev/cu.usbserial-1110` and its flash hash verified.
- Initial physical runs timed out at Wi-Fi. The final run connected to the phone hotspot, synchronised its clock and reported `PASS: Telegram accepted the test message.` Certificate validation remained enabled.
- The user confirmed that the test message arrived in the private bot chat.

This verifies the standalone ESP8266-to-Telegram path. It does not verify Uno communication or sensor-triggered messages. Each restart repeats the startup test.

Run the offline control-flow check from the project root:

```sh
python3 diagnostics/checks/telegram_test_check.py
```

It runs the sketch with simulated external hardware boundaries. It checks successful sending, configuration rejection, Wi-Fi/clock timeouts, hotspot visibility/scan failure, rollover and no repeated sends in `loop()`. It sends no network requests and does not by itself prove actual Wi-Fi, TLS or phone delivery. The separate physical verification is recorded above.

References: [ESP8266 installation](https://arduino-esp8266.readthedocs.io/en/latest/installing.html), [ESP8266 TLS validation and clock requirements](https://arduino-esp8266.readthedocs.io/en/latest/esp8266wifi/bearssl-client-secure-class.html), [UniversalTelegramBot ESP8266 example](https://github.com/witnessmenow/Universal-Arduino-Telegram-Bot/blob/master/examples/ESP8266/EchoBot/EchoBot.ino).
