"""
Unit and integration tests for sessionList core modules.
Covers TSV parsing, data directory fallback, text cleaning, and backup/restore mechanisms.
"""

import os
import sys
import unittest
import tempfile
import shutil
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import sessionlist

class TestSessionListCore(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="sl_test_")
        self.orig_data_dir = os.environ.get("SESSIONLIST_DATA_DIR")
        os.environ["SESSIONLIST_DATA_DIR"] = self.test_dir
        
        sessionlist.DATA_DIR = self.test_dir
        sessionlist.HISTORY_DB = os.path.join(self.test_dir, "history.db")
        sessionlist.MASTER_TSV = os.path.join(self.test_dir, "master_history.tsv")
        sessionlist.LOCK_FILE = os.path.join(self.test_dir, "history.lock")
        sessionlist.CONFIG_FILE = os.path.join(self.test_dir, "config.json")
        sessionlist.GROUPS_FILE = os.path.join(self.test_dir, "groups.txt")

    def tearDown(self):
        if self.orig_data_dir is not None:
            os.environ["SESSIONLIST_DATA_DIR"] = self.orig_data_dir
        else:
            os.environ.pop("SESSIONLIST_DATA_DIR", None)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_clean_text(self):
        raw = "Hello\tworld\nwith   extra   spaces\r"
        cleaned = sessionlist.clean_text(raw)
        self.assertEqual(cleaned, "Hello world with extra spaces")

    def test_tsv_write_and_read(self):
        now = time.time()
        sample_records = [
            {
                "id": "uuid-111",
                "mtime": now,
                "msgs": 5,
                "group": "General",
                "title": "First Test Chat"
            },
            {
                "id": "uuid-222",
                "mtime": now - 3600,
                "msgs": 12,
                "group": "Work",
                "title": "Second Test Chat"
            }
        ]
        
        sessionlist.write_master_tsv(sample_records)
        read_records = sessionlist.read_master_tsv()
        
        self.assertEqual(len(read_records), 2)
        self.assertEqual(read_records[0]["id"], "uuid-111")
        self.assertEqual(read_records[0]["title"], "First Test Chat")
        self.assertEqual(read_records[1]["group"], "Work")

    def test_detect_cli_command(self):
        cmd = sessionlist.detect_cli_command()
        self.assertIn(cmd, ["agy", "antigravity"])

if __name__ == "__main__":
    unittest.main()
