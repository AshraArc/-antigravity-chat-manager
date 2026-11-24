"""
Unit and integration tests for safe native Antigravity session deletion in Ach!.
Uses strictly isolated temporary directories — never touches real user chats.
"""

import json
import os
import shutil
import sqlite3
import stat
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import ach


class TestNativeDeletion(unittest.TestCase):
    def setUp(self):
        self.test_root = tempfile.mkdtemp(prefix="ach_native_del_")
        self.cli_dir = os.path.join(self.test_root, "antigravity-cli")
        self.brain_dir = os.path.join(self.cli_dir, "brain")
        self.conv_dir = os.path.join(self.cli_dir, "conversations")
        self.annot_dir = os.path.join(self.cli_dir, "annotations")
        self.data_dir = os.path.join(self.test_root, "ach_data")
        self.outside_dir = os.path.join(self.test_root, "outside_secret")

        for d in (self.brain_dir, self.conv_dir, self.annot_dir, self.data_dir, self.outside_dir):
            os.makedirs(d, exist_ok=True)

        self.orig_data_dir = ach.DATA_DIR
        self.orig_history_db = ach.HISTORY_DB
        self.orig_lock_file = ach.LOCK_FILE
        self.orig_brain_dir = ach.BRAIN_DIR
        self.orig_get_all_data_dirs = ach.get_all_data_dirs

        ach.DATA_DIR = self.data_dir
        ach.HISTORY_DB = os.path.join(self.data_dir, "history.db")
        ach.LOCK_FILE = os.path.join(self.data_dir, "history.lock")
        ach.BRAIN_DIR = self.brain_dir
        ach.get_all_data_dirs = lambda: [self.data_dir]

        ach.init_db()

    def tearDown(self):
        # Restore permissions in case a test made something read-only
        for root, dirs, files in os.walk(self.test_root):
            for name in dirs:
                try:
                    os.chmod(os.path.join(root, name), 0o755)
                except OSError:
                    pass
            for name in files:
                try:
                    os.chmod(os.path.join(root, name), 0o644)
                except OSError:
                    pass

        ach.DATA_DIR = self.orig_data_dir
        ach.HISTORY_DB = self.orig_history_db
        ach.LOCK_FILE = self.orig_lock_file
        ach.BRAIN_DIR = self.orig_brain_dir
        ach.get_all_data_dirs = self.orig_get_all_data_dirs
        shutil.rmtree(self.test_root, ignore_errors=True)

    def _create_mock_session(self, cid, title="Mock Chat"):
        b_dir = os.path.join(self.brain_dir, cid)
        os.makedirs(b_dir, exist_ok=True)
        with open(os.path.join(b_dir, "transcript.jsonl"), "w", encoding="utf-8") as f:
            f.write('{"role":"user","text":"hello"}\n')

        for ext in (".db", ".db-wal", ".db-shm", ".pb"):
            with open(os.path.join(self.conv_dir, f"{cid}{ext}"), "w", encoding="utf-8") as f:
                f.write("data")

        with open(os.path.join(self.annot_dir, f"{cid}.pbtxt"), "w", encoding="utf-8") as f:
            f.write("annot")

        ach.write_session({
            "id": cid,
            "title": title,
            "mtime": time.time(),
            "msgs": 2,
            "group": "General",
        })

        ws_path = os.path.join(self.data_dir, "workspaces.json")
        ws = {}
        if os.path.exists(ws_path):
            with open(ws_path, "r", encoding="utf-8") as f:
                ws = json.load(f)
        ws[cid] = "/tmp/ws"
        with open(ws_path, "w", encoding="utf-8") as f:
            json.dump(ws, f)

    def test_validate_conversation_id(self):
        self.assertTrue(ach.validate_conversation_id("8ab723ac-06ba-4f22-bd0d-2ceacb011a86"))
        self.assertTrue(ach.validate_conversation_id("target_del-999"))
        for bad in ("", " ", "..", ".", "../escape", "/etc/passwd", "a/b", "a\\b", "*", "abc*", "a?b", "a[0]", "bad id", "abc\n", None, 123):
            self.assertFalse(ach.validate_conversation_id(bad), f"Expected invalid: {bad!r}")

    def test_rejects_path_traversal_and_leaves_outside_files_intact(self):
        secret_file = os.path.join(self.outside_dir, "keep.txt")
        with open(secret_file, "w", encoding="utf-8") as f:
            f.write("important")

        report = ach.purge_chats_from_all_storage(
            ["../outside_secret", "/etc/passwd", "*", ".."],
            agy_cli_dir=self.cli_dir,
            brain_dir=self.brain_dir,
            return_report=True,
        )
        self.assertEqual(report["purged"], [])
        self.assertEqual(len(report["invalid"]), 4)
        self.assertTrue(os.path.exists(secret_file))

    def test_symlink_safety_does_not_follow_outside_targets(self):
        cid = "symlink-test-001"
        outside_target_dir = os.path.join(self.outside_dir, "real_dir")
        os.makedirs(outside_target_dir, exist_ok=True)
        outside_inside_file = os.path.join(outside_target_dir, "precious.txt")
        with open(outside_inside_file, "w", encoding="utf-8") as f:
            f.write("do not delete")

        outside_conv_file = os.path.join(self.outside_dir, "real_conv.db")
        with open(outside_conv_file, "w", encoding="utf-8") as f:
            f.write("do not delete")

        brain_link = os.path.join(self.brain_dir, cid)
        conv_link = os.path.join(self.conv_dir, f"{cid}.db")
        os.symlink(outside_target_dir, brain_link)
        os.symlink(outside_conv_file, conv_link)

        report = ach.purge_chats_from_all_storage(
            [cid],
            agy_cli_dir=self.cli_dir,
            brain_dir=self.brain_dir,
            return_report=True,
        )
        self.assertEqual(report["purged"], [cid])
        self.assertEqual(report["warnings"], [])
        # Symlinks themselves are removed
        self.assertFalse(os.path.lexists(brain_link))
        self.assertFalse(os.path.lexists(conv_link))
        # Outside targets remain completely untouched
        self.assertTrue(os.path.exists(outside_inside_file))
        self.assertTrue(os.path.exists(outside_conv_file))

    def test_idempotent_deletion_of_missing_session(self):
        cid = "already-gone-404"
        report = ach.purge_chats_from_all_storage(
            [cid],
            agy_cli_dir=self.cli_dir,
            brain_dir=self.brain_dir,
            return_report=True,
        )
        self.assertEqual(report["purged"], [cid])
        self.assertEqual(report["warnings"], [])

    def test_removes_all_conversation_extensions_and_summaries(self):
        cid_del = "session-del-001"
        cid_keep = "session-keep-002"
        self._create_mock_session(cid_del, "Delete Target")
        self._create_mock_session(cid_keep, "Keep Target")

        sum_db = os.path.join(self.cli_dir, "conversation_summaries.db")
        conn = sqlite3.connect(sum_db)
        conn.execute("CREATE TABLE conversation_summaries (conversation_id TEXT PRIMARY KEY, title TEXT);")
        conn.execute("CREATE VIRTUAL TABLE conversations_fts USING fts5(conversation_id UNINDEXED, title);")
        conn.execute("CREATE TABLE conversation_parents (conversation_id TEXT PRIMARY KEY, parent_id TEXT);")
        conn.execute("INSERT INTO conversation_summaries VALUES (?, 'Del'), (?, 'Keep');", (cid_del, cid_keep))
        conn.execute("INSERT INTO conversations_fts VALUES (?, 'Del'), (?, 'Keep');", (cid_del, cid_keep))
        conn.execute("INSERT INTO conversation_parents VALUES (?, 'p0');", (cid_del,))
        conn.commit()
        conn.close()

        report = ach.purge_chats_from_all_storage(
            [cid_del],
            agy_cli_dir=self.cli_dir,
            brain_dir=self.brain_dir,
            return_report=True,
        )
        self.assertEqual(report["purged"], [cid_del])
        self.assertEqual(report["warnings"], [])

        self.assertFalse(os.path.exists(os.path.join(self.brain_dir, cid_del)))
        self.assertTrue(os.path.exists(os.path.join(self.brain_dir, cid_keep)))
        for ext in (".db", ".db-wal", ".db-shm", ".pb"):
            self.assertFalse(os.path.exists(os.path.join(self.conv_dir, f"{cid_del}{ext}")))
            self.assertTrue(os.path.exists(os.path.join(self.conv_dir, f"{cid_keep}{ext}")))
        self.assertFalse(os.path.exists(os.path.join(self.annot_dir, f"{cid_del}.pbtxt")))
        self.assertTrue(os.path.exists(os.path.join(self.annot_dir, f"{cid_keep}.pbtxt")))

        with open(os.path.join(self.data_dir, "workspaces.json"), "r", encoding="utf-8") as f:
            ws = json.load(f)
        self.assertNotIn(cid_del, ws)
        self.assertIn(cid_keep, ws)

        self.assertEqual([r["id"] for r in ach.read_sessions()], [cid_keep])
        self.assertEqual(len(ach.search_sessions_fts("Delete")), 0)

    def test_active_session_protection_and_force_override(self):
        cid = "active-session-777"
        self._create_mock_session(cid, "Current Active Chat")

        orig_env = os.environ.get("AGY_CONVERSATION_ID")
        try:
            os.environ["AGY_CONVERSATION_ID"] = cid
            report = ach.purge_chats_from_all_storage(
                [cid],
                agy_cli_dir=self.cli_dir,
                brain_dir=self.brain_dir,
                return_report=True,
            )
            self.assertEqual(report["purged"], [])
            self.assertEqual(report["skipped"], [cid])
            self.assertTrue(os.path.exists(os.path.join(self.brain_dir, cid)))

            # Force override should delete it
            report_force = ach.purge_chats_from_all_storage(
                [cid],
                agy_cli_dir=self.cli_dir,
                brain_dir=self.brain_dir,
                force=True,
                return_report=True,
            )
            self.assertEqual(report_force["purged"], [cid])
            self.assertFalse(os.path.exists(os.path.join(self.brain_dir, cid)))
        finally:
            if orig_env is not None:
                os.environ["AGY_CONVERSATION_ID"] = orig_env
            else:
                os.environ.pop("AGY_CONVERSATION_ID", None)

    def test_permission_error_reported_as_warning_without_crashing(self):
        if os.geteuid() == 0:
            self.skipTest("Running as root; chmod read-only does not block deletion")
        cid = "perm-err-001"
        self._create_mock_session(cid, "Locked Chat")
        locked_brain = os.path.join(self.brain_dir, cid)
        os.chmod(locked_brain, stat.S_IRUSR | stat.S_IXUSR)

        report = ach.purge_chats_from_all_storage(
            [cid],
            agy_cli_dir=self.cli_dir,
            brain_dir=self.brain_dir,
            return_report=True,
        )
        self.assertEqual(report["purged"], [cid])
        self.assertTrue(len(report["warnings"]) > 0)
        # Other layers (like history.db) were still cleaned up
        self.assertEqual(ach.read_sessions(), [])


if __name__ == "__main__":
    unittest.main()
