#!/usr/bin/python3
"""Control the Telegram bot and NFC gateway from the local INT4089 dashboard."""

import errno
import fcntl
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
import time

from diagnostics.telegram_mac_test.fridge_door import DashboardDoor
from diagnostics.telegram_mac_test.nfc_telegram_gateway import DashboardGateway
from diagnostics.telegram_mac_test.sensor_alerts import DashboardTemperature
from diagnostics.telegram_mac_test.status_data import current_status, publish, save_warning_limit

HOST = "127.0.0.1"
PORT = 8767
BOT_SCRIPT = Path(__file__).resolve().parent / "diagnostics/telegram_mac_test/fridge_mac_test.py"
STATUS_PAGE = BOT_SCRIPT.with_name("dashboard_status.html")
BOT_LOCK = Path.home() / ".config/int4089/fridge_mac_test/runner.lock"
STOPPED = ("idle", "Ready to start on this Mac.")
STOP_FAILED = ("stop_failed", "The bot did not stop. Try again or stop it in its Terminal window.")

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>VIK | Telegram Bot</title>
<style>
    :root {
        color-scheme: light;
        font-family: system-ui, sans-serif;
        color: #162e2a;
        background: #eff5f1;
    }
    * { box-sizing: border-box; }
    body { margin: 0; }
    main {
        width: min(100% - 2rem, 33rem);
        margin: clamp(2rem, 11vh, 8rem) auto;
        padding: clamp(1.5rem, 5vw, 3rem);
        background: #ffffff;
        border: 1px solid #cbdcd1;
        border-top: 5px solid #12604a;
        border-radius: 1rem;
    }
    header p { margin: 0; color: #435f54; font-weight: 600; }
    h1 { margin: .35rem 0 1.75rem; font-size: clamp(2rem, 7vw, 3rem); letter-spacing: -.04em; }
    header a { display: inline-block; margin-bottom: 1rem; color: #12604a; font-weight: 700; }
    .status {
        padding: 1rem 1.15rem;
        background: #edf4f0;
        border-left: 4px solid #617c70;
        border-radius: .35rem;
        min-height: 5.4rem;
    }
    .status[data-state="running"] { border-color: #12604a; }
    .status[data-state="starting"], .status[data-state="restarting"], .status[data-state="stopping"], .status[data-state="moved"] { border-color: #956509; }
    .status[data-state="error"], .status[data-state="stop_failed"] { border-color: #a33935; background: #fff1f0; }
    .status p { margin: .3rem 0 0; line-height: 1.5; overflow-wrap: anywhere; }
    section { margin-top: 2rem; padding-top: 1rem; border-top: 1px solid #cbdcd1; }
    h2 { margin: .25rem 0 1rem; font-size: 1.4rem; }
    .address { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: .6rem; margin: 1rem 0; }
    .address strong, .address code { display: block; }
    .address code { margin-top: .3rem; overflow-wrap: anywhere; }
    .address button { width: auto; min-height: 2.5rem; margin: 0; padding: .5rem .75rem; }
    #copy-feedback { min-height: 1.4em; margin: .4rem 0 0; color: #435f54; }
    button {
        width: 100%;
        min-height: 3.25rem;
        margin-top: 1.15rem;
        padding: .75rem 1rem;
        border: 0;
        border-radius: .5rem;
        color: white;
        background: #12604a;
        font: inherit;
        font-weight: 700;
        cursor: pointer;
    }
    button:hover:enabled { background: #0d4d3b; }
    #stop:enabled, #nfc-stop:enabled { background: #9b3431; }
    #stop:hover:enabled, #nfc-stop:hover:enabled { background: #802725; }
    button:focus-visible { outline: 3px solid #183e99; outline-offset: 3px; }
    button:disabled { color: #425851; background: #e5eee8; cursor: default; }
    .hint { margin: 1rem 0 0; color: #435f54; line-height: 1.5; }
</style>
</head>
<body>
<main>
    <header>
        <p>VIK</p>
        <h1>Telegram Bot</h1>
        <a href="/status">Current Status</a>
    </header>
    <div id="status" class="status" role="status" aria-atomic="true">
        <strong id="label">Checking status…</strong>
        <p id="detail"></p>
    </div>
    <button id="start" type="button" disabled>Start Telegram Bot</button>
    <button id="restart" type="button" disabled>Restart Telegram Bot</button>
    <button id="stop" type="button" disabled>Terminate Telegram Bot</button>
    <section aria-labelledby="nfc-heading">
        <h2 id="nfc-heading">NFC Gateway</h2>
        <div id="nfc-status" class="status" role="status" aria-atomic="true">
            <strong id="nfc-label">Checking status…</strong>
            <p id="nfc-detail"></p>
        </div>
        <div class="address">
            <div><strong>Current Mac Wi-Fi IP</strong><code id="nfc-ip">—</code></div>
            <button id="copy-ip" type="button" disabled>Copy IP</button>
        </div>
        <div class="address">
            <div><strong>iPhone NFC Shortcut URL</strong><code id="nfc-url">—</code></div>
            <button id="copy-url" type="button" disabled>Copy NFC URL</button>
        </div>
        <p id="copy-feedback" role="status"></p>
        <button id="nfc-start" type="button" disabled>Start NFC Gateway</button>
        <button id="nfc-stop" type="button" disabled>Terminate NFC Gateway</button>
    </section>
    <p class="hint">Keep the launcher’s Terminal window open while using either service.</p>
</main>
<script>
    const statusPanel = document.querySelector("#status");
    const label = document.querySelector("#label");
    const detail = document.querySelector("#detail");
    const startButton = document.querySelector("#start");
    const restartButton = document.querySelector("#restart");
    const stopButton = document.querySelector("#stop");
    let changing = false;
    let changeCount = 0;

    function render({state, message}) {
        const labels = {
            idle: "Stopped", starting: "Starting…", running: "Running",
            restarting: "Restarting…", stopping: "Stopping…", stop_failed: "Stop failed", error: "Unavailable"
        };
        if (statusPanel.dataset.state !== state || detail.textContent !== message) {
            statusPanel.dataset.state = state;
            label.textContent = labels[state];
            detail.textContent = message;
        }
        startButton.disabled = changing || !["idle", "error"].includes(state);
        restartButton.disabled = changing || !["starting", "running", "stop_failed"].includes(state);
        stopButton.disabled = changing || !["starting", "running", "stop_failed"].includes(state);
    }

    async function request(path, method = "GET") {
        const response = await fetch(path, {method, cache: "no-store"});
        if (!response.ok) throw new Error("Dashboard request failed");
        return response.json();
    }

    const disconnected = {
        state: "error",
        message: "The dashboard is unreachable. Open StartFrontendDemo.command again."
    };

    async function change(path, state, message) {
        changing = true;
        changeCount++;
        render({state, message});
        let result;
        try {
            result = await request(path, "POST");
        } catch {
            result = disconnected;
        } finally {
            changing = false;
        }
        render(result);
    }

    startButton.addEventListener("click", () => change("/api/start", "starting", "Connecting to Telegram…"));
    restartButton.addEventListener("click", () => change("/api/restart", "restarting", "Stopping the current bot before starting it again…"));
    stopButton.addEventListener("click", () => change("/api/stop", "stopping", "Stopping the bot…"));

    async function refresh() {
        const count = changeCount;
        if (!changing) {
            let result;
            try {
                result = await request("/api/status");
            } catch {
                result = disconnected;
            }
            if (!changing && count === changeCount) render(result);
        }
        setTimeout(refresh, 1000);
    }
    refresh();

    const nfcPanel = document.querySelector("#nfc-status");
    const nfcLabel = document.querySelector("#nfc-label");
    const nfcDetail = document.querySelector("#nfc-detail");
    const nfcIp = document.querySelector("#nfc-ip");
    const nfcUrl = document.querySelector("#nfc-url");
    const nfcStart = document.querySelector("#nfc-start");
    const nfcStop = document.querySelector("#nfc-stop");
    const copyIp = document.querySelector("#copy-ip");
    const copyUrl = document.querySelector("#copy-url");
    const copyFeedback = document.querySelector("#copy-feedback");
    let nfcChanging = false;
    let nfcChangeCount = 0;

    function renderNfc({state, message, ip, url, can_stop}) {
        const labels = {
            idle: "Stopped", starting: "Starting…", running: "Running", moved: "IP changed",
            stopping: "Stopping…", offline: "Wi-Fi unavailable", error: "Unavailable"
        };
        if (nfcPanel.dataset.state !== state || nfcDetail.textContent !== message) {
            nfcPanel.dataset.state = state;
            nfcLabel.textContent = labels[state];
            nfcDetail.textContent = message;
        }
        if (nfcIp.textContent !== (ip || "—")) {
            copyFeedback.textContent = "";
            nfcIp.textContent = ip || "—";
        }
        if (nfcUrl.textContent !== (url || "—")) nfcUrl.textContent = url || "—";
        copyIp.disabled = !ip;
        copyUrl.disabled = !url;
        nfcStart.disabled = nfcChanging || !ip || !["idle", "error", "moved"].includes(state);
        nfcStart.textContent = state === "moved" ? "Restart NFC Gateway" : "Start NFC Gateway";
        nfcStop.disabled = nfcChanging || !can_stop;
    }

    async function copyValue(source, message) {
        try {
            await navigator.clipboard.writeText(source.textContent);
            copyFeedback.textContent = message;
        } catch {
            copyFeedback.textContent = "Select the address and copy it manually.";
        }
    }

    copyIp.addEventListener("click", () => copyValue(nfcIp, "IP address copied."));
    copyUrl.addEventListener("click", () => copyValue(nfcUrl, "NFC URL copied."));
    async function changeNfc(path) {
        nfcChanging = true;
        nfcStart.disabled = true;
        nfcStop.disabled = true;
        nfcChangeCount++;
        let result;
        try {
            result = await request(path, "POST");
        } catch {
            result = disconnected;
        } finally {
            nfcChanging = false;
        }
        renderNfc(result);
    }

    nfcStart.addEventListener("click", () => changeNfc("/api/nfc/start"));
    nfcStop.addEventListener("click", () => changeNfc("/api/nfc/stop"));

    async function refreshNfc() {
        const count = nfcChangeCount;
        if (!nfcChanging) {
            let result;
            try {
                result = await request("/api/nfc/status");
            } catch {
                result = disconnected;
            }
            if (!nfcChanging && count === nfcChangeCount) renderNfc(result);
        }
        setTimeout(refreshNfc, 1000);
    }
    refreshNfc();
</script>
</body>
</html>
"""


class Bot:
    def __init__(self):
        self.mutex = threading.Lock()
        self.process = None
        self.closing = False
        self.state = STOPPED
        self.stop_deadline = 0
        self.door_status = DashboardDoor(lambda opened: publish("door", opened=opened))

    def status(self):
        with self.mutex:
            return self.current_status()

    def current_status(self):
        other_running = self.process is None and self.running_in_another_window()
        if self.state[0] == "stopping" and time.monotonic() >= self.stop_deadline:
            self.state = STOP_FAILED
        if self.process is None and not other_running and self.state[0] in ("stopping", "stop_failed"):
            self.state = STOPPED
        state, message = self.state
        if other_running and state not in ("restarting", "stopping", "stop_failed"):
            state, message = "running", "The bot is already running in another Terminal window."
        return {"state": state, "message": message}

    @staticmethod
    def running_in_another_window():
        try:
            with BOT_LOCK.open("rb") as lock:
                fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        except OSError:
            pass
        return False

    @staticmethod
    def external_bot_pid():
        # Look up the exact runner lock, then verify the same user's fridge bot command.
        owners = subprocess.run(
            ["/usr/sbin/lsof", "-nP", "-t", str(BOT_LOCK)],
            capture_output=True, text=True, timeout=2,
        ).stdout.split()
        if len(owners) != 1 or not owners[0].isdigit():
            raise RuntimeError("Cannot identify the bot holding the runner lock.")
        pid = owners[0]
        details = subprocess.run(
            ["/bin/ps", "-ww", "-p", pid, "-o", "uid=", "-o", "command="],
            capture_output=True, text=True, timeout=2,
        ).stdout.strip().split(maxsplit=1)
        if (len(details) != 2 or details[0] != str(os.getuid())
                or not re.search(r"(?:[/\s])fridge_mac_test\.py(?:\s|$)", details[1])):
            raise RuntimeError("The lock owner could not be verified as the fridge bot.")
        return int(pid)

    def start(self):
        with self.mutex:
            if (self.closing or self.state[0] == "restarting" or self.process is not None
                    or self.running_in_another_window()):
                return self.current_status()
            self.start_locked()
            return self.current_status()

    def start_locked(self):
        if not BOT_SCRIPT.is_file():
            self.state = ("error", "Run the launcher from the INT4089 Group Project folder.")
            return
        try:
            self.process = subprocess.Popen(
                [sys.executable, "-u", str(BOT_SCRIPT), "--door"],
                cwd=BOT_SCRIPT.parent,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except OSError:
            self.state = ("error", "Python could not start the bot. Check the project folder.")
            return
        self.state = ("starting", "Connecting to Telegram…")
        threading.Thread(target=self.watch, args=(self.process,), daemon=True).start()

    def signal_stop_locked(self):
        try:
            if self.process is not None:
                self.process.terminate()
            elif self.running_in_another_window():
                pid = self.external_bot_pid()
                if self.running_in_another_window():
                    os.kill(pid, signal.SIGTERM)
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
            print(f"Could not stop the bot: {error}", file=sys.stderr, flush=True)
            self.state = STOP_FAILED
            return False
        return True

    def stop(self):
        with self.mutex:
            status = self.current_status()
            if self.closing or status["state"] in ("restarting", "stopping"):
                return status
            if self.process is None and status["state"] not in ("running", "stop_failed"):
                self.state = STOPPED
                return self.current_status()
            self.state = ("stopping", "Stopping the bot…")
            self.stop_deadline = time.monotonic() + 5
            self.signal_stop_locked()
            return self.current_status()

    def restart(self):
        with self.mutex:
            status = self.current_status()
            if self.closing or status["state"] not in ("starting", "running", "stop_failed"):
                return status
            if not BOT_SCRIPT.is_file():
                return {"state": status["state"], "message": "Run the launcher from the INT4089 Group Project folder."}
            self.state = ("restarting", "Stopping the current bot before starting it again…")
            threading.Thread(target=self.finish_restart, daemon=True).start()
            return self.current_status()

    def finish_restart(self):
        with self.mutex:
            if self.closing or not self.signal_stop_locked():
                return
        deadline = time.monotonic() + 5
        while True:
            with self.mutex:
                if self.closing:
                    return
                if self.process is None and not self.running_in_another_window():
                    self.start_locked()
                    return
                if time.monotonic() >= deadline:
                    self.state = STOP_FAILED
                    return
            time.sleep(0.1)

    def watch(self, process):
        failure = "The bot stopped. Check Terminal for details, then try again."
        with process.stdout as output:
            for raw_line in output:
                line = raw_line.rstrip()
                print(line, flush=True)
                if line.startswith("Cannot start: "):
                    failure = line.removeprefix("Cannot start: ")
                with self.mutex:
                    if self.state[0] in ("restarting", "stopping", "stop_failed"):
                        continue
                    if line.startswith("Running. In Telegram"):
                        self.state = ("running", "Send /list in your bot chat to check that it responds.")
                    elif line == "Uno door: waiting for switch events.":
                        self.state = ("running", "Waiting for the Uno. Connect it over USB and close Arduino Serial Monitor.")
                    elif line == "Uno door: receiving switch events.":
                        self.state = ("running", "Uno connected. Open the fridge door to test the flow.")
        process.wait()
        with self.mutex:
            self.process = None
            if self.state[0] != "restarting":
                self.state = STOPPED if self.state[0] in ("stopping", "stop_failed") else ("error", failure)

    def close(self):
        with self.mutex:
            self.closing = True
            process = self.process
        self.door_status.close()
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


class Dashboard(BaseHTTPRequestHandler):
    timeout = 5

    def log_message(self, *_args):
        pass

    def reply(self, data, content_type):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'",
        )
        self.end_headers()
        self.wfile.write(data)

    def reply_status(self, status):
        self.reply(json.dumps(status).encode(), "application/json")

    def do_GET(self):
        if self.headers.get("Host") != self.server.dashboard_host:
            self.send_error(403)
        elif self.path == "/":
            self.reply(PAGE.encode(), "text/html; charset=utf-8")
        elif self.path == "/status":
            try:
                page = STATUS_PAGE.read_bytes()
            except OSError:
                self.send_error(500, "Current Status page is missing from the project folder")
                return
            self.reply(page, "text/html; charset=utf-8")
        elif self.path == "/api/current-status":
            self.reply_status(current_status())
        elif self.path == "/api/status":
            self.reply_status(self.server.bot.status())
        elif self.path == "/api/nfc/status":
            self.reply_status(self.server.nfc.status())
        else:
            self.send_error(404)

    def do_POST(self):
        if (self.headers.get("Host") != self.server.dashboard_host
                or self.headers.get("Origin") != self.server.dashboard_origin):
            self.send_error(403)
        elif self.path == "/api/warning-limit":
            try:
                length = int(self.headers.get("Content-Length", 0))
                if not 0 < length <= 1024:
                    raise ValueError("Invalid setting payload.")
                payload = json.loads(self.rfile.read(length))
                value = save_warning_limit(payload["name"], payload["value"])
            except (ValueError, TypeError, KeyError):
                self.send_error(400, "Invalid warning setting")
                return
            except OSError:
                self.send_error(500, "Could not save setting")
                return
            self.reply_status({"value": value})
        elif self.path == "/api/start":
            self.reply_status(self.server.bot.start())
        elif self.path == "/api/restart":
            self.reply_status(self.server.bot.restart())
        elif self.path == "/api/stop":
            self.reply_status(self.server.bot.stop())
        elif self.path == "/api/nfc/start":
            self.reply_status(self.server.nfc.start())
        elif self.path == "/api/nfc/stop":
            self.reply_status(self.server.nfc.stop())
        else:
            self.send_error(404)


def main():
    bot = Bot()
    nfc = DashboardGateway()
    temperature = DashboardTemperature()
    try:
        try:
            server = ThreadingHTTPServer((HOST, PORT), Dashboard)
        except OSError as error:
            if error.errno != errno.EADDRINUSE:
                raise
            server = ThreadingHTTPServer((HOST, 0), Dashboard)
    except OSError as error:
        print(f"Could not open the bot dashboard on {HOST}:{PORT}: {error}", file=sys.stderr)
        return 1
    server.dashboard_host = f"{HOST}:{server.server_port}"
    server.dashboard_origin = f"http://{server.dashboard_host}"
    server.bot = bot
    server.nfc = nfc
    print(f"Telegram bot dashboard: {server.dashboard_origin}/", flush=True)
    print("Keep this window open. Press Control-C to close the dashboard and its services.", flush=True)
    with server:
        try:
            bot.door_status.start()
            temperature.start()
            try:
                subprocess.Popen(["/usr/bin/open", server.dashboard_origin + "/"])
            except OSError:
                print("Open the dashboard URL above in your browser.", file=sys.stderr)
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            temperature.close()
            nfc.close()
            bot.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
