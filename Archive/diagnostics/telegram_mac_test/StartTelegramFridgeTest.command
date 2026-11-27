#!/bin/bash
cd -- "$(dirname -- "$0")" || exit 1
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 fridge_mac_test.py
printf '\nPress Enter to close this window.\n'
read -r _fridge_test_close
