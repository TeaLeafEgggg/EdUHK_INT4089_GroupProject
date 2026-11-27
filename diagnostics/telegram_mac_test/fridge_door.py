"""Read 9600-baud door snapshots from the Uno switch or InputPullupSerial sketch."""

import fcntl
import os
from pathlib import Path
import select
import termios
import threading
import time
import tty


if __package__:
    from .status_data import STATUS_DIR, publish, warning_limit
else:
    from status_data import STATUS_DIR, publish, warning_limit


DISPLAY_SECONDS = 30
DEMO_SECONDS = 5


class DoorMonitor:
    def __init__(self, port=None, on_door_state=None):
        self.port = port
        self.on_door_state = on_door_state
        self.fd = None
        self.buffer = b''
        self.active = False
        self.opened_at = None
        self.warning_sent = False
        self.next_connection = 0
        self.next_warning = 0
        self.alarm_deadline = None
        self.alarm_finished = False
        self.next_alarm_report = 0
        self.raw_input = False
        self.board_limits = {}
        self.raw_candidate = None
        self.candidate_since = 0
        self.next_raw_snapshot = 0

    def connect(self):
        now = time.monotonic()
        if now < self.next_connection:
            return
        self.next_connection = now + 2
        ports = [self.port] if self.port else list(Path('/dev').glob('cu.usbmodem*'))
        if len(ports) != 1:
            return
        try:
            self.fd = os.open(ports[0], os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.ioctl(self.fd, termios.TIOCEXCL)
            tty.setraw(self.fd)
            settings = termios.tcgetattr(self.fd)
            settings[2] |= termios.CLOCAL | termios.CREAD
            settings[4] = settings[5] = termios.B9600
            termios.tcsetattr(self.fd, termios.TCSAFLUSH, settings)
        except (OSError, termios.error):
            self.close()

    def poll(self):
        if self.fd is None:
            self.connect()
        if self.fd is None:
            return False
        try:
            if not select.select([self.fd], [], [], 0)[0]:
                return False
            data = os.read(self.fd, 4096)
            if not data:
                raise OSError('Uno USB disconnected')
        except BlockingIOError:
            return False
        except OSError:
            self.close()
            print('Uno door: waiting for switch events.', flush=True)
            return False
        return self.consume(data)

    def consume(self, data):
        # Keep partial frames across reads and discard any oversized partial frame.
        *lines, self.buffer = (self.buffer + data).split(b'\n')
        if len(self.buffer) > 32:
            self.buffer = b'\x00'
        opened = False
        now = time.monotonic()
        buzzing = None
        latest_state = None
        for line in lines:
            frame = line.rstrip(b'\r')
            if frame.startswith((b'W:', b'M:')) and frame[2:].isdigit() and len(frame) <= 7:
                self.board_limits[frame[:1]] = int(frame[2:])
                continue
            if frame in (b'B:BUZZING', b'B:IDLE'):
                buzzing = frame == b'B:BUZZING'
                continue
            if frame == b'B:DONE' and self.alarm_deadline is not None:
                self.alarm_finished = True
                continue
            if frame not in (b'0', b'1', b'D:C', b'D:O', b'D:30'):
                continue
            self.raw_input = frame in (b'0', b'1')
            state = frame not in (b'0', b'D:C')
            if self.raw_input:
                if state != self.raw_candidate:
                    self.raw_candidate = state
                    self.candidate_since = now
                if now - self.candidate_since < 0.05:
                    continue
                if self.active and state == (self.opened_at is not None) and now < self.next_raw_snapshot:
                    continue
                self.next_raw_snapshot = now + 1
            else:
                self.raw_candidate = None
            if latest_state is not None and latest_state != state and self.on_door_state is not None:
                self.on_door_state(latest_state)
            latest_state = state
            if not self.active:
                self.active = True
                print('Uno door: receiving switch events.', flush=True)
            if not latest_state:
                self.opened_at = None
                self.warning_sent = False
                self.next_warning = 0
            elif self.opened_at is None:
                opened = True
                self.opened_at = time.monotonic()
                if frame == b'D:30':
                    self.opened_at -= 30  # D:30 confirms 30 elapsed seconds on the Uno.
        # InputPullupSerial streams continuously. Publish the latest sample once per read.
        if latest_state is not None and self.on_door_state is not None:
            self.on_door_state(latest_state)
        if buzzing is not None:
            publish("buzzer", buzzing=buzzing, delay_s=self.board_limits.get(b'W'),
                    muted=self.board_limits.get(b'M'))
            self.sync_buzzer_limits()
        return opened

    def sync_buzzer_limits(self):
        if self.fd is None or not self.board_limits:
            return
        desired = {b'W': int(warning_limit('buzz_delay_s')), b'M': int(warning_limit('muted'))}
        commands = [key + b':' + str(value).encode('ascii') for key, value in desired.items()
                    if self.board_limits.get(key) != value]
        if commands:
            try:
                os.write(self.fd, b'\n' + b'\n'.join(commands) + b'\n')
            except OSError:
                pass  # The next snapshot retries until the Uno reports the requested values.

    def warn(self, send):
        now = time.monotonic()
        limit = warning_limit("door_seconds")
        incident = self.opened_at
        if (self.active and incident is not None and now - incident >= limit
                and not self.warning_sent and now >= self.next_warning):
            self.next_warning = now + 10
            send(f'Fridge door warning: the door reached the {limit:g}-second limit. Please close it as soon as possible.')
            if self.opened_at == incident:
                self.warning_sent = True

    def start_alarm(self):
        if self.alarm_deadline is not None:
            return f'DEMO: The {DISPLAY_SECONDS}-second alarm countdown is already active.'
        if self.fd is None or not self.active:
            return 'Connect the Arduino Uno over USB and wait for the bot to detect it before using /alarm.'
        if self.raw_input:
            return 'The door sensor is connected. Upload fridge_switch.ino to use the buzzer alarm.'
        if self.board_limits.get(b'M') or warning_limit('muted'):
            return 'Buzzer muted. Use Enable buzzer on Current Status before starting an alarm.'
        command = f'\nB:{DEMO_SECONDS}\n'.encode('ascii')
        try:
            if os.write(self.fd, command) != len(command):
                return 'The alarm command was not sent completely. Send /alarm to retry.'
        except OSError:
            return 'Could not send the alarm to the Uno. Check USB and try /alarm again.'
        self.alarm_deadline = time.monotonic() + DEMO_SECONDS + 5
        self.alarm_finished = False
        self.next_alarm_report = 0
        return f'DEMO: Alarm set to {DISPLAY_SECONDS} seconds. Countdown started.'

    def report_alarm(self, send):
        now = time.monotonic()
        if self.alarm_deadline is None or now < self.next_alarm_report:
            return
        if self.board_limits.get(b'M') and not self.alarm_finished:
            message = 'Manual alarm cancelled because the buzzer was muted.'
        elif self.alarm_finished:
            message = f'DEMO: {DISPLAY_SECONDS}-second alarm countdown complete. Uno activated the buzzer output.'
        elif now >= self.alarm_deadline:
            message = 'The Uno did not confirm the alarm. Check USB and that the updated sketch is uploaded.'
        else:
            return
        self.next_alarm_report = now + 10
        send(message)
        self.alarm_deadline = None

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
        self.active = False
        self.board_limits.clear()
        self.raw_candidate = None
        self.buffer = b''
        self.opened_at = None
        self.warning_sent = False
        self.next_warning = 0


class BotDoorMonitor(DoorMonitor):
    """Keep USB sampling independent of Telegram network waits."""

    def __init__(self, port=None, on_door_state=None):
        super().__init__(port, on_door_state)
        self.lock = threading.Lock()
        self.open_event = False
        # Signal readiness before opening USB. The dashboard releases the port
        # on its next poll and resumes automatically when this process exits.
        STATUS_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.reader_lock = (STATUS_DIR / 'bot-door.lock').open('a')
        fcntl.flock(self.reader_lock, fcntl.LOCK_EX)
        threading.Thread(target=self._sample, daemon=True).start()

    def _sample(self):
        while True:
            with self.lock:
                if super().poll():
                    self.open_event = True
            time.sleep(0.05)

    def take_opening(self):
        with self.lock:
            opened = self.open_event
            self.open_event = False
            return opened

    def start_alarm(self):
        with self.lock:
            return super().start_alarm()


class DashboardDoor:
    """Read the door locally during periods when the bot is stopped."""

    def __init__(self, on_door_state):
        self.reader = DoorMonitor(on_door_state=on_door_state)
        self.lock = threading.Lock()
        self.closed = threading.Event()
        self.worker = None

    def start(self):
        with self.lock:
            if self.worker is None and not self.closed.is_set():
                self.worker = threading.Thread(target=self.monitor, daemon=True)
                self.worker.start()

    def bot_reads_door(self):
        try:
            with (STATUS_DIR / 'bot-door.lock').open('rb') as lock:
                fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        except FileNotFoundError:
            pass
        return False

    def monitor(self):
        try:
            while not self.closed.is_set():
                if self.bot_reads_door():
                    if self.reader.fd is not None:
                        self.reader.close()
                else:
                    self.reader.poll()
                self.closed.wait(0.2)
        finally:
            self.reader.close()

    def close(self):
        self.closed.set()
        if self.worker is not None:
            self.worker.join(1)
