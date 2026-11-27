"""Share the latest device readings between the dashboard and Mac helpers."""

from fractions import Fraction
import json
import re
import os
from pathlib import Path
import tempfile
import time


STATUS_DIR = Path.home() / '.config/int4089/dashboard_status'
LIVE_SECONDS = 6


DEFAULT_LIMITS = {'door_seconds': 5, 'ambient_c': 55, 'buzz_delay_s': 60, 'muted': 0}


def warning_limit(name, fallback=None):
    default = DEFAULT_LIMITS[name] if fallback is None else fallback
    try:
        return float((STATUS_DIR / (name + '.limit')).read_text())
    except (OSError, ValueError):
        return default


def save_warning_limit(name, raw):
    if name not in DEFAULT_LIMITS or not isinstance(raw, (int, float, str)):
        raise ValueError('Unknown warning setting.')
    value = str(raw).strip()
    if name == 'door_seconds' and not value:
        (STATUS_DIR / 'door_seconds.limit').unlink(missing_ok=True)
        return None
    if not re.fullmatch(r'(?:[0-9]+/[1-9][0-9]*|[0-9]+(?:\.[0-9]*)?|\.[0-9]+)', value):
        raise ValueError('Enter a non-negative number or a fraction such as 3/2.')
    number = Fraction(value)
    if name == 'door_seconds' and not 0 <= number <= 30:
        raise ValueError('Enter a time from 0 to 30 seconds.')
    if name == 'buzz_delay_s' and (number.denominator != 1 or not 10 <= number <= 60):
        raise ValueError('Select a buzzer start delay from 10 to 60 seconds.')
    if name == 'muted' and number not in (0, 1):
        raise ValueError('Mute must be 0 or 1.')
    if name == 'ambient_c' and (number.denominator != 1 or not 20 <= number <= 90):
        raise ValueError('Select a whole temperature from 20 to 90 °C.')
    STATUS_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile(mode='w', dir=STATUS_DIR, delete=False) as out:
        out.write(str(float(number)))
    try:
        os.replace(out.name, STATUS_DIR / (name + '.limit'))
    finally:
        Path(out.name).unlink(missing_ok=True)
    return float(number)


def publish(source, **values):
    temporary = None
    try:
        STATUS_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
        now = time.time()
        if source == 'door' and values.get('opened'):
            previous = latest('door')
            start = now
            if previous and previous.get('opened') and 0 <= now - previous['seen_at'] <= LIVE_SECONDS:
                start = previous.get('opened_since', previous['seen_at'])
            values['opened_since'] = start
        with tempfile.NamedTemporaryFile(mode='w', dir=STATUS_DIR, delete=False) as output:
            temporary = Path(output.name)
            json.dump({**values, 'seen_at': now}, output, allow_nan=False)
        os.replace(temporary, STATUS_DIR / f'{source}.json')
        temporary = None
    except (OSError, ValueError):
        # Status data must not interrupt an alarm or Telegram message.
        pass
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except OSError:
                pass


def latest(source):
    try:
        data = json.loads((STATUS_DIR / f'{source}.json').read_text())
        if isinstance(data, dict) and isinstance(data.get('seen_at'), (int, float)):
            return data
    except (OSError, ValueError):
        pass
    return None


def is_live(reading):
    return reading is not None and 0 <= time.time() - reading['seen_at'] <= LIVE_SECONDS


def current_status():
    readings = {source: latest(source) for source in ('door', 'buzzer', 'temperature', 'nfc')}
    for source in ('door', 'buzzer', 'temperature'):
        reading = readings[source]
        if reading is not None:
            reading['live'] = is_live(reading)
    if readings['temperature'] is not None:
        readings['temperature'].pop('object', None)
    readings['limits'] = {name: warning_limit(name) for name in DEFAULT_LIMITS}
    return readings
