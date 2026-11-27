# VIK: component and integration checklist

Updated 5 November 2026. Main controller: Arduino Uno R3. The Mega is not required for the current direction.

Checked boxes record choices or results the user has confirmed. Unchecked boxes are pending or unconfirmed; they do not necessarily mean a part must be purchased.

## Current status

- [x] Uno R3 chosen as the main controller.
- [x] Standalone countdown sketch reported working on the Uno.
- [x] Water sensor pin labels identified: S, +, -.
- [x] Serial readings respond to finger contact. Reported examples include 0, 43, 55 and 69; these are not water-calibration values.
- [x] Door-sensor choice confirmed: GPS-23L, matching magnet included, normally open, left wire exit.
- [ ] Magnetic sensor received and physically tested; last reported as in delivery.
- [ ] NFC tags received and physically tested; last reported as in delivery.
- [x] Wi-Fi board identified from photos: NodeMCU-style ESP8266 development board with ESP-12F module, CH340 USB interface, micro-USB socket and FLASH/RST buttons. Arduino IDE profile: NodeMCU 1.0 (ESP-12E Module).
- [ ] NFC reader, water sensor, shield and audio module exact models recorded.

The previous Uno-plus-Mega build guide and diagram are marked superseded. Do not use their Mega pin assignments for the Uno.

## 1. Uno R3, USB cable and Arduino IDE

- [x] Upload and run the standalone countdown test.
- [ ] Save the working countdown sketch separately from other tests.
- [ ] Label each test sketch clearly: water readings, buzzer, LED, door, NFC and integrated project.
- [ ] Confirm the correct board and USB port before each upload.
- [ ] Match Serial Monitor baud rate to the sketch; the current tests use 9600 baud.
- [ ] Keep the Uno as the main controller; leave the spare Mega out of the current build.

## 2. Breadboard, DuPont wires and Grove cables

- [ ] Inspect for damaged insulation, loose connectors and exposed wires touching adjacent pins.
- [ ] Check male/female connector types match the board and modules.
- [ ] Check whether the breadboard's power rails are split in the middle.
- [ ] Identify and label power, ground and signal connections.
- [ ] Establish a common ground between interconnected modules.
- [ ] Disconnect power before moving wires.
- [ ] Keep independently USB-powered 5 V outputs separate; do not accidentally connect supply outputs together.
- [ ] Secure wires so moving the cup or box does not pull a connection loose.

## 3. Grove Base Shield

- [ ] Record the exact shield version and confirm Uno R3 compatibility.
- [ ] Seat it in the correct header orientation with power disconnected.
- [ ] If it is the documented Base Shield V2, select the 5 V setting for the Uno setup.
- [ ] Check each connected module's own voltage requirements; the shield does not convert every signal voltage.
- [ ] Record which port each module uses.
- [ ] Check for pin overlap: Grove sockets share the Uno pins rather than creating new pins.

## 4. Grove buzzer

- [ ] Confirm the exact buzzer module and its signal/power/ground labels.
- [ ] Connect it to the selected digital Grove socket; D4 remains a proposed assignment until the final pin map is checked.
- [ ] Test a brief sound and verify it stops.
- [ ] Test two recognisable patterns for fridge and water warnings.
- [ ] Confirm water warnings can take priority when both conditions are active.
- [ ] Confirm resetting one condition does not silence the other active warning.
- [ ] Confirm audibility and comfort with a potential user in the intended room.

The buzzer provides tones. Spoken item names require an audio playback module and speaker.

## 5. Small LED and resistor

- [x] Small LED selected instead of an unspecified light bulb.
- [ ] Prepare a 330-ohm series resistor for an ordinary small indicator LED.
- [ ] Identify anode and cathode.
- [ ] Wire selected Uno output -> resistor -> anode; cathode -> GND.
- [ ] Test on and off separately before linking it to water detection.
- [ ] Confirm the LED follows the water warning state and clears correctly.
- [ ] Keep an immediate nonvisual water cue as well as the LED.

## 6. Water-level sensor

- [x] Identify S, + and - labels.
- [x] Confirm changing readings appear in Serial Monitor during the finger test.
- [ ] Record the individual sensor model. EF08239 is the Wonder Building Kit number.
- [ ] Confirm the operating voltage before final installation. The standalone test used S -> A0, + -> 3.3 V, - -> GND for the ELECFREAKS sensor.
- [ ] Record at least five dry, untouched readings.
- [ ] Record readings with actual cold tap water below, at and above the desired warning position.
- [ ] Keep the connector and upper electronics dry; wet only the intended sensing tracks.
- [ ] Choose the warning threshold from the measured water data, not finger readings.
- [ ] Set a separate clear threshold/stability rule so readings near the boundary do not produce repeated alerts.
- [ ] Test different pouring speeds and confirm there is time to stop before overflow.
- [ ] Test residual droplets, cup movement and splashes for false/repeated alerts.
- [ ] Confirm one Telegram alert per filling event and correct rearming afterwards.
- [ ] Disconnect power, blot gently and air-dry after testing.
- [ ] Check food-contact suitability before using the sensor with anything intended to be consumed.

