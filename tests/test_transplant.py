"""
Integration tests for session moving and transplanting across workspaces.
Verifies:
1. Single chat move: updates workspaces.json, history.db, and mock conversation_summaries.db.
2. Group move (-g): creates multiple chats in a group, transplants them all, verifies all workspaces updated.
3. CLI command parsing: ach mv <id|num> [target], ach mv -g <group> [target], validation and error cases.
"""

import os
import sys
import json
import sqlite3
import shutil
import tempfile
import unittest
import subprocess
from datetime import datetime

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import sessionlist

class TestSessionTransplant(unittest.TestCase):
    def setUp(self):
        self.test_root = tempfile.mkdtemp(prefix="sl_transplant_test_")
        self.data_dir = os.path.join(self.test_root, "data")
        self.brain_dir = os.path.join(self.test_root, "brain")
        self.target_ws1 = os.path.join(self.test_root, "workspace_1")
        self.target_ws2 = os.path.join(self.test_root, "workspace_2")
        self.agy_db_path = os.path.join(self.test_root, "mock_conversation_summaries.db")

        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.brain_dir, exist_ok=True)
        os.makedirs(self.target_ws1, exist_ok=True)
        os.makedirs(self.target_ws2, exist_ok=True)

        self.orig_data_dir = sessionlist.DATA_DIR
        self.orig_brain_dir = sessionlist.BRAIN_DIR
        self.orig_history_db = sessionlist.HISTORY_DB
        self.orig_master_tsv = sessionlist.MASTER_TSV
        self.orig_lock_file = sessionlist.LOCK_FILE
        self.orig_workspaces_file = sessionlist.WORKSPACES_FILE
        self.orig_agy_env = os.environ.get("AGY_SUMMARIES_DB")

        sessionlist.DATA_DIR = self.data_dir
        sessionlist.BRAIN_DIR = self.brain_dir
        sessionlist.HISTORY_DB = os.path.join(self.data_dir, "history.db")
        sessionlist.MASTER_TSV = os.path.join(self.data_dir, "master_history.tsv")
        sessionlist.LOCK_FILE = os.path.join(self.data_dir, "history.lock")
        sessionlist.WORKSPACES_FILE = os.path.join(self.data_dir, "workspaces.json")
        os.environ["AGY_SUMMARIES_DB"] = self.agy_db_path

        sessionlist.init_db()
        self._init_mock_agy_db(self.agy_db_path)

    def tearDown(self):
        sessionlist.DATA_DIR = self.orig_data_dir
        sessionlist.BRAIN_DIR = self.orig_brain_dir
        sessionlist.HISTORY_DB = self.orig_history_db
        sessionlist.MASTER_TSV = self.orig_master_tsv
        sessionlist.LOCK_FILE = self.orig_lock_file
        sessionlist.WORKSPACES_FILE = self.orig_workspaces_file
        if self.orig_agy_env is not None:
            os.environ["AGY_SUMMARIES_DB"] = self.orig_agy_env
        else:
            os.environ.pop("AGY_SUMMARIES_DB", None)
        shutil.rmtree(self.test_root, ignore_errors=True)

    def _init_mock_agy_db(self, path):
        conn = sqlite3.connect(path)
        with conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS conversation_summaries (
                    conversation_id TEXT PRIMARY KEY,
                    workspace_uris TEXT,
                    title TEXT
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS conversations_fts (
                    conversation_id TEXT,
                    workspace TEXT,
                    title TEXT
                );
            """)
        conn.close()

    def _insert_session(self, cid, title, group, ws, mtime=1700000000.0, step_count=5):
        dt = datetime.fromtimestamp(mtime)
        conn = sessionlist.get_db_connection()
        with conn:
            conn.execute("""
                INSERT OR REPLACE INTO sessions 
                (conversation_id, timestamp, relative_time, title, group_name, workspace, step_count, last_modified_time)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """, (cid, dt.isoformat(), "Just now", title, group, ws, step_count, mtime))
            sessionlist.update_fts_entry(conn, cid, title, group, ws, "")
        conn.close()

    def test_single_chat_move(self):
        cid = "cid-single-001"
        initial_ws = "/old/workspace/path"
        
        self._insert_session(cid, "Single Move Test Chat", "Development", initial_ws)
        sessionlist.save_workspace(cid, initial_ws)

        # Populate mock AGY db
        conn_agy = sqlite3.connect(self.agy_db_path)
        with conn_agy:
            conn_agy.execute("""
                INSERT INTO conversation_summaries (conversation_id, workspace_uris, title)
                VALUES (?, ?, ?);
            """, (cid, json.dumps(["file://" + initial_ws]), "Single Move Test Chat"))
            conn_agy.execute("""
                INSERT INTO conversations_fts (conversation_id, workspace, title)
                VALUES (?, ?, ?);
            """, (cid, initial_ws, "Single Move Test Chat"))
        conn_agy.close()

        # Execute transplant_conversations
        count, moved_ws = sessionlist.transplant_conversations([cid], self.target_ws1, target_db_path=self.agy_db_path)
        self.assertEqual(count, 1)
        self.assertEqual(moved_ws, os.path.abspath(self.target_ws1))

        # 1. Verify workspaces.json
        ws_map = sessionlist.load_workspaces()
        self.assertEqual(ws_map.get(cid), os.path.abspath(self.target_ws1))

        # 2. Verify history.db
        conn = sessionlist.get_db_connection()
        row = conn.execute("SELECT workspace FROM sessions WHERE conversation_id = ?;", (cid,)).fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row["workspace"], os.path.abspath(self.target_ws1))

        # 3. Verify mock conversation_summaries.db
        conn_agy = sqlite3.connect(self.agy_db_path)
        agy_row = conn_agy.execute("SELECT workspace_uris FROM conversation_summaries WHERE conversation_id = ?;", (cid,)).fetchone()
        fts_row = conn_agy.execute("SELECT workspace FROM conversations_fts WHERE conversation_id = ?;", (cid,)).fetchone()
        conn_agy.close()
        
        self.assertIsNotNone(agy_row)
        self.assertIn("file://" + os.path.abspath(self.target_ws1), agy_row[0])
        self.assertIsNotNone(fts_row)
        self.assertEqual(fts_row[0], os.path.abspath(self.target_ws1))

    def test_group_move(self):
        cids = [f"cid-grp-{i:03d}" for i in range(1, 4)]
        group_name = "Sprint3"
        initial_ws = "/initial/group/path"

        for i, cid in enumerate(cids):
            self._insert_session(cid, f"Chat {cid}", group_name, initial_ws, mtime=1700000000.0 + i)
            sessionlist.save_workspace(cid, initial_ws)

        conn_agy = sqlite3.connect(self.agy_db_path)
        with conn_agy:
            for cid in cids:
                conn_agy.execute("""
                    INSERT INTO conversation_summaries (conversation_id, workspace_uris, title)
                    VALUES (?, ?, ?);
                """, (cid, json.dumps(["file://" + initial_ws]), f"Chat {cid}"))
                conn_agy.execute("""
                    INSERT INTO conversations_fts (conversation_id, workspace, title)
                    VALUES (?, ?, ?);
                """, (cid, initial_ws, f"Chat {cid}"))
        conn_agy.close()

        # Transplant all 3 conversations
        count, moved_ws = sessionlist.transplant_conversations(cids, self.target_ws2, target_db_path=self.agy_db_path)
        self.assertEqual(count, 3)
        self.assertEqual(moved_ws, os.path.abspath(self.target_ws2))

        # Verify all 3 in workspaces.json
        ws_map = sessionlist.load_workspaces()
        for cid in cids:
            self.assertEqual(ws_map.get(cid), os.path.abspath(self.target_ws2))

        # Verify all 3 in history.db
        conn = sessionlist.get_db_connection()
        rows = conn.execute("SELECT conversation_id, workspace FROM sessions WHERE group_name = ?;", (group_name,)).fetchall()
        conn.close()
        self.assertEqual(len(rows), 3)
        for r in rows:
            self.assertEqual(r["workspace"], os.path.abspath(self.target_ws2))

        # Verify all 3 in mock conversation_summaries.db
        conn_agy = sqlite3.connect(self.agy_db_path)
        for cid in cids:
            sum_row = conn_agy.execute("SELECT workspace_uris FROM conversation_summaries WHERE conversation_id = ?;", (cid,)).fetchone()
            fts_row = conn_agy.execute("SELECT workspace FROM conversations_fts WHERE conversation_id = ?;", (cid,)).fetchone()
            self.assertIn("file://" + os.path.abspath(self.target_ws2), sum_row[0])
            self.assertEqual(fts_row[0], os.path.abspath(self.target_ws2))
        conn_agy.close()

    def test_cli_parsing(self):
        script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "sessionlist.py"))
        env = os.environ.copy()
        env["SESSIONLIST_DATA_DIR"] = self.data_dir
        env["AGY_SUMMARIES_DB"] = self.agy_db_path

        # 1. Test CLI help documents mv command
        res = subprocess.run([sys.executable, script_path, "--help"], capture_output=True, text=True, env=env)
        self.assertEqual(res.returncode, 0)
        self.assertIn("mv <id|num> [target_dir]", res.stdout)
        self.assertIn("mv -g, --group", res.stdout)

        # 2. Test CLI usage without arguments
        res = subprocess.run([sys.executable, script_path, "mv"], capture_output=True, text=True, env=env)
        self.assertEqual(res.returncode, 0)
        self.assertIn("Usage:", res.stdout)
        self.assertIn("ach mv <id|num>", res.stdout)

        # 3. Test CLI move with invalid index
        res = subprocess.run([sys.executable, script_path, "mv", "9999", self.target_ws1], capture_output=True, text=True, env=env)
        self.assertEqual(res.returncode, 0)
        self.assertIn("Error:", res.stdout)

        # 4. Test CLI move group with missing group name
        res = subprocess.run([sys.executable, script_path, "mv", "-g"], capture_output=True, text=True, env=env)
        self.assertEqual(res.returncode, 0)
        self.assertIn("Error: Missing group name", res.stdout)

        # 5. Populate a test chat and test actual CLI move by ID/num
        cid = "cid-cli-001"
        self._insert_session(cid, "CLI Test Chat", "General", "/init/ws", mtime=1700000000.0)

        res = subprocess.run([sys.executable, script_path, "mv", "1", self.target_ws1], capture_output=True, text=True, env=env)
        self.assertEqual(res.returncode, 0)
        self.assertIn("Successfully moved", res.stdout)
        self.assertIn(self.target_ws1, res.stdout)

        # 6. Test CLI move by group name
        cid2 = "cid-cli-002"
        self._insert_session(cid2, "CLI Group Chat", "TargetGroup", "/init/ws2", mtime=1700000001.0)

        res = subprocess.run([sys.executable, script_path, "mv", "-g", "TargetGroup", self.target_ws2], capture_output=True, text=True, env=env)
        self.assertEqual(res.returncode, 0)
        self.assertIn("Successfully moved 1 chat(s) in group 'TargetGroup'", res.stdout)
        self.assertIn(self.target_ws2, res.stdout)

if __name__ == "__main__":
    unittest.main()
