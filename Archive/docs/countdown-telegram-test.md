# Uno countdown → ESP8266 → Telegram

This test keeps the countdown on the **Arduino Uno R3**. At 30 seconds, the Uno sends a short serial event to the ESP8266, which sends one Telegram alert. At 60 seconds, the Uno prints the endpoint and stops. A magnetic switch and buzzer are not part of this test.

## Files and board settings

| Device | Sketch | Board profile | USB port on this Mac | Serial Monitor |
|---|---|---|---|---|
| Uno R3 | `diagnostics/uno_countdown_link/uno_countdown_link.ino` | Arduino Uno | `/dev/cu.usbmodem11401` | 9600 baud |
| ESP8266 | Configured local copy: `/Users/oscarng/.config/int4089/countdown_gateway/countdown_gateway.ino` | NodeMCU 1.0 (ESP-12E Module) | `/dev/cu.usbserial-1110` | 115200 baud |

The shareable ESP sketch is `diagnostics/countdown_gateway/countdown_gateway.ino`; its `secrets.example.h` contains placeholders. The configured copy outside OneDrive reuses the credentials from the successful standalone test. Do not copy the real `secrets.h` into the shared course folder. USB port names can change after reconnecting.

Use the ESP8266 core and library versions installed for the [standalone Telegram test](../diagnostics/telegram_test/README.md). The gateway uses the core HTTP client and ArduinoJson, with the trusted Telegram certificate provided by the installed UniversalTelegramBot library.

## Wire with three 1 kΩ resistors

**Disconnect both boards from USB/power before wiring.** Use three separate 1 kΩ resistors on the breadboard:

```text
Uno D9 ---- [1 kΩ R1] ----+---------------- ESP D5 (GPIO14)
                         |
                      [1 kΩ R2]
                         |
                      [1 kΩ R3]
                         |
Uno GND -----------------+---------------- ESP GND
```

The two lower resistors are in series, making 2 kΩ. The junction after R1 and before R2 gives approximately `5 × 2 / (1 + 2) = 3.33 V` when the Uno output is HIGH. All resistors are nonpolarised.

1. Connect Uno **D9** to one end of **R1**.
2. Put R1's other end, R2's first end and the wire to ESP **D5** in the same electrically connected breadboard row. This is the signal junction.
3. Connect R2's other end to R3's first end in another connected row. Do not connect ESP D5 to this middle point between R2 and R3.
4. Connect R3's remaining end to GND. Join **Uno GND** and **ESP GND** to that same ground connection.
5. Uno **D8** is unused; leave it unconnected. ESP **TX/RX** pins are unused for the interboard link. Use the ESP pin labelled **D5**, not the bare module's fifth physical pin.

Keep Uno D9 separated from ESP D5 by R1. A direct 5 V connection can damage the ESP8266. Power each board through its own USB connection; keep their 5 V supply outputs separate. Only the ground and the divided signal are connected between boards.

Send a clear photo of the unpowered wiring before powering the first assembly. If a meter is available, the divider can also be checked separately with ESP D5 disconnected: the signal junction should be near 3.3 V when Uno D9 is HIGH.

## Upload and run

1. Upload the gateway sketch to the **ESP8266**, using the configured local copy above. This replaces the automatic startup-message test. The gateway sends no Telegram message just because it boots.
2. Upload the Uno link sketch to the **Uno R3**. Keep the two IDE windows' board and port selections separate.
   Close Serial Monitor/Plotter while another program is uploading or monitoring a port. An open monitor can keep the port busy. Confirm the upload verification and new sketch's startup banner rather than relying only on an uploader exit code.
3. Keep the phone hotspot available, with the same settings that passed the standalone test.
4. Open the ESP8266 Serial Monitor at **115200 baud**. Wait for:

   ```text
   READY: Waiting for Uno D9 through the divider to ESP D5. Reset the Uno now.
   ```

