#!/usr/bin/env python3
"""INT4089 local Wi-Fi NFC receiver for the existing Telegram fridge bot."""
import argparse
import errno
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

if __package__:
    from .status_data import publish
else:
    from status_data import publish

DEFAULT_BOT = Path(__file__).resolve().with_name("fridge_mac_test.py")
DEFAULT_SETTINGS = Path.home() / ".config/int4089/nfc_gateway"
NFC_PORT = 8766
STOPPED_MESSAGE = "Start the gateway before scanning an NFC tag."
DEFAULT_ITEMS = {"salt_01": "Salt", "sugar_01": "Sugar"}
TELEGRAM_DISPLAY_NAMES = {"oil_01": "Fruit Knife", "pepper_01": "Meat Knife"}
MAX_BODY = 1024


class GatewayError(Exception):
    pass


def load_bot(path):
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise GatewayError("Existing bot script was not found. Use --bot-script with its full path.")
    spec = importlib.util.spec_from_file_location("_int4089_existing_fridge_bot", str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_settings(directory):
    directory = Path(directory).expanduser()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    key_path = directory / "access_key.txt"
    try:
        descriptor = os.open(str(key_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        key = key_path.read_text(encoding="utf-8").strip()
    else:
        key = secrets.token_urlsafe(32)
        with os.fdopen(descriptor, "w", encoding="utf-8") as target:
            target.write(key + "\n")
    if len(key) < 32 or not key.isascii():
        raise GatewayError("The saved NFC access key is invalid.")
    items_path = directory / "ingredients.json"
    try:
        descriptor = os.open(str(items_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        pass
    else:
        with os.fdopen(descriptor, "w", encoding="utf-8") as target:
            json.dump(DEFAULT_ITEMS, target, indent=2)
            target.write("\n")
    try:
        items = json.loads(items_path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        raise GatewayError("Cannot read ingredients.json.") from None
    if not isinstance(items, dict) or not items:
        raise GatewayError("ingredients.json must contain item IDs and ingredient names.")
    for item_id, name in items.items():
        if not isinstance(item_id, str) or not 1 <= len(item_id) <= 64:
            raise GatewayError("An ingredient ID is invalid.")
        if not isinstance(name, str) or not name.strip() or len(name) > 120:
            raise GatewayError("An ingredient name is invalid.")
    return key, items


def private_ipv4(value):
    try:
        address = ipaddress.IPv4Address(value)
    except ipaddress.AddressValueError:
        return False
    return (
        address.is_private
        and not address.is_unspecified
        and not address.is_link_local
        and not address.is_multicast
        and not address.is_reserved
        and not address.is_loopback
    )


def mac_lan_address():
    for interface in ("en0", "en1", "en2", "en3"):
        try:
            result = subprocess.run(
                ["/sbin/ifconfig", interface, "inet"],
                capture_output=True, text=True, check=False, timeout=1,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        for line in result.stdout.splitlines():
            fields = line.split()
            if len(fields) >= 2 and fields[0] == "inet" and private_ipv4(fields[1]):
                return fields[1]
    raise GatewayError("Connect the Mac to Wi-Fi or an iPhone hotspot to get a local IPv4 address.")


def make_handler(api, access_key, ingredients, on_scan=None):
    class NFCHandler(BaseHTTPRequestHandler):
        server_version = "INT4089NFC/1"
        sys_version = ""

        def setup(self):
            super().setup()
            self.connection.settimeout(15)

        def log_message(self, format_string, *args):
            # Never log request paths, headers, access keys or Telegram URLs.
            pass

        def reply(self, status, payload, allowed_method=None):
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            if allowed_method is not None:
                self.send_header("Allow", allowed_method)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = urlsplit(self.path).path.removesuffix("/")
            if path == "/health":
                self.reply(200, {"ok": True, "service": "INT4089 NFC gateway"})
            elif path == "/nfc":
                self.reply(405, {"ok": False, "error": "Set the iPhone Shortcut method to POST for /nfc."}, "POST")
            else:
                self.reply(404, {"ok": False, "error": "Open /health to test the connection."})

        def do_POST(self):
            path = urlsplit(self.path).path.removesuffix("/")
            if path == "/health":
                self.reply(405, {"ok": False, "error": "Set the iPhone Shortcut URL to /nfc for scans."}, "GET")
                return
            if path != "/nfc":
                self.reply(404, {"ok": False, "error": "Set the iPhone Shortcut URL to /nfc for scans."})
                return
            supplied_key = self.headers.get("X-NFC-Key", "")
            if not supplied_key.isascii() or not secrets.compare_digest(supplied_key, access_key):
                self.reply(401, {"ok": False, "error": "Invalid NFC access key"})
                return
            if self.headers.get("Transfer-Encoding"):
                self.reply(400, {"ok": False, "error": "Use a JSON request body"})
                return
            content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            if content_type != "application/json":
                self.reply(415, {"ok": False, "error": "Content-Type must be application/json"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = 0
            if not 0 < length <= MAX_BODY:
                self.reply(400, {"ok": False, "error": "Invalid request size"})
                return
            try:
                raw = self.rfile.read(length)
                if len(raw) != length:
                    raise ValueError()
                payload = json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeError, OSError):
                self.reply(400, {"ok": False, "error": "Invalid JSON"})
                return
            if not isinstance(payload, dict) or not isinstance(payload.get("item_id"), str):
                self.reply(400, {"ok": False, "error": "Provide item_id as text"})
                return
            item_id = payload["item_id"].strip()
            if item_id not in ingredients:
                self.reply(404, {"ok": False, "error": "Unknown ingredient ID"})
                return
            ingredient = ingredients[item_id]
            if on_scan is not None:
                on_scan(item_id, ingredient)
            display_name = TELEGRAM_DISPLAY_NAMES.get(item_id, ingredient)
            message = "Object detected: " + display_name
            try:
                api.send(message)
            except Exception:
                # The existing bot wrapper can include private values in some
                # exception types. Return a fixed error instead of the exception.
                self.reply(502, {"ok": False, "error": "Telegram delivery failed; check the Mac connection and bot settings"})
                print("NFC request failed: Telegram delivery was not confirmed.", flush=True)
                return
            print("NFC identified: " + item_id, flush=True)
            self.reply(200, {
                "ok": True, "item_id": item_id,
                "ingredient": ingredient, "message": message,
            })
    return NFCHandler


def build_gateway(host, port, settings_dir=DEFAULT_SETTINGS, bot_script=DEFAULT_BOT):
    bot = load_bot(bot_script)
    try:
        token, chat = bot.credentials()
        api = bot.Telegram(token, chat)
        identity = api.call("getMe")
        if api.call("getChat", chat_id=chat).get("type") != "private":
            raise GatewayError("The existing bot settings must use a private Telegram chat.")
    except GatewayError:
        raise
    except Exception:
        raise GatewayError("Cannot verify the existing bot settings or Telegram connection. Keep using the same Mac account as the fridge bot.") from None
    access_key, ingredients = load_settings(settings_dir)
    try:
        handler = make_handler(api, access_key, ingredients,
                               lambda tag, ingredient: publish('nfc', tag=tag, ingredient=ingredient))
        server = ThreadingHTTPServer((host, port), handler)
    except OSError as error:
        if error.errno == errno.EADDRINUSE:
            raise GatewayError(f"Port {port} is already in use. Close the older NFC gateway and try again.") from None
        raise GatewayError("Cannot open the local address/port. Check the Wi-Fi address and whether another NFC gateway is running.") from None
    return server, identity, access_key


class DashboardGateway:
    def __init__(self):
        self.lock = threading.Lock()
        self.server = None
        self.host = None
        self.closed = False
        self.state = "idle"
        self.message = STOPPED_MESSAGE

    @staticmethod
    def current_ip():
        try:
            return mac_lan_address()
        except GatewayError:
            return None

    def status(self):
        ip = self.current_ip()
        with self.lock:
            return self.status_for(ip)

    def status_for(self, ip):
        state, message = self.state, self.message
        if ip is None and state != "stopping":
            state, message = "offline", "Connect the Mac to Wi-Fi or an iPhone hotspot."
        elif state == "running" and ip != self.host:
            state, message = "moved", "The IP changed. Restart the gateway to use the new address."
        return {"state": state, "message": message, "ip": ip,
                "can_stop": self.state in ("starting", "running"),
                "url": f"http://{ip}:{NFC_PORT}/nfc" if ip else None}

    def start(self):
        ip = self.current_ip()
        with self.lock:
            if self.closed or ip is None or self.state in ("starting", "stopping"):
                return self.status_for(ip)
            if self.server is not None and self.host == ip:
                return self.status_for(ip)
            previous, self.server = self.server, None
            self.state, self.message = "starting", "Connecting to Telegram…"
            threading.Thread(target=self.serve, args=(ip, previous), daemon=True).start()
            return self.status_for(ip)

    def serve(self, host, previous):
        server = None
        published = False
        failure = None
        try:
            if previous is not None:
                previous.shutdown()
            with self.lock:
                if self.closed or self.state == "stopping":
                    return
            server, _, _ = build_gateway(host, NFC_PORT)
            with server:
                with self.lock:
                    if self.closed or self.state == "stopping":
                        return
                    self.server, self.host = server, host
                    self.state, self.message = "running", "Ready to receive NFC scans on this address."
                    published = True
                print(f"NFC gateway running at http://{host}:{NFC_PORT}/nfc", flush=True)
                server.serve_forever(poll_interval=0.2)
        except GatewayError as error:
            failure = str(error)
        except OSError:
            failure = "Check the NFC settings files and folder permissions."
        finally:
            with self.lock:
                if not published or self.server is server:
                    self.server, self.host = None, None
                    if failure and self.state != "stopping":
                        self.state, self.message = "error", failure
                    else:
                        self.state, self.message = "idle", STOPPED_MESSAGE

    def stop(self):
        ip = self.current_ip()
        with self.lock:
            if self.state in ("starting", "running"):
                self.state, self.message = "stopping", "Stopping the NFC gateway…"
                if self.server is not None:
                    threading.Thread(target=self.server.shutdown, daemon=True).start()
            return self.status_for(ip)

    def close(self):
        with self.lock:
            self.closed = True
            server = self.server
        if server is not None:
            server.shutdown()


def run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bot-script", type=Path, default=DEFAULT_BOT)
    addresses = parser.add_mutually_exclusive_group()
    addresses.add_argument("--lan", action="store_true", help="Listen on the Mac's local network address")
    addresses.add_argument("--host", default="127.0.0.1", help="Explicit local IPv4 address")
    parser.add_argument("--port", type=int, default=NFC_PORT)
    parser.add_argument("--settings-dir", type=Path, default=DEFAULT_SETTINGS)
    args = parser.parse_args()
    host = mac_lan_address() if args.lan else args.host
    if host != "127.0.0.1" and not private_ipv4(host):
        raise GatewayError("Choose a private local IPv4 address; this test receiver is for local Wi-Fi.")
    if not 1 <= args.port <= 65535:
        raise GatewayError("The port must be between 1 and 65535.")
    server, identity, access_key = build_gateway(host, args.port, args.settings_dir, args.bot_script)
    print("NFC gateway running", flush=True)
    print("Bot: @" + identity.get("username", "(existing bot)"), flush=True)
    print("URL: http://" + host + ":" + str(args.port) + "/nfc", flush=True)
    print("Method: POST", flush=True)
    print("Header name: X-NFC-Key", flush=True)
    print("Header value: " + access_key, flush=True)
    print('JSON body: {"item_id": "salt_01"}', flush=True)
    print("Keep this Terminal open. The existing fridge bot can remain running.", flush=True)
    print("Use the iPhone and Mac on the same Wi-Fi for this local test.", flush=True)
    print("Press Ctrl+C to stop only this NFC gateway.", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print("\nNFC gateway stopped.")
    except GatewayError as error:
        print("Cannot start: " + str(error), file=sys.stderr)
        sys.exit(1)
    except Exception:
        print("Cannot start the NFC gateway. Check the local file and folder permissions.", file=sys.stderr)
        sys.exit(1)