Record:

| Measurement | Observed result |
|---|---|
| Dry, untouched range | |
| Below-warning range | |
| At-warning range | |
| Above-warning range | |
| Trigger threshold | |
| Clear threshold | |
| Time from warning to overflow at tested pouring speeds | |

## 7. GPS-23L magnetic sensor and model fridge

- [x] Choose GPS-23L: matching magnet, normally open, left wire exit.
- [ ] Inspect the delivered unit and confirm it is a passive two-wire contact.
- [ ] Verify contact connected with magnet near and disconnected with magnet far; check actual behaviour rather than relying only on NO/NC wording.
- [ ] Connect the passive contact between the selected Uno input and GND; D2 remains the proposed assignment. Use INPUT_PULLUP.
- [ ] Verify near = LOW and far = HIGH for the chosen contact behaviour.
- [ ] Mount the wired part on the fixed box frame and magnet on the moving door near the latch edge.
- [ ] Test fully closed, slightly ajar, partly open and fully open positions.
- [ ] Adjust mounting if a small gap still registers closed. Use a different sensing method if the required gap cannot be distinguished.
- [ ] Verify short contact flicker does not repeatedly reset a continuously open incident.
- [ ] Open for less than 30 seconds, then close: no remote warning and no 60-second alarm.
- [ ] Keep open for 30 seconds: one Telegram warning.
- [ ] Keep open for 60 seconds total: local fridge buzzer starts.
- [ ] Close: fridge timer and fridge alarm reset.
- [ ] Reopen: a new countdown begins.

The box checks door position. It does not establish that a real fridge's whole seal is airtight.

## 8. Countdown software

- [x] Run the standalone 60-second countdown; user reported success.
- [x] Confirm the 30-second reminder occurs once. Verified on the Uno-to-ESP8266 countdown test, with receipt confirmed in Telegram.
- [x] Confirm the 60-second endpoint occurs once. Verified from the Uno Serial output; no second Telegram alert at this endpoint.
- [ ] Confirm RESET restarts the standalone test.
- [ ] Combine countdown and buzzer with no door sensor first.
- [ ] Later, start/reset the countdown from the real door state.
- [ ] Use elapsed-time checks rather than long delays in the integrated program so water and NFC remain responsive.

The two-board countdown test passed on 5 November 2026. Uno D9 sends 9600-baud events through three 1 kΩ resistors to ESP D5, with common GND. Reset the Uno after ESP READY to repeat. The physical buzzer and magnetic switch have not been added to this test.

## 9. NFC reader

- [ ] Record the exact model, interface mode and pin labels.
- [ ] Confirm support for the chosen tags; an MFRC522/RC522 supports NTAG, but other boards have different requirements.
- [ ] Confirm module supply and signal-voltage requirements before wiring.
- [ ] Prepare suitable voltage conversion where required; do not assume all reader inputs accept Uno 5 V outputs.
- [ ] Assign the actual reader pins in the Uno pin map; do not use the old Mega wiring table.
- [ ] Install the matching library and run its reader-identification example.
- [ ] Read and record each tag's complete unique ID and ID length.
- [ ] Test one container at a time at a tactile-marked scanning area.
- [ ] Test an unknown tag and an unreadable scan; never retain an old name as the new result.
- [ ] Check repeated-read suppression while a tag remains present and successful rescan after removing it.

## 10. NFC tags and phone app

- [ ] Confirm the delivered tag type; NTAG213, 13.56 MHz, writable and NDEF-formatted is the recommended option.
- [ ] Install NFC Tools by wakdev on an NFC-capable phone.
- [ ] Read each tag and record its unique ID and assigned item.
- [ ] Write a text record: Rice, Oil or Salt, then read it back.
- [ ] Keep tags writable during development.
- [ ] Attach tags consistently outside their containers with a tactile cue where useful.
- [ ] Test the actual filled containers; use suitable on-metal tags if mounting on metal.
- [ ] Keep phone-readable labels and Arduino ID-to-name mapping consistent.
- [ ] Check that the phone can read the label using the chosen app.
- [ ] If phone-triggered speech/Telegram is required, configure and test that separately. A text record alone does not provide those automations.
- [ ] Keep the Telegram bot token and Wi-Fi password off the tags.

| Container | Complete tag ID | Phone text | Arduino name/audio verified |
|---|---|---|---|
| Rice | | Rice | |
| Oil | | Oil | |
| Salt | | Salt | |

## 11. Audio playback module and speaker — additional hardware