5. Press the **Uno RESET** button once. This starts a fresh 60-second run and rearms the ESP alert. The ESP should print:

   ```text
   New Uno countdown started.
   ```

6. At 30 seconds, expect this in your private bot chat:

   ```text
   Countdown test: 30 seconds elapsed on the Arduino Uno.
   ```

   The ESP should report `PASS: Telegram accepted the Uno countdown alert.` The Uno, if viewed at 9600 baud, reports `30-second event sent to ESP8266.`

7. At 60 seconds, the Uno prints its endpoint and stops. No second Telegram message or buzzer sound is expected in this test.
8. Reset the Uno to repeat. Opening its Serial Monitor or uploading can also reset the Uno and start a new run.

The Uno timer continues independently while the ESP performs HTTPS. The computer is used here for programming, USB power and logs; the timer and messaging run on the boards.

## Limits and diagnosis

- Start/reset the Uno **after ESP READY** for this test. There is no readiness handshake or durable event queue.
- This is a one-way 9600-baud connection: Uno D9 transmits; ESP D5 receives. No return wire is required.
- The ESP accepts only `START` and `COUNTDOWN_30` lines. It ignores unknown, nonprinting and oversized input lines, and suppresses repeated reminders until a new `START`.
- It makes one Telegram request for each countdown reminder, with certificate validation enabled. It waits for the complete HTTP response and reports success only for HTTP 200 with a valid JSON `ok: true` result. There are no automatic delivery retries. If network/clock readiness is lost, the event is skipped. Restore ESP readiness and reset the Uno to run another test.
- A failed HTTP response can mean delivery is uncertain. Check the chat before repeating the countdown.
- If the Uno reports its event but the ESP shows no `New Uno countdown started`, check the common GND, resistor junction and the D9-to-D5 connection. Do not bypass the divider to troubleshoot.

## Software checks

```sh
python3 diagnostics/checks/countdown_link_check.py
python3 diagnostics/checks/telegram_test_check.py
```

The first runs the actual new sketches against simulated external hardware boundaries: countdown timing/rollover, exactly one reminder, reset/rearm, fragmented input, malformed/oversized input, network/clock failure and failed delivery. The response checks use the installed ArduinoJson library, covering a complete response body, a large ignored result field, invalid JSON, API rejection and HTTP error status. The second preserves the standalone Telegram diagnostic checks. Real compilation and physical interboard receipt are separate checks.

Verified on 5 November 2026:

- The Uno and gateway sketches compiled for `arduino:avr:uno` and `esp8266:esp8266:nodemcuv2`. Both were uploaded with verification; the ESP flash hash and the correct gateway startup banner were checked.
- The actual three-resistor link carried the Uno START and 30-second events to ESP D5. The user confirmed the ground connection; the divider voltage was not measured.
- The initial Telegram helper incorrectly reported a delivered message as unconfirmed. After switching the gateway to the core HTTP client, a fresh physical run reported `Telegram HTTP status: 200` and `PASS: Telegram accepted the Uno countdown alert.` The user confirmed receipt of that new message.
- The final monitored run recorded one Telegram success response, the Uno's 30-second transmit event, and its 60-second endpoint. No second alert was sent at the endpoint.
- All 12 link scenarios and all eight standalone Telegram scenarios passed after the response-handling change. The original countdown check passed during initial verification.
- The configured gateway copy matches the shareable source; credentials remain outside OneDrive. Arduino IDE was reopened and its ESP Serial Monitor set to 115200 baud.

This verifies the countdown-to-Telegram prototype. The magnetic switch, physical buzzer and other sensor integrations remain untested in this two-board setup.

References: [Uno R3](https://docs.arduino.cc/hardware/uno-rev3/), [Arduino SoftwareSerial](https://docs.arduino.cc/learn/built-in-libraries/software-serial/), [ESP8266 3.1.2 reference](https://arduino-esp8266.readthedocs.io/en/3.1.2/reference.html).
