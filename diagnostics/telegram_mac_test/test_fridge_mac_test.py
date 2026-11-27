import datetime as dt
import tempfile
import sqlite3
from pathlib import Path
import unittest
from fridge_mac_test import Fridge, HONG_KONG


class FridgeTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name)/'test.sqlite3'
        self.fridge = Fridge(self.path)
        self.now = 1800000000

    def tearDown(self):
        self.fridge.db.close()
        self.folder.cleanup()

    def prompt(self, message_id):
        self.fridge.db.execute('UPDATE conversation SET prompt=?', (message_id,))
        self.fridge.db.commit()

    def enter(self, name='Milk', expiry='2026-12-01', when=None):
        when = self.now if when is None else when
        self.fridge.handle('/open', 1, when)
        self.prompt(10)
        self.fridge.handle(name, 11, when)
        self.prompt(12)
        self.fridge.handle('Layer 2', 13, when)
        self.prompt(14)
        self.fridge.handle(expiry, 15, when)
        self.fridge.db.commit()

    def test_mandatory_answers_and_stale_messages(self):
        self.fridge.handle('/open', 1, self.now)
        self.assertIsNone(self.fridge.handle('Old message', 2, self.now))
        self.prompt(10)
        self.assertIsNone(self.fridge.handle('Old message', 9, self.now))
        for command in ('/list', '/open', '/test_expiry', '/cancel'):
            self.assertIn('food name', self.fridge.handle(command, 11, self.now))
        self.fridge.handle('Milk', 12, self.now)
        self.prompt(13)
        for invalid in ('Layer 0', '4', '2026-12-01', '/open'):
            self.assertIn('Choose Layer 1', self.fridge.handle(invalid, 14, self.now))
        self.assertIsNone(self.fridge.handle('3', 15, self.now))
        self.prompt(16)
        for invalid in ('2026-02-29', '2026-11-31', '2026-1-1', '/list', ''):
            self.assertIn('real expiry date', self.fridge.handle(invalid, 17, self.now))
        self.assertEqual(self.fridge.state()[0], 'expiry')
        self.assertIn('Layer 3', self.fridge.handle('2028-02-29', 18, self.now))
        self.assertEqual(self.fridge.state()[0], 'idle')

    def test_start_shows_vik_welcome_and_preserves_pending_entry(self):
        self.fridge.start(self.now)
        self.assertEqual(self.fridge.handle('/start', 10, self.now),
                         'Welcome to VIK, Vision Intervention Kit.\n\nFor the full list of command, /help')
        self.assertEqual(self.fridge.question(),
                         'What food are you putting in the fridge? Send the food name or /skip to skip this entry.')

    def test_skip_discards_only_the_pending_entry(self):
        self.enter('Milk')
        self.assertTrue(self.fridge.start(self.now))
        self.prompt(20)
        self.assertIsNone(self.fridge.handle('/skip', 19, self.now))
        self.assertIn('skipped', self.fridge.handle('/skip', 21, self.now))
        self.assertTrue(self.fridge.start(self.now))
        self.prompt(22)
        self.fridge.handle('Eggs', 23, self.now)
        self.prompt(24)
        self.assertIn('skipped', self.fridge.handle('/skip', 25, self.now))
        self.assertEqual(self.fridge.state()[:4], ('idle', '', 0.0, 0))
        self.assertEqual(self.fridge.db.execute('SELECT name FROM foods').fetchall(), [('Milk',)])
        self.assertIn('Milk', self.fridge.handle('/list', 26, self.now))
        self.assertTrue(self.fridge.start(self.now))

    def test_real_restart_reopens_sqlite_pending_and_saved_food(self):
        self.fridge.handle('/open', 1, self.now)
        self.prompt(10)
        self.fridge.handle('Milk', 11, self.now)
        self.fridge.db.commit()
        self.fridge.db.close()
        self.fridge = Fridge(self.path)
        self.assertEqual(self.fridge.state()[:2], ('layer', 'Milk'))
        self.prompt(12)
        self.fridge.handle('Layer 1', 13, self.now)
        self.fridge.db.commit()
        self.fridge.db.close()
        self.fridge = Fridge(self.path)
        self.prompt(14)
        self.fridge.handle('2026-12-01', 15, self.now)
        self.fridge.db.commit()
        self.fridge.db.close()
        self.fridge = Fridge(self.path)
        self.assertIn('Milk | Layer 1', self.fridge.handle('/list', 16, self.now))
        self.assertIn('Layer 1', self.fridge.handle('/view 1', 17, self.now))

    def test_expiry_reminder_is_due_only_two_hong_kong_calendar_days_before(self):
        due_at = dt.datetime(2026, 11, 29, tzinfo=HONG_KONG).timestamp()
        next_day = dt.datetime(2026, 11, 30, tzinfo=HONG_KONG).timestamp()
        self.enter('Milk', '2026-12-01', due_at - 60)
        self.enter('Rice', '2026-12-03', due_at - 60)
        self.assertIsNone(self.fridge.due(due_at - 1))
        self.assertEqual(self.fridge.due(due_at), (1, 'Milk', '2026-12-01', 0))
        self.assertEqual(self.fridge.due(next_day - 1), (1, 'Milk', '2026-12-01', 0))
        self.assertIsNone(self.fridge.due(next_day))
        sent = []
        self.fridge.send_due_reminder(due_at, sent.append)
        self.fridge.send_due_reminder(due_at, sent.append)
        self.assertEqual(sent, ['Expiry reminder: Milk expires in 2 days (2026-12-01).'])
        self.assertIn('Expiry reminder: already sent', self.fridge.handle('/view 1', 20, due_at))
        self.fridge.handle('/expiry 1 2026-12-02', 21, due_at)
        self.assertEqual(self.fridge.due(next_day), (1, 'Milk', '2026-12-02', 0))

    def test_test_expiry_previews_newest_food_without_consuming_real_reminder(self):
        due_at = dt.datetime(2026, 11, 29, tzinfo=HONG_KONG).timestamp()
        stored = due_at - 60
        self.enter('Rice', '2026-12-03', stored)
        self.enter('Milk', '2026-12-01', stored)
        help_text = self.fridge.handle('/help', 19, stored)
        self.assertIn('/test_expiry', help_text)
        self.assertNotIn('/test_week', help_text)
        self.fridge.handle('/test_week', 20, stored)
        self.assertIsNone(self.fridge.due(stored))
        self.fridge.handle('/test_expiry', 21, stored)
        self.assertEqual(self.fridge.due(stored), (2, 'Milk', '2026-12-01', 1))
        sent = []
        self.fridge.send_due_reminder(stored, sent.append)
        self.assertEqual(sent, ['Expiry reminder: Milk expires in 2 days (2026-12-01).'])
        self.assertEqual(self.fridge.db.execute('SELECT expiry,stored FROM foods WHERE id=2').fetchone(), ('2026-12-01', stored))
        self.assertIsNone(self.fridge.due(stored))
        self.assertEqual(self.fridge.due(due_at), (2, 'Milk', '2026-12-01', 0))

    def test_direct_edits_reorder_without_resetting_timer_or_reminder(self):
        self.enter('Milk', '2026-12-05')
        self.enter('Rice', '2026-12-03', self.now+100)
        result = self.fridge.handle('/list', 20, self.now)
        self.assertIn('#1: Rice', result)
        self.assertIn('#2: Milk', result)
        self.fridge.db.execute('UPDATE foods SET notified=1 WHERE id=1')
        self.assertIn('Updated #2', self.fridge.handle('/rename 2 Fresh milk', 21, self.now))
        self.assertIn('now #1', self.fridge.handle('/expiry 2 2026-12-01', 22, self.now))
        result = self.fridge.handle('/list', 23, self.now)
        self.assertIn('#1: Fresh milk', result)
        self.assertIn('#2: Rice', result)
        self.assertEqual(self.fridge.db.execute('SELECT stored,notified FROM foods WHERE id=1').fetchone(), (self.now, 1))
        self.assertIn('Updated #2', self.fridge.handle('/edit 2 name Brown rice', 24, self.now))
        self.assertIn('Updated #2', self.fridge.handle('/edit 2 expiry 2026-12-02', 25, self.now))
        before = self.fridge.db.execute('SELECT * FROM foods').fetchall()
        for command in ('/expiry 2 2026-02-29', '/rename 2 '+('界'*22), '/edit 2 unknown 123',
                        '/rename 2 bad\nname', '/edit 999 name Food', '/delete 9223372036854775808'):
            self.fridge.handle(command, 26, self.now)
        self.assertEqual(before, self.fridge.db.execute('SELECT * FROM foods').fetchall())

    def test_interactive_edit_resumes_after_restart_and_can_cancel(self):
        self.enter()
        self.assertIsNone(self.fridge.handle('/edit 1', 20, self.now))
        self.assertIn('Reply name or expiry', self.fridge.question())
        self.prompt(21)
        self.assertIsNone(self.fridge.handle('expiry', 22, self.now))
        self.fridge.db.commit()
        self.fridge.db.close()
        self.fridge = Fridge(self.path)
        self.assertEqual(self.fridge.state()[0], 'edit_expiry')
        self.assertEqual(self.fridge.editing_id(), 1)
        self.assertIn('#1', self.fridge.question())
        self.assertIsNone(self.fridge.handle('2026-12-02', 23, self.now))
        self.prompt(24)
        self.assertIn('real expiry date', self.fridge.handle('2026-13-01', 25, self.now))
        self.assertIn('Updated #1', self.fridge.handle('2026-12-02', 26, self.now))
        self.assertEqual(self.fridge.state()[0], 'idle')
        self.fridge.handle('/rename 1', 27, self.now)
        self.prompt(28)
        self.assertIn('cancelled', self.fridge.handle('/cancel', 29, self.now))
        self.assertEqual(self.fridge.db.execute('SELECT name,expiry FROM foods').fetchone(), ('Milk','2026-12-02'))

    def test_delete_keeps_internal_ids_but_display_numbers_have_no_gaps(self):
        self.enter('Milk')
        self.enter('Rice')
        self.assertEqual(self.fridge.handle('/delete 1', 20, self.now), 'Removed.')
        self.enter('Eggs')
        rows = self.fridge.db.execute('SELECT id,name FROM foods ORDER BY id').fetchall()
        self.assertEqual(rows, [(2, 'Rice'), (3, 'Eggs')])
        self.assertIn('#2: Eggs', self.fridge.handle('/view 2', 21, self.now))
        self.assertIn('Hong Kong time', self.fridge.handle('/view 2', 22, self.now))
        self.assertIn('#1: Rice', self.fridge.handle('/view 1', 23, self.now))
        self.assertIn('not found', self.fridge.handle('/view 3', 24, self.now))

    def test_sort_modes_ties_and_pagination(self):
        self.enter('Zucchini', '2026-12-03', self.now+100)
        self.enter('Apple', '2026-12-03', self.now)
        result = self.fridge.handle('/list', 20, self.now)
        self.assertIn('#1: Apple', result)
        self.assertIn('#2: Zucchini', result)
        for mode in ('added', 'name'):
            result = self.fridge.handle('/list '+mode, 21, self.now)
            self.assertIn('#1: Apple', result)
            self.assertIn('#2: Zucchini', result)
        for i in range(20):
            self.enter('Item '+str(i), '2026-12-04')
        page = self.fridge.handle('/list 2', 22, self.now)
        self.assertIn('page 2/3', page)
        self.assertEqual(sum(line.startswith('#') for line in page.splitlines()), 10)
        self.assertTrue(next(line for line in page.splitlines() if line.startswith('#')).startswith('#11:'))
        self.assertIn('Next page: /list name 3', page)
        self.assertLess(len(page), 4096)
        self.assertIn('Page not found', self.fridge.handle('/list 99999', 23, self.now))
        self.assertIn('Use /list', self.fridge.handle('/list expiry nope', 24, self.now))

    def test_old_database_migration_keeps_saved_and_pending_data(self):
        self.fridge.db.close()
        legacy_path = Path(self.folder.name)/'old.sqlite3'
        with sqlite3.connect(legacy_path) as legacy:
            legacy.execute('CREATE TABLE conversation (id INTEGER PRIMARY KEY,stage TEXT,name TEXT,opened REAL,prompt INTEGER,offset INTEGER,initialised INTEGER)')
            legacy.execute("INSERT INTO conversation VALUES(1,'expiry','Cheese',1800000000,42,99,1)")
            legacy.execute('CREATE TABLE foods (id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,expiry TEXT NOT NULL,stored REAL NOT NULL,notified INTEGER NOT NULL DEFAULT 0,test_pending INTEGER NOT NULL DEFAULT 0)')
            legacy.execute("INSERT INTO foods VALUES(7,'Milk','2026-12-01',1800000000,1,0)")
        self.fridge = Fridge(legacy_path)
        self.assertEqual(self.fridge.state(), ('expiry','Cheese',1800000000,42,99,1))
        self.assertEqual(self.fridge.editing_id(), 0)
        self.assertEqual(self.fridge.db.execute('SELECT * FROM foods').fetchone(), (7,'Milk','2026-12-01',1800000000,1,0,None,None))
        due_at = dt.datetime(2026, 11, 29, tzinfo=HONG_KONG).timestamp()
        self.assertEqual(self.fridge.due(due_at), (7, 'Milk', '2026-12-01', 0))
        self.assertIn('Saved #2', self.fridge.handle('2026-12-02', 43, self.now))
        self.fridge.db.commit()
        self.fridge.db.close()
        self.fridge = Fridge(legacy_path)
        self.assertIn('#2: Cheese', self.fridge.handle('/list', 44, self.now))
        self.assertEqual(self.fridge.db.execute('SELECT id FROM foods ORDER BY id').fetchall(), [(7,), (8,)])

    def test_delete_only_item_then_insert_again_shows_one(self):
        self.enter('Milk')
        self.assertEqual(self.fridge.handle('/delete 1', 20, self.now), 'Removed.')
        self.assertIn('No test food', self.fridge.handle('/list', 21, self.now))
        self.enter('Rice')
        self.assertEqual(self.fridge.db.execute('SELECT id FROM foods').fetchone()[0], 2)
        self.assertIn('#1: Rice', self.fridge.handle('/list', 22, self.now))
        self.assertNotIn('#2:', self.fridge.handle('/list', 23, self.now))
        self.assertIn('Updated #1', self.fridge.handle('/rename 1 Brown rice', 24, self.now))
        self.assertEqual(self.fridge.db.execute('SELECT name FROM foods WHERE id=2').fetchone()[0], 'Brown rice')
        self.assertEqual(self.fridge.handle('/delete 1', 25, self.now), 'Removed.')
        self.assertEqual(self.fridge.db.execute('SELECT COUNT(*) FROM foods').fetchone()[0], 0)

    def test_commands_follow_selected_sort_and_keep_mapping_on_restart(self):
        self.enter('Zucchini', '2026-12-01')
        self.enter('Apple', '2026-12-02')
        self.assertIn('#1: Apple', self.fridge.handle('/list name', 20, self.now))
        self.fridge.db.commit()
        self.fridge.db.close()
        self.fridge = Fridge(self.path)
        self.assertIn('#1: Apple', self.fridge.handle('/view 1', 21, self.now))
        self.fridge.handle('/edit 1', 22, self.now)
        self.assertEqual(self.fridge.editing_id(), 2)
        self.prompt(23)
        self.fridge.handle('name', 24, self.now)
        self.prompt(25)
        self.fridge.handle('Pear', 26, self.now)
        self.assertEqual(self.fridge.db.execute('SELECT name FROM foods WHERE id=2').fetchone()[0], 'Pear')
        self.fridge.handle('/delete 2', 27, self.now)
        self.assertIn('#1: Pear', self.fridge.handle('/view 1', 28, self.now))

    def test_upgrade_requires_fresh_list_before_numbered_actions(self):
        self.fridge.db.close()
        legacy_path = Path(self.folder.name)/'old-id-list.sqlite3'
        with sqlite3.connect(legacy_path) as legacy:
            legacy.execute('CREATE TABLE conversation (id INTEGER PRIMARY KEY,stage TEXT,name TEXT,opened REAL,prompt INTEGER,offset INTEGER,initialised INTEGER)')
            legacy.execute("INSERT INTO conversation VALUES(1,'idle','',0,0,99,1)")
            legacy.execute('CREATE TABLE foods (id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,expiry TEXT NOT NULL,stored REAL NOT NULL,notified INTEGER NOT NULL DEFAULT 0,test_pending INTEGER NOT NULL DEFAULT 0)')
            legacy.execute("INSERT INTO foods VALUES(7,'Milk','2026-12-01',1800000000,0,0)")
        self.fridge = Fridge(legacy_path)
        self.assertIn('Send /list', self.fridge.handle('/delete 1', 20, self.now))
        self.assertEqual(self.fridge.db.execute('SELECT COUNT(*) FROM foods').fetchone()[0], 1)
        self.assertIn('#1: Milk', self.fridge.handle('/list', 21, self.now))
        self.assertIn('#1: Milk', self.fridge.handle('/view 1', 22, self.now))
        self.assertEqual(self.fridge.handle('/delete 1', 23, self.now), 'Removed.')


if __name__ == '__main__':
    unittest.main()