- [ ] Select and obtain a suitable playback module and speaker, or a module with an integrated speaker.
- [ ] Confirm its supply, logic interface and compatibility with the available Uno connections.
- [ ] Resolve how audio and ESP8266 communication coexist on the Uno; do not assume two SoftwareSerial receivers can listen simultaneously.
- [ ] Prepare recordings for Rice, Oil, Salt and Item not registered in the intended user's language.
- [ ] Verify every audio selection independently before linking it to NFC.
- [ ] Confirm the correct name plays after each registered tag.
- [ ] Test volume and intelligibility in the intended environment.
- [ ] Check urgent water/fridge cues remain clear during item playback.
- [ ] Verify spoken identification works without internet and without a laptop.

## 12. ESP8266 and Wi-Fi

- [x] Confirm whether the board is already available; record its exact model. Photos show a NodeMCU-style ESP-12F / CH340 USB development board; use the NodeMCU 1.0 (ESP-12E Module) profile.
- [ ] Check its supply/regulator and provide adequate power.
- [x] Use a suitable interface for Uno 5 V signals; ESP8266 GPIO is not 5 V tolerant. The countdown prototype uses a three-1 kΩ divider; UART reception was verified, but voltage was not measured.
- [ ] Connect common ground and confirm the final serial/interface pin map.
- [ ] Avoid contention with USB upload/debug connections when programming.
- [ ] Test Wi-Fi and internet access at the intended demonstration location.
- [x] Test reception of one known event from the Uno before adding all events. START and COUNTDOWN_30 were received through the physical link.
- [x] Check secure HTTPS certificate validation; do not disable it to make a connection appear successful.
- [ ] Test disconnection and reconnection without stopping Uno local sensing and alarms.

Standalone test passed on 5 November 2026: ESP8266 connected through a phone hotspot, synchronised time and received a Telegram API success response with certificate validation enabled. The user confirmed receipt in the private bot chat. Uno communication, demonstration-location access and recovery during local sensing remain pending.

## 13. Telegram bot — software/service

- [ ] Confirm bot creation through official BotFather and save its token privately.
- [x] Start the bot conversation or add it to the intended destination group.
- [x] Obtain the correct destination chat ID.
- [ ] Send one manual test message and confirm receipt.
- [x] Send one message from ESP8266 firmware and check the API success response. User confirmed the test message arrived in the private chat.
- [ ] Test fridge, water and recognised-item messages separately.
- [ ] Confirm each incident/presentation produces the intended number of messages.
- [ ] Report failed delivery; keep the local buzzer/speech operating.
- [ ] Check phone notification settings if audible phone notifications are part of the demonstration.
- [ ] Remove tokens and Wi-Fi credentials from shared source, photographs and slides.

## 14. Final combined test

- [ ] Final Uno wiring map reviewed with no unintended pin conflicts.
- [ ] Model fridge and cup mounts secure; boards and power connections outside spill area.
- [ ] Door alarm does not stop water monitoring or NFC scanning.
- [ ] Water warning is prioritised and is not cleared by closing the fridge.
- [ ] A recognised tag does not restart or reset the fridge timer.
- [ ] Network failure does not stop local functions.
- [ ] Unknown tags cannot produce a false known item name.
- [ ] After a restart, an already-high water level is detected; calibration does not wrongly treat it as dry.
- [ ] Boot with the fridge open and document that elapsed time starts at boot.
- [ ] Test using standalone power with no laptop; Serial Monitor is a development aid.
- [ ] Check the actual setup with potential users and document their feedback.
- [ ] Record observed pass/fail results, timing, missed/false alerts and modifications.
- [ ] Save final part numbers, wiring, sketches, library versions, calibration and assembly/user instructions for the course submission.

## Suggested next tests with parts already available

1. Grove buzzer alone.
2. Small LED with its series resistor.
3. Actual-water measurements and warning threshold.
4. Water-triggered buzzer/LED.
5. Countdown-triggered buzzer.
6. Manual Telegram test while waiting for sensor/tag delivery.

## Reference documentation

- [Uno R3](https://docs.arduino.cc/hardware/uno-rev3/)
- [Grove Base Shield V2](https://wiki.seeedstudio.com/Base_Shield_V2/)
- [Grove buzzer](https://wiki.seeedstudio.com/Grove-Buzzer/)
- [ELECFREAKS EF04094 water sensor](https://shop.elecfreaks.com/products/elecfreaks-octopus-water-level-sensor) — verify the kit's individual sensor before applying its specification.
- [NXP NTAG213/215/216](https://www.nxp.com/products/NTAG213_215_216)
- [MFRC522 specification](https://www.nxp.com/docs/en/data-sheet/MFRC522.pdf)
- [NFC Tools Android](https://www.wakdev.com/en/apps/nfc-tools-android.html), [iPhone](https://www.wakdev.com/en/apps/nfc-tools-ios.html)
- [Telegram Bot API](https://core.telegram.org/bots/api)
- [Espressif ESP8266 specifications and GPIO guidance](https://www.espressif.com/en/products/socs/esp8266ex/resources/)

This checklist records reported progress; it is not evidence that the unconfirmed components or final integrated circuit have passed testing.
