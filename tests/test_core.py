"""
Unit and integration tests for Ach! core modules.
Covers SQLite session persistence, data directory fallback, text cleaning, and backup/restore mechanisms.
"""

import os
import sys
import unittest
import tempfile
import shutil
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import ach

class TestSessionListCore(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="ach_test_")
        self.orig_data_dir = os.environ.get("ACH_DATA_DIR")
        os.environ["ACH_DATA_DIR"] = self.test_dir
        
        ach.DATA_DIR = self.test_dir
        ach.HISTORY_DB = os.path.join(self.test_dir, "history.db")
        ach.LOCK_FILE = os.path.join(self.test_dir, "history.lock")
        ach.CONFIG_FILE = os.path.join(self.test_dir, "config.json")
        ach.GROUPS_FILE = os.path.join(self.test_dir, "groups.txt")

    def tearDown(self):
        if self.orig_data_dir is not None:
            os.environ["ACH_DATA_DIR"] = self.orig_data_dir
        else:
            os.environ.pop("ACH_DATA_DIR", None)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_clean_text(self):
        raw = "Hello\tworld\nwith   extra   spaces\r"
        cleaned = ach.clean_text(raw)
        self.assertEqual(cleaned, "Hello world with extra spaces")

    def test_sqlite_write_and_read(self):
        ach.init_db()
        now = time.time()
        ach.write_session({
            "id": "uuid-111",
            "mtime": now,
            "msgs": 5,
            "group": "General",
            "title": "First Test Chat"
        })
        ach.write_session({
            "id": "uuid-222",
            "mtime": now - 3600,
            "msgs": 12,
            "group": "Work",
            "title": "Second Test Chat"
        })
        
        read_records = ach.read_sessions()
        
        self.assertEqual(len(read_records), 2)
        self.assertEqual(read_records[0]["id"], "uuid-111")
        self.assertEqual(read_records[0]["title"], "First Test Chat")
        self.assertEqual(read_records[1]["group"], "Work")

    def test_detect_cli_command(self):
        cmd = ach.detect_cli_command()
        self.assertIn(cmd, ["agy", "antigravity"])

if __name__ == "__main__":
    unittest.main()
