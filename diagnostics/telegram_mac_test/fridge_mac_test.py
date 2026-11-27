#!/usr/bin/env python3
"""Mac-only fridge conversation test. Uses stdlib and existing private bot settings."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import socket
import sqlite3
import ssl
import sys
import time
import urllib.error
import urllib.request

PAGE_SIZE = 10
LAYER_LABELS = ('Layer 1', 'Layer 2', 'Layer 3')
ENTRY_STAGES = ('name', 'layer', 'expiry')
HONG_KONG = dt.timezone(dt.timedelta(hours=8))
WELCOME = 'Welcome to VIK, Vision Intervention Kit.\n\nFor the full list of command, /help'


def valid_name(text):
    return bool(text and not text.startswith('/') and len(text.encode('utf-8')) <= 64
                and not any(ord(char) < 32 or ord(char) == 127 for char in text))


def valid_expiry(text):
    try:
        if not re.fullmatch(r'20[0-9]{2}-[0-9]{2}-[0-9]{2}', text):
            return False
        dt.date.fromisoformat(text)
        return True
    except ValueError:
        return False


def item_number(text):
    if not re.fullmatch(r'[1-9][0-9]{0,18}', text):
        return None
    number = int(text)
    return number if number <= 9223372036854775807 else None


class SetupError(Exception):
    pass


class TelegramError(Exception):
    pass


def credentials():
    token, chat = os.environ.get('FRIDGE_BOT_TOKEN'), os.environ.get('FRIDGE_CHAT_ID')
    if token and chat:
        return token, chat
    home = Path.home() / '.config/int4089'
    for source in (home / 'countdown_gateway/secrets.h', home / 'telegram_test/secrets.h'):
        try:
            content = source.read_text()
        except OSError:
            continue
        values = {}
        for key in ('BOT_TOKEN', 'CHAT_ID'):
            match = re.search(r'\b' + key + r'\s*(?:\[\s*\])?\s*=\s*("(?:\\.|[^"\\])*")', content)
            if match:
                try:
                    values[key] = json.loads(match.group(1))
                except ValueError:
                    pass
        if all(values.get(key) and not values[key].startswith('YOUR_') for key in ('BOT_TOKEN', 'CHAT_ID')):
            return values['BOT_TOKEN'], values['CHAT_ID']
    raise SetupError('Existing private bot settings were not found. Set FRIDGE_BOT_TOKEN and FRIDGE_CHAT_ID locally; do not paste your token into chat.')


class Telegram:
    def __init__(self, token, chat):
        self.token, self.chat = token, str(chat)

    def call(self, method, **payload):
        request = urllib.request.Request(
            'https://api.telegram.org/bot' + self.token + '/' + method,
            data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                result = json.load(response)
        except urllib.error.HTTPError as error:
            # Do not print exceptions/URLs: those contain the bot token.
            if error.code == 409:
                raise SetupError('Another process is polling this bot, or it has a webhook. Stop the other bot test before using this one.') from None
            if error.code in (401, 403):
                raise SetupError('Telegram rejected the bot token or access to this private chat.') from None
            raise TelegramError('Telegram returned HTTP ' + str(error.code)) from None
        except urllib.error.URLError as error:
            reason = error.reason
            if isinstance(reason, socket.gaierror):
                message = 'DNS lookup failed for api.telegram.org.'
            elif isinstance(reason, ssl.SSLCertVerificationError):
                message = 'Python could not verify the Telegram HTTPS certificate.'
            elif isinstance(reason, ssl.SSLError):
                message = 'The Telegram HTTPS handshake failed.'
            elif isinstance(reason, TimeoutError):
                message = 'The connection to Telegram timed out.'
            else:
                message = 'Python could not connect to api.telegram.org.'
            raise TelegramError(message) from None
        except (TimeoutError, OSError, ValueError):
            raise TelegramError('Telegram did not return a complete response. Check the connection.') from None
        if result.get('ok') is not True:
            raise TelegramError('Telegram rejected the request.')
        return result['result']

    def send(self, text, question=False, layer_choices=False):
        payload = {'chat_id': self.chat, 'text': text}
        if layer_choices:
            payload['reply_markup'] = {'keyboard': [list(LAYER_LABELS)], 'resize_keyboard': True,
                                       'one_time_keyboard': True}
        elif question:
            payload['reply_markup'] = {'force_reply': True, 'selective': True}
        return int(self.call('sendMessage', **payload)['message_id'])


class Fridge:
    def __init__(self, path):
        self.db = sqlite3.connect(str(path))
        self.db.execute('PRAGMA synchronous=FULL')
        with self.db:
            self.db.execute('CREATE TABLE IF NOT EXISTS conversation (id INTEGER PRIMARY KEY CHECK(id=1), stage TEXT NOT NULL, name TEXT NOT NULL, opened REAL NOT NULL, prompt INTEGER NOT NULL, offset INTEGER NOT NULL, initialised INTEGER NOT NULL)')
            self.db.execute("INSERT OR IGNORE INTO conversation(id,stage,name,opened,prompt,offset,initialised) VALUES (1,'idle','',0,0,0,0)")
            self.db.execute('CREATE TABLE IF NOT EXISTS foods (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, expiry TEXT NOT NULL, stored REAL NOT NULL, notified INTEGER NOT NULL DEFAULT 0, test_pending INTEGER NOT NULL DEFAULT 0, expiry_notified TEXT)')
            if 'expiry_notified' not in {row[1] for row in self.db.execute('PRAGMA table_info(foods)')}:
                self.db.execute('ALTER TABLE foods ADD COLUMN expiry_notified TEXT')
            if 'layer' not in {row[1] for row in self.db.execute('PRAGMA table_info(foods)')}:
                self.db.execute('ALTER TABLE foods ADD COLUMN layer INTEGER CHECK(layer BETWEEN 1 AND 3)')
            columns = {row[1] for row in self.db.execute('PRAGMA table_info(conversation)')}
            if 'layer' not in columns:
                self.db.execute('ALTER TABLE conversation ADD COLUMN layer INTEGER CHECK(layer BETWEEN 1 AND 3)')
            if 'editing_id' not in columns:
                self.db.execute('ALTER TABLE conversation ADD COLUMN editing_id INTEGER NOT NULL DEFAULT 0')
            if 'display_sort' not in columns:
                self.db.execute("ALTER TABLE conversation ADD COLUMN display_sort TEXT NOT NULL DEFAULT 'expiry'")
            if 'numbering_ready' not in columns:
                self.db.execute('ALTER TABLE conversation ADD COLUMN numbering_ready INTEGER NOT NULL DEFAULT 0')
                if not self.db.execute('SELECT 1 FROM foods LIMIT 1').fetchone():
                    self.db.execute('UPDATE conversation SET numbering_ready=1 WHERE id=1')

    def state(self):
        return self.db.execute('SELECT stage,name,opened,prompt,offset,initialised FROM conversation WHERE id=1').fetchone()

    def start(self, now):
        if self.state()[0] != 'idle':
            return False
        self.db.execute("UPDATE conversation SET stage='name',name='',layer=NULL,opened=?,prompt=0 WHERE id=1", (now,))
        return True

    def display_sort(self):
        return self.db.execute('SELECT display_sort FROM conversation WHERE id=1').fetchone()[0]

    def order_sql(self, sort=None):
        return {'expiry': 'expiry ASC, stored ASC, id ASC',
                'added': 'stored ASC, id ASC',
                'name': 'name COLLATE NOCASE ASC, expiry ASC, id ASC'}[sort or self.display_sort()]

    def visible_number(self, item_id):
        rows = self.db.execute('SELECT id FROM foods ORDER BY ' + self.order_sql())
        return next((number for number, row in enumerate(rows, 1) if row[0] == item_id), None)

    def resolve_number(self, number):
        if number is None:
            return None
        row = self.db.execute('SELECT id FROM foods ORDER BY ' + self.order_sql() + ' LIMIT 1 OFFSET ?', (number-1,)).fetchone()
        return row[0] if row else None

    def question(self):
        stage, name, *_ = self.state()
        if stage == 'name':
            return 'What food are you putting in the fridge? Send the food name or /skip to skip this entry.'
        if stage == 'layer':
            return f'Which fridge layer is {name} on? Choose Layer 1, Layer 2, or Layer 3. Send /skip to discard this entry.'
        if stage.startswith('edit_'):
            item_id = self.editing_id()
            number = self.visible_number(item_id)
            label = '#' + str(number) if number else 'the selected food'
            if stage == 'edit_field':
                return 'Editing ' + label + '. Reply name or expiry to choose a field. Send /cancel to leave this edit.'
            if stage == 'edit_name':
                return 'Send the new food name for ' + label + '. Send /cancel to leave it unchanged.'
            return 'Send the new expiry date for ' + label + ' in YYYY-MM-DD format. Send /cancel to leave it unchanged.'
        return 'What is the expiry date for ' + name + '? Send YYYY-MM-DD, for example 2026-12-01, or /skip to discard this entry.'

    def finish_entry(self):
        self.db.execute("UPDATE conversation SET stage='idle',name='',layer=NULL,opened=0,prompt=0 WHERE id=1")

    def editing_id(self):
        return self.db.execute('SELECT editing_id FROM conversation WHERE id=1').fetchone()[0]

    def finish_edit(self):
        self.db.execute("UPDATE conversation SET stage='idle',editing_id=0,prompt=0 WHERE id=1")

    def edit_value(self, item_id, field, value):
        row = self.db.execute('SELECT name,expiry FROM foods WHERE id=?', (item_id,)).fetchone()
        if not row:
            return 'That food was not found. Use /list to see the current item numbers.'
        number = self.visible_number(item_id)
        if field == 'name':
            if not valid_name(value):
                return 'Please send a food name up to 64 UTF-8 bytes, without commands or line breaks.'
            self.db.execute('UPDATE foods SET name=? WHERE id=?', (value, item_id))
        else:
            if not valid_expiry(value):
                return 'Please send a real expiry date in YYYY-MM-DD format (2000-2099).'
            self.db.execute('UPDATE foods SET expiry=? WHERE id=?', (value, item_id))
        new_number = self.visible_number(item_id)
        moved = ' It is now #' + str(new_number) + '.' if new_number != number else ''
        return 'Updated #' + str(number) + ': ' + ('name = ' if field == 'name' else 'expiry = ') + value + '.' + moved + ' Use /list for the current numbers.'

    def list_food(self, text):
        parts = text.split()
        sort, page = 'expiry', 1
        if len(parts) > 1:
            if parts[1] in ('expiry', 'added', 'name'):
                sort = parts[1]
                if len(parts) == 3:
                    page = item_number(parts[2])
                elif len(parts) > 3:
                    page = None
            elif len(parts) == 2:
                sort = self.display_sort()
                page = item_number(parts[1])
            else:
                page = None
        if page is None:
            return 'Use /list, /list 2, /list added, or /list name. You can add a page number after the sort, for example /list added 2.'
        count = self.db.execute('SELECT COUNT(*) FROM foods').fetchone()[0]
        if not count:
            self.db.execute('UPDATE conversation SET display_sort=?,numbering_ready=1 WHERE id=1', (sort,))
            return 'No test food recorded. Send /open to start.'
        pages = (count + PAGE_SIZE-1)//PAGE_SIZE
        if page > pages:
            return 'Page not found. There are ' + str(pages) + ' pages. Send /list to start.'
        order = self.order_sql(sort)
        self.db.execute('UPDATE conversation SET display_sort=?,numbering_ready=1 WHERE id=1', (sort,))
        rows = self.db.execute('SELECT id,name,expiry,stored,layer FROM foods ORDER BY ' + order + ' LIMIT ? OFFSET ?',
                               (PAGE_SIZE, (page-1)*PAGE_SIZE)).fetchall()
        label = {'expiry': 'earliest expiry first', 'added': 'oldest added first', 'name': 'name A-Z'}[sort]
        heading = 'Food list (' + label + ') - page ' + str(page) + '/' + str(pages) + '\n'
        entries = '\n'.join('#' + str(number) + ': ' + name + (f' | Layer {layer}' if layer else '') + ' | expiry ' + expiry + ' | added ' +
                            dt.datetime.fromtimestamp(stored, HONG_KONG).strftime('%Y-%m-%d')
                            for number, (_, name, expiry, stored, layer) in enumerate(rows, (page-1)*PAGE_SIZE+1))
        footer = '\nUse these list numbers with /edit NUMBER, /view NUMBER or /delete NUMBER. Numbers change after adding, deleting or reordering; check /list again.'
        if page < pages:
            footer += '\nNext page: /list ' + sort + ' ' + str(page+1)
        return heading + entries + footer

    def view_food(self, item_id):
        row = self.db.execute('SELECT name,expiry,stored,expiry_notified,layer FROM foods WHERE id=?', (item_id,)).fetchone()
        if not row:
            return 'That food was not found. Use /list to see the current item numbers.'
        name, expiry, stored, expiry_notified, layer = row
        added = dt.datetime.fromtimestamp(stored, HONG_KONG).strftime('%Y-%m-%d %H:%M')
        number = self.visible_number(item_id)
        return ('#' + str(number) + ': ' + name + (f'\nLayer {layer}' if layer else '') + '\nExpiry: ' + expiry + '\nAdded: ' + added +
                ' (Hong Kong time)\nExpiry reminder: ' + ('already sent' if expiry_notified == expiry else 'not sent yet') +
                '\n/edit ' + str(number) + ' - edit name or expiry\n/delete ' + str(number) + ' - remove this item')

    def handle(self, text, message_id, now):
        stage, _, _, prompt, *_ = self.state()
        text = text.strip()
        if text == '/start':
            return WELCOME
        if stage != 'idle':
            if not prompt or message_id <= prompt:
                return None
            if stage.startswith('edit_'):
                if text == '/cancel':
                    self.finish_edit()
                    return 'Edit cancelled. The food record was left unchanged.'
                item_id = self.editing_id()
                if not self.db.execute('SELECT 1 FROM foods WHERE id=?', (item_id,)).fetchone():
                    self.finish_edit()
                    return 'That food item no longer exists. Use /list.'
                if stage == 'edit_field':
                    fields = {'name': 'edit_name', 'food name': 'edit_name', '1': 'edit_name',
                              'expiry': 'edit_expiry', 'expiry date': 'edit_expiry', 'date': 'edit_expiry', '2': 'edit_expiry'}
                    selected = fields.get(text.lower())
                    if not selected:
                        return 'Reply name or expiry. Send /cancel to leave this edit.'
                    self.db.execute('UPDATE conversation SET stage=?,prompt=0 WHERE id=1', (selected,))
                    return None
                response = self.edit_value(item_id, 'name' if stage == 'edit_name' else 'expiry', text)
                if response.startswith('Updated #'):
                    self.finish_edit()
                return response
            if text == '/skip':
                self.finish_entry()
                return 'Entry skipped. No food was added.'
            if stage == 'name':
                if not valid_name(text):
                    return 'Please send a food name up to 64 UTF-8 bytes, or /skip to skip this entry.'
                self.db.execute("UPDATE conversation SET stage='layer',name=?,prompt=0 WHERE id=1", (text,))
                return None
            if stage == 'layer':
                choice = re.fullmatch(r'(?:layer +)?([1-3])', text, re.IGNORECASE)
                if not choice:
                    return self.question()
                self.db.execute("UPDATE conversation SET stage='expiry',layer=?,prompt=0 WHERE id=1",
                                (int(choice[1]),))
                return None
            if not valid_expiry(text):
                return 'Please send a real expiry date in YYYY-MM-DD format, or /skip to discard this entry.'
            _, name, opened, *_ = self.state()
            layer, = self.db.execute('SELECT layer FROM conversation WHERE id=1').fetchone()
            cursor = self.db.execute('INSERT INTO foods(name,expiry,stored,layer) VALUES (?,?,?,?)',
                                     (name, text, opened, layer))
            self.finish_entry()
            self.db.execute('UPDATE conversation SET numbering_ready=1 WHERE id=1')
            number = self.visible_number(cursor.lastrowid)
            return 'Saved #' + str(number) + ': ' + name + (f', Layer {layer}' if layer else '') + ', expiry ' + text + '.\nThe expiry reminder is due two days before this date. Use /list for the current numbered list, /edit NUMBER to edit, or /test_expiry to test a reminder.'
        if text in ('/open', '/add'):
            self.start(now)
            return None
        if text == '/skip':
            return 'There is no pending food entry to skip.'
        parts = text.split(maxsplit=1)
        command = parts[0] if parts else ''
        if command == '/list':
            return self.list_food(text)
        if command in ('/view', '/remove', '/delete', '/edit', '/rename', '/expiry'):
            if not self.db.execute('SELECT numbering_ready FROM conversation WHERE id=1').fetchone()[0]:
                return 'The list now uses consecutive item numbers. Send /list before viewing, editing or deleting an item.'
        if command in ('/view', '/remove', '/delete'):
            number = item_number(parts[1]) if len(parts) == 2 else None
            if number is None:
                return 'Use ' + command + ' NUMBER with a number from the current list, for example ' + command + ' 1.'
            item_id = self.resolve_number(number)
            if item_id is None:
                return 'That item number was not found. Use /list for the current numbers.'
            if command == '/view':
                return self.view_food(item_id)
            cursor = self.db.execute('DELETE FROM foods WHERE id=?', (item_id,))
            return 'Removed.' if cursor.rowcount else 'That item ID was not found.'
        if command in ('/edit', '/rename', '/expiry'):
            arguments = parts[1].split(maxsplit=1) if len(parts) == 2 else []
            number = item_number(arguments[0]) if arguments else None
            if number is None:
                return 'Use /edit NUMBER, /edit NUMBER name NEW NAME, or /edit NUMBER expiry YYYY-MM-DD. Find numbers with /list.'
            item_id = self.resolve_number(number)
            if item_id is None:
                return 'That item number was not found. Use /list for the current numbers.'
            field, value = None, None
            if command in ('/rename', '/expiry'):
                field = 'name' if command == '/rename' else 'expiry'
                value = arguments[1] if len(arguments) == 2 else None
            elif len(arguments) == 2:
                values = arguments[1].split(maxsplit=1)
                field = values[0].lower()
                if field not in ('name', 'expiry'):
                    return 'Choose name or expiry, for example /edit ' + str(number) + ' expiry 2026-12-01.'
                value = values[1] if len(values) == 2 else None
            if value is not None:
                return self.edit_value(item_id, field, value)
            edit_stage = 'edit_' + field if field else 'edit_field'
            self.db.execute('UPDATE conversation SET stage=?,editing_id=?,prompt=0 WHERE id=1', (edit_stage, item_id))
            return None
        if text == '/test_expiry':
            row = self.db.execute('SELECT id FROM foods ORDER BY id DESC LIMIT 1').fetchone()
            if not row:
                return 'Record a test food first with /open.'
            self.db.execute('UPDATE foods SET test_pending=1 WHERE id=?', (row[0],))
            return 'Preparing a test expiry reminder for the newest item.'
        return ('VIK bot ready.\n/open or /add - add a food\n/list - earliest expiry first\n/list added - oldest added first\n/list name - sort by name\n/view NUMBER - show one food\n/edit NUMBER - edit name or expiry step by step\n/rename NUMBER NEW NAME - rename directly\n/expiry NUMBER YYYY-MM-DD - change expiry directly\n/delete NUMBER or /remove NUMBER - delete one food\n/skip - discard the current new entry\n/alarm - start the demo buzzer countdown with the Uno connected\n/test_expiry - simulate the two-day expiry reminder\n\nExample: /rename 1 Fresh milk\nList numbers run 1, 2, 3 with no gaps and follow the latest list order. Check /list after adding, editing, deleting or sorting. /cancel leaves an edit without changes.\nKeep this Mac and Terminal running.')

    def due(self, now):
        today = dt.datetime.fromtimestamp(now, HONG_KONG).date()
        target_expiry = (today + dt.timedelta(days=2)).isoformat()
        return self.db.execute(
            'SELECT id,name,expiry,test_pending FROM foods '
            'WHERE test_pending=1 OR (expiry=? AND expiry_notified IS NOT expiry) ORDER BY id LIMIT 1',
            (target_expiry,)).fetchone()

    def send_due_reminder(self, now, send):
        row = self.due(now)
        if not row:
            return
        item_id, name, expiry, test = row
        send(f'Expiry reminder: {name} expires in 2 days ({expiry}).')
        with self.db:
            if test:
                self.db.execute('UPDATE foods SET test_pending=0 WHERE id=?', (item_id,))
            else:
                self.db.execute('UPDATE foods SET expiry_notified=? WHERE id=?', (expiry, item_id))


def run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=Path.home()/'.config/int4089/fridge_mac_test')
    parser.add_argument('--check', action='store_true', help='Check Telegram connection without sending messages or saving data')
    parser.add_argument('--door', action='store_true', help='Read the physical fridge switch over Uno USB')
    parser.add_argument('--door-port', help='Select the Uno serial device for physical door mode')
    args = parser.parse_args()
    token, chat = credentials()
    api = Telegram(token, chat)
    identity = api.call('getMe')
    if api.call('getWebhookInfo').get('url'):
        raise SetupError('This bot has an active webhook. No settings were changed; use a separate test bot or remove its webhook deliberately first.')
    chat_info = api.call('getChat', chat_id=chat)
    if chat_info.get('type') != 'private':
        raise SetupError('Use the existing private bot chat, not a group or channel.')
    print('Bot: https://t.me/' + identity['username'], flush=True)
    if args.check:
        print('Connection and private chat verified. No messages sent.', flush=True)
        return
    args.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(args.data_dir, 0o700)
    # Prevent a second local test from competing for this bot's updates.
    import fcntl
    lock = (args.data_dir/'runner.lock').open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SetupError('This Mac test is already running. Use its existing Terminal window.') from None
    fridge = Fridge(args.data_dir/'test_food.sqlite3')
    if not fridge.state()[5]:
        # On first-ever test startup, ignore old bot messages, then persist the
        # cursor before publishing a new prompt. Do not reset it on normal restart.
        previous = api.call('getUpdates', offset=-1, limit=1, timeout=0, allowed_updates=['message'])
        offset = int(previous[-1]['update_id'])+1 if previous else 0
        with fridge.db:
            fridge.db.execute('UPDATE conversation SET offset=?,initialised=1 WHERE id=1', (offset,))
    door = None
    if args.door or args.door_port:
        from fridge_door import BotDoorMonitor
        from sensor_alerts import SensorAlerts, claim_temperature_alerts
        from status_data import publish
        door = BotDoorMonitor(args.door_port, lambda opened: publish('door', opened=opened))
        temperature_alerts = SensorAlerts(api.send, send_error=TelegramError)

    api.send(WELCOME)
    print('Running. In Telegram send /open. Keep this Terminal open; press Ctrl+C to stop.', flush=True)
    if door is not None:
        print('Uno door: waiting for switch events.', flush=True)
    next_reminder = 0
    next_temperature_check = 0
    retry_prompt = 0
    repeat_entry_prompt = False
    while True:
        try:
            if door is not None:
                if door.take_opening():
                    with fridge.db:
                        fridge.start(time.time())
                    repeat_entry_prompt = fridge.state()[0] in ENTRY_STAGES
                    if repeat_entry_prompt:
                        retry_prompt = 0
                try:
                    door.warn(api.send)
                except TelegramError as error:
                    print(f'{error} Door warning will retry if the door is still open.', flush=True)
                try:
                    door.report_alarm(api.send)
                except TelegramError as error:
                    print(f'{error} The alarm status message will retry.', flush=True)
                if time.monotonic() >= next_temperature_check:
                    next_temperature_check = time.monotonic() + 1
                    try:
                        alert_lock = claim_temperature_alerts()
                    except OSError:
                        print('Could not open the temperature alert lock. Will retry in 10 seconds.', flush=True)
                        next_temperature_check = time.monotonic() + 10
                    else:
                        if alert_lock is not None:
                            with alert_lock:
                                temperature_alerts.process_latest()
            stage, _, _, prompt, offset, _ = fridge.state()
            if stage not in ENTRY_STAGES:
                repeat_entry_prompt = False
            if stage != 'idle' and (not prompt or repeat_entry_prompt) and time.monotonic() >= retry_prompt:
                retry_prompt = time.monotonic()+10
                prompt_id = api.send(fridge.question(), question=True, layer_choices=(stage == 'layer'))
                if not prompt:
                    # Keep accepting replies sent after the original question when we resend it.
                    with fridge.db:
                        fridge.db.execute('UPDATE conversation SET prompt=? WHERE id=1', (prompt_id,))
                repeat_entry_prompt = False
            updates = api.call('getUpdates', offset=offset, limit=1, timeout=1 if door is not None else 5, allowed_updates=['message'])
            for update in updates:
                message = update.get('message', {})
                target = message.get('chat', {})
                response = None
                with fridge.db:
                    if str(target.get('id')) == str(chat) and target.get('type') == 'private':
                        text = message.get('text', '')
                        if text.strip() == '/alarm':
                            response = (door.start_alarm() if door is not None else
                                        'Use the dashboard to start the bot with the Arduino Uno before using /alarm.')
                        else:
                            response = fridge.handle(text, int(message.get('message_id', 0)), time.time())
                    fridge.db.execute('UPDATE conversation SET offset=? WHERE id=1', (int(update['update_id'])+1,))
                if response:
                    api.send(response)
                # A stage advance should ask the next question immediately.
                if fridge.state()[0] != 'idle' and not fridge.state()[3]:
                    retry_prompt = 0
            if time.monotonic() >= next_reminder:
                next_reminder = time.monotonic()+10
                fridge.send_due_reminder(time.time(), api.send)
        except TelegramError as error:
            print(str(error) + ' Retrying in 10 seconds.', flush=True)
            time.sleep(10)


if __name__ == '__main__':
    try:
        run()
    except KeyboardInterrupt:
        print('\nStopped. Test records are saved for next time.')
    except (SetupError, TelegramError) as error:
        print('Cannot start: ' + str(error), file=sys.stderr)
        sys.exit(1)
    except (OSError, sqlite3.Error):
        print('Cannot start or save test data. Check the local folder permissions and available storage.', file=sys.stderr)
        sys.exit(1)
