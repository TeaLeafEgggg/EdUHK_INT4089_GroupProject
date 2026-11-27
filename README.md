# VIK · Vision Intervention Kit

INT4089 Group 5 built VIK as a kitchen assistance prototype for people with low vision. The demo combines fridge-door and buzzer alerts, Telegram food records and expiry reminders, NFC item identification, and an infrared temperature reading.

## Start the demo on macOS

Double-click [StartFrontendDemo.command](StartFrontendDemo.command) and keep its Terminal window open. The dashboard opens in your browser. Use **Current Status** for the sensor readings and **Start Telegram Bot** or **Start NFC Gateway** when those services are configured. The launcher uses macOS's `/usr/bin/python3` and Python's standard library.

On another Mac, supply your own `FRIDGE_BOT_TOKEN` and `FRIDGE_CHAT_ID` as local environment variables. From that Terminal session, run `./StartFrontendDemo.command` in the project folder. Existing setups can also read their private Telegram settings from `~/.config/int4089`, as described in the [setup guide](diagnostics/telegram_mac_test/README.md). The guide covers the iPhone Shortcut and the bot commands.

| Hardware | Firmware |
| --- | --- |
| Arduino Uno R3 with GPS-23L fridge-door switch and Grove buzzer | [fridge_switch.ino](diagnostics/fridge_switch/fridge_switch.ino) |
| NodeMCU ESP8266 with MLX90614 sensor and the Adafruit MLX90614 Arduino library | [esp8266_sensor_test.ino](diagnostics/esp8266_sensor_test/esp8266_sensor_test.ino) |
