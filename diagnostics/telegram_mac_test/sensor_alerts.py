"""Send ESP8266 ambient temperature alerts to the existing private Telegram chat."""

import argparse
from contextlib import nullcontext
import errno
import fcntl
import math
import os
from pathlib import Path
import re
import select
import sys
import termios
import threading
import time
import tty

if __package__:
    from .fridge_mac_test import SetupError, Telegram, TelegramError, credentials
    from . import status_data
else:
    from fridge_mac_test import SetupError, Telegram, TelegramError, credentials
    import status_data

DEFAULT_TEMPERATURE_THRESHOLD = 55


def parse_ambient(line):
    for field in line.strip().split(' | '):
        match = re.fullmatch(r'Ambient: (-?\d+\.\d+) C', field)
        if match:
            value = float(match[1])
            return value if math.isfinite(value) else None
    return None


def claim_temperature_alerts(wait=False):
    status_data.STATUS_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = (status_data.STATUS_DIR / 'temperature-alerts.lock').open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX if wait else fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        return None
    except OSError:
        lock.close()
        raise
    return lock


class SensorAlerts:
    def __init__(self, send, temperature_threshold=DEFAULT_TEMPERATURE_THRESHOLD, send_error=TelegramError):
        self.send = send
        self.send_error = send_error
        self.temperature_threshold = temperature_threshold
        self.sent = False
        self.clear_samples = 0
        self.retry_at = 0
        self.last_seen = None

    def process(self, line):
        self.process_ambient(parse_ambient(line))

    def process_latest(self, port=None):
        reading = status_data.latest('temperature')
        if (status_data.is_live(reading) and (port is None or reading.get('port') == str(port))
                and reading['seen_at'] != self.last_seen):
            self.last_seen = reading['seen_at']
            self.process_ambient(reading.get('ambient'))

    def process_ambient(self, ambient):
        if ambient is None:
            self.clear_samples = 0
            return
        if ambient <= status_data.warning_limit('ambient_c', self.temperature_threshold):
            if self.sent:
                self.clear_samples += 1
                if self.clear_samples == 3:
                    self.sent = False
                    self.retry_at = 0
            return
        self.clear_samples = 0
        if self.sent or time.monotonic() < self.retry_at:
            return
        try:
            self.send(f'Do not touch! Heat warning: the detected temperature is {ambient:.1f}°C.')
        except self.send_error as error:
            print(f'{error} Will retry in 10 seconds if the reading is still high.', file=sys.stderr, flush=True)
            self.retry_at = time.monotonic() + 10
        else:
            self.sent = True


def esp_ports():
    devices = Path('/dev')
    return sorted(set(devices.glob('cu.usbserial*')) | set(devices.glob('cu.wchusbserial*')))


def read_temperatures(port, on_reading=None, stop=None):
    fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.ioctl(fd, termios.TIOCEXCL)
        tty.setraw(fd)
        settings = termios.tcgetattr(fd)
        settings[2] |= termios.CLOCAL | termios.CREAD
        settings[4] = settings[5] = termios.B9600
        termios.tcsetattr(fd, termios.TCSAFLUSH, settings)
        buffer = b''
        while stop is None or not stop.is_set():
            if not select.select([fd], [], [], 1)[0]:
                continue
            try:
                data = os.read(fd, 4096)
            except BlockingIOError:
                continue
            if not data:
                raise SetupError('The serial connection closed. Reconnect the ESP8266 and run the command again.')
            *lines, buffer = (buffer + data).split(b'\n')
            if len(buffer) > 512:
                buffer = b'\x00'
            for raw in lines:
                line = raw.decode('ascii', errors='replace')
                ambient = parse_ambient(line)
                if ambient is not None:
                    status_data.publish('temperature', port=str(port), ambient=ambient)
                if on_reading is not None:
                    on_reading(ambient)
    finally:
        os.close(fd)


class DashboardTemperature:
    def __init__(self):
        self.lock = threading.Lock()
        self.closed = threading.Event()
        self.worker = None

    def start(self):
        with self.lock:
            if self.worker is None and not self.closed.is_set():
                self.worker = threading.Thread(target=self.monitor, daemon=True)
                self.worker.start()

    def monitor(self):
        while not self.closed.is_set():
            ports = esp_ports()
            if len(ports) == 1:
                try:
                    read_temperatures(ports[0], stop=self.closed)
                except (OSError, SetupError, termios.error):
                    pass
            self.closed.wait(2)

    def close(self):
        self.closed.set()
        with self.lock:
            worker = self.worker
        if worker is not None:
            worker.join(2)


def run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', help='ESP8266 serial port, e.g. /dev/cu.usbserial-140')
    parser.add_argument('--dry-run', action='store_true', help='Print alerts without sending them')
    parser.add_argument('--temperature-threshold', type=float, default=DEFAULT_TEMPERATURE_THRESHOLD,
                        help='Ambient alarm threshold in °C (default: %(default)s)')
    args = parser.parse_args()
    if not math.isfinite(args.temperature_threshold):
        parser.error('--temperature-threshold must be a finite number')
    port = args.port
    if not port:
        ports = esp_ports()
        if len(ports) != 1:
            available = ', '.join(str(path) for path in ports) or 'none'
            parser.error(f'expected one ESP8266 USB serial port; found {available}. '
                         'Connect the ESP8266 or pass its port with --port.')
        port = ports[0]

    def send(message):
        if not args.dry_run:
            api.send(message)
        label = 'DRY RUN (no Telegram message)' if args.dry_run else 'Telegram sent'
        print(f'{label}: {message}', flush=True)

    if not args.dry_run:
        api = Telegram(*credentials())
    alerts = SensorAlerts(send, temperature_threshold=args.temperature_threshold)
    print(f'Reading ESP8266 on {port} at 9600 baud. Press Ctrl+C to stop.', flush=True)
    print(f'Heat alert: ambient > {args.temperature_threshold:g} °C.', flush=True)
    with (nullcontext() if args.dry_run else claim_temperature_alerts(wait=True)):
        waiting = False
        while True:
            try:
                read_temperatures(port, on_reading=alerts.process_ambient)
            except OSError as error:
                if error.errno not in (errno.EAGAIN, errno.EBUSY):
                    raise
                if not waiting:
                    print('ESP8266 port is in use. Waiting for readings from the dashboard or for the port to become free.', flush=True)
                    waiting = True
                alerts.process_latest(port)
                time.sleep(0.5)


if __name__ == '__main__':
    try:
        run()
    except KeyboardInterrupt:
        print('\nSensor alerts stopped.')
    except (OSError, SetupError) as error:
        sys.exit(f'Sensor alerts stopped: {error}. Check USB and close Arduino Serial Monitor.')
