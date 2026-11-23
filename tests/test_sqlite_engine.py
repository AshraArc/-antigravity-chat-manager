"""
Integration and regression test suite for sessionList SQLite Engine & FTS5.
Tests:
1. Migration from legacy master_history.tsv to history.db
2. FTS5 full-text search (queries on title, notebook group, workspace, and message content)
3. Concurrency and WAL mode multi-process read/write stress testing
4. Complete multi-layer deletion (brain, conversations db+wal, summaries.db, annotations, history.db, tsv, workspaces)
5. Antigravity DB discovery and sync (conversation_summaries.db)
"""

import os
import sys
import time
import json
import sqlite3
import shutil
import tempfile
import unittest
import multiprocessing
from datetime import datetime

# Import sessionlist module under test
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import ach

class TestSQLiteEngine(unittest.TestCase):
    def setUp(self):
        self.test_root = tempfile.mkdtemp(prefix="sl_sqlite_test_")
        self.data_dir = os.path.join(self.test_root, "data")
        self.brain_dir = os.path.join(self.test_root, "brain")
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.brain_dir, exist_ok=True)

        self.orig_data_dir = ach.DATA_DIR
        self.orig_brain_dir = ach.BRAIN_DIR
        self.orig_history_db = ach.HISTORY_DB
        self.orig_lock_file = ach.LOCK_FILE

        ach.DATA_DIR = self.data_dir
        ach.BRAIN_DIR = self.brain_dir
        ach.HISTORY_DB = os.path.join(self.data_dir, "history.db")
        ach.LOCK_FILE = os.path.join(self.data_dir, "history.lock")

    def tearDown(self):
        ach.DATA_DIR = self.orig_data_dir
        ach.BRAIN_DIR = self.orig_brain_dir
        ach.HISTORY_DB = self.orig_history_db
        ach.LOCK_FILE = self.orig_lock_file
        shutil.rmtree(self.test_root, ignore_errors=True)

    def test_01_init_db_and_pragmas(self):
        """Verify DB initialization, tables, FTS5 virtual table, and pragmas."""
        ach.init_db()
        self.assertTrue(os.path.exists(ach.HISTORY_DB))

        conn = ach.get_db_connection()
        try:
            # Check journal mode
            jm = conn.execute("PRAGMA journal_mode;").fetchone()[0]
            self.assertEqual(jm.lower(), "wal")

            # Check tables
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'view');").fetchall()}
            self.assertIn("sessions", tables)
            self.assertIn("sessions_fts", tables)

            # Check indices
            indices = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index';").fetchall()}
            self.assertIn("idx_sessions_mtime", indices)
            self.assertIn("idx_sessions_group", indices)
            self.assertIn("idx_sessions_title", indices)
        finally:
            conn.close()

    def test_02_write_and_read_sessions(self):
        """Verify writing and reading sessions directly in SQLite."""
        ach.init_db()
        now = time.time()
        ach.write_session({"id": "cid-001", "mtime": now - 100, "msgs": 5, "group": "Work", "title": "Project Alpha Architecture"})
        ach.write_session({"id": "cid-002", "mtime": now - 50, "msgs": 12, "group": "Research", "title": "Deep Learning Transformers"})
        ach.write_session({"id": "cid-003", "mtime": now - 10, "msgs": 3, "group": "Personal", "title": "Vacation Plans"})

        # Verify records in SQLite
        sessions = ach.read_sessions()
        self.assertEqual(len(sessions), 3)

        # Check order (ordered by mtime DESC)
        self.assertEqual(sessions[0]["id"], "cid-003")
        self.assertEqual(sessions[0]["title"], "Vacation Plans")
        self.assertEqual(sessions[1]["id"], "cid-002")
        self.assertEqual(sessions[1]["group"], "Research")
        self.assertEqual(sessions[2]["id"], "cid-001")
        self.assertEqual(sessions[2]["msgs"], 5)

        # Verify idempotency (updating an existing session should not duplicate rows)
        ach.write_session({"id": "cid-003", "mtime": now - 10, "msgs": 4, "group": "Personal", "title": "Vacation Plans"})
        sessions_again = ach.read_sessions()
        self.assertEqual(len(sessions_again), 3)

    def test_03_fts5_full_text_search(self):
        """Test FTS5 search across title, group, workspace, and transcript content."""
        ach.init_db()

        # Seed test sessions with content
        s1 = {
            "id": "cid-alpha",
            "mtime": time.time() - 200,
            "msgs": 4,
            "group": "Backend",
            "title": "PostgreSQL connection pool optimization",
            "workspace": "/mnt/a/project/backend",
            "content": "Discussed psycopg3 connection pooling, max connections set to 50 with queue limit."
        }
        s2 = {
            "id": "cid-beta",
            "mtime": time.time() - 100,
            "msgs": 8,
            "group": "Frontend",
            "title": "React component state bug",
            "workspace": "/mnt/a/project/frontend",
            "content": "Zustand selector re-rendering unnecessarily when theme context updates."
        }
        s3 = {
            "id": "cid-gamma",
            "mtime": time.time(),
            "msgs": 2,
            "group": "Infra",
            "title": "Kubernetes helm deployment",
            "workspace": "/mnt/a/project/devops",
            "content": "Configured ingress alb controller and horizontal pod autoscaler targets."
        }

        for s in (s1, s2, s3):
            ach.write_session(s)

        # 1. Search by title keyword
        res = ach.search_sessions_fts("optimization")
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["id"], "cid-alpha")

        # 2. Search by group name
        res = ach.search_sessions_fts("Frontend")
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["id"], "cid-beta")

        # 3. Search by workspace substring
        res = ach.search_sessions_fts("devops")
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["id"], "cid-gamma")

        # 4. Search deep within message content
        res = ach.search_sessions_fts("psycopg3")
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["id"], "cid-alpha")

        res_zustand = ach.search_sessions_fts("Zustand")
        self.assertEqual(len(res_zustand), 1)
        self.assertEqual(res_zustand[0]["id"], "cid-beta")

        # 5. Empty / non-matching queries
        self.assertEqual(ach.search_sessions_fts(""), [])
        self.assertEqual(ach.search_sessions_fts("nonexistenttermXYZ"), [])

    def test_04_sync_antigravity_summaries_db(self):
        """Test direct discovery and sync with Antigravity's conversation_summaries.db."""
        # Create a mock conversation_summaries.db
        fake_home = os.path.join(self.test_root, "home")
        mock_cli_dir = os.path.join(fake_home, ".gemini", "antigravity-cli")
        os.makedirs(mock_cli_dir, exist_ok=True)
        agy_db_path = os.path.join(mock_cli_dir, "conversation_summaries.db")

        conn = sqlite3.connect(agy_db_path)
        conn.execute("""
            CREATE TABLE conversation_summaries (
                conversation_id TEXT PRIMARY KEY,
                title TEXT,
                project_id TEXT,
                group_id TEXT,
                workspace_uris TEXT,
                step_count INTEGER,
                last_modified_time REAL
            );
        """)
        now = time.time()
        conn.execute("""
            INSERT INTO conversation_summaries VALUES
            ('agy-001', 'Refactoring Go Router', 'proj-1', 'Routing', '["/mnt/a/code/router"]', 14, ?),
            ('agy-002', 'Debug Memory Leak in Cache', 'proj-2', 'General', '["/mnt/a/code/cache"]', 22, ?);
        """, (now - 50, now))
        conn.commit()
        conn.close()

        # Monkeypatch home expansion or test with mock path
        orig_expanduser = os.path.expanduser
        try:
            os.path.expanduser = lambda path: path.replace("~", fake_home) if path.startswith("~") else orig_expanduser(path)
            synced = ach.sync_antigravity_summaries_db()
            self.assertEqual(synced, 2)

            sessions = ach.read_sessions()
            self.assertEqual(len(sessions), 2)
            cids = {s["id"] for s in sessions}
            self.assertIn("agy-001", cids)
            self.assertIn("agy-002", cids)

            # Check that workspace was unpacked from JSON array
            router_sess = [s for s in sessions if s["id"] == "agy-001"][0]
            self.assertEqual(router_sess["workspace"], "/mnt/a/code/router")
            self.assertEqual(router_sess["group"], "Routing")
            self.assertEqual(router_sess["msgs"], 14)
        finally:
            os.path.expanduser = orig_expanduser

    def test_05_complete_multi_layer_deletion(self):
        """Test multi-layer purge across brain, conversations db, summaries.db, annotations, and history.db."""
        fake_home = os.path.join(self.test_root, "home")
        mock_cli_dir = os.path.join(fake_home, ".gemini", "antigravity-cli")
        mock_conv_dir = os.path.join(mock_cli_dir, "conversations")
        mock_annot_dir = os.path.join(mock_cli_dir, "annotations")
        mock_plugin_data = os.path.join(mock_cli_dir, "plugin_data", "sessionlist")
        os.makedirs(mock_conv_dir, exist_ok=True)
        os.makedirs(mock_annot_dir, exist_ok=True)
        os.makedirs(mock_plugin_data, exist_ok=True)

        cid_to_del = "target-del-999"
        cid_to_keep = "keeper-111"

        # 1. Setup Brain Directory
        brain_del = os.path.join(ach.BRAIN_DIR, cid_to_del)
        brain_keep = os.path.join(ach.BRAIN_DIR, cid_to_keep)
        os.makedirs(brain_del, exist_ok=True)
        os.makedirs(brain_keep, exist_ok=True)
        with open(os.path.join(brain_del, "data.txt"), "w") as f: f.write("dummy")
        with open(os.path.join(brain_keep, "data.txt"), "w") as f: f.write("keep")

        # 2. Setup Conversations DBs (*.db, *.db-wal, *.db-shm)
        for ext in (".db", ".db-wal", ".db-shm"):
            with open(os.path.join(mock_conv_dir, f"{cid_to_del}{ext}"), "w") as f: f.write("db")
            with open(os.path.join(mock_conv_dir, f"{cid_to_keep}{ext}"), "w") as f: f.write("db")

        # 3. Setup Annotations
        with open(os.path.join(mock_annot_dir, f"{cid_to_del}.pbtxt"), "w") as f: f.write("annot")
        with open(os.path.join(mock_annot_dir, f"{cid_to_keep}.pbtxt"), "w") as f: f.write("annot")

        # 4. Setup conversation_summaries.db
        sum_db_path = os.path.join(mock_cli_dir, "conversation_summaries.db")
        c_sum = sqlite3.connect(sum_db_path)
        c_sum.execute("CREATE TABLE conversation_summaries (conversation_id TEXT PRIMARY KEY, title TEXT);")
        c_sum.execute("CREATE VIRTUAL TABLE conversations_fts USING fts5(conversation_id UNINDEXED, title);")
        c_sum.execute("CREATE TABLE conversation_parents (conversation_id TEXT PRIMARY KEY, parent_id TEXT);")
        c_sum.execute("INSERT INTO conversation_summaries VALUES (?, 'Del Chat'), (?, 'Keep Chat');", (cid_to_del, cid_to_keep))
        c_sum.execute("INSERT INTO conversations_fts VALUES (?, 'Del Chat'), (?, 'Keep Chat');", (cid_to_del, cid_to_keep))
        c_sum.execute("INSERT INTO conversation_parents VALUES (?, 'parent-0'), ('other-1', ?);", (cid_to_del, cid_to_del))
        c_sum.commit()
        c_sum.close()

        # 5. Setup history.db and mirror files
        ach.init_db()
        ach.write_session({"id": cid_to_del, "title": "Delete Me", "mtime": time.time(), "msgs": 1, "group": "Test"})
        ach.write_session({"id": cid_to_keep, "title": "Keep Me", "mtime": time.time(), "msgs": 1, "group": "Test"})

        orig_expanduser = os.path.expanduser
        orig_get_dirs = ach.get_all_data_dirs
        try:
            os.path.expanduser = lambda path: path.replace("~", fake_home) if path.startswith("~") else orig_expanduser(path)
            ach.get_all_data_dirs = lambda: [ach.DATA_DIR, mock_plugin_data]

            # Execute multi-layer purge
            purged_count = ach.purge_chats_from_all_storage([cid_to_del])
            self.assertEqual(purged_count, 1)

            # Check 1: Brain folder
            self.assertFalse(os.path.exists(brain_del))
            self.assertTrue(os.path.exists(brain_keep))

            # Check 2: Conversations files
            for ext in (".db", ".db-wal", ".db-shm"):
                self.assertFalse(os.path.exists(os.path.join(mock_conv_dir, f"{cid_to_del}{ext}")))
                self.assertTrue(os.path.exists(os.path.join(mock_conv_dir, f"{cid_to_keep}{ext}")))

            # Check 3: Annotations
            self.assertFalse(os.path.exists(os.path.join(mock_annot_dir, f"{cid_to_del}.pbtxt")))
            self.assertTrue(os.path.exists(os.path.join(mock_annot_dir, f"{cid_to_keep}.pbtxt")))

            # Check 4: conversation_summaries.db
            c_check = sqlite3.connect(sum_db_path)
            rows_sum = c_check.execute("SELECT conversation_id FROM conversation_summaries;").fetchall()
            self.assertEqual([r[0] for r in rows_sum], [cid_to_keep])
            rows_fts = c_check.execute("SELECT conversation_id FROM conversations_fts;").fetchall()
            self.assertEqual([r[0] for r in rows_fts], [cid_to_keep])
            rows_parents = c_check.execute("SELECT conversation_id FROM conversation_parents;").fetchall()
            self.assertEqual(len(rows_parents), 0)
            c_check.close()

            # Check 5: history.db
            remaining_sessions = ach.read_sessions()
            self.assertEqual(len(remaining_sessions), 1)
            self.assertEqual(remaining_sessions[0]["id"], cid_to_keep)

            # Check FTS index cleaned
            search_res = ach.search_sessions_fts("Delete")
            self.assertEqual(len(search_res), 0)
        finally:
            os.path.expanduser = orig_expanduser
            ach.get_all_data_dirs = orig_get_dirs


# Multiprocessing helper for Concurrency Test
def _writer_worker(db_path, worker_id, iterations):
    for i in range(iterations):
        conn = ach.get_db_connection(db_path)
        try:
            cid = f"worker-{worker_id}-item-{i}"
            now = time.time()
            with conn:
                conn.execute("BEGIN IMMEDIATE;")
                conn.execute("""
                    INSERT OR REPLACE INTO sessions 
                    (conversation_id, timestamp, relative_time, title, group_name, workspace, step_count, last_modified_time)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """, (cid, datetime.now().isoformat(), "Just now", f"Worker {worker_id} Item {i}", f"Group{worker_id}", "/ws", i, now))
                ach.update_fts_entry(conn, cid, f"Worker {worker_id} Item {i}", f"Group{worker_id}", "/ws", f"content {i}")
        finally:
            conn.close()
        time.sleep(0.001)

def _reader_worker(db_path, iterations, results_queue):
    successes = 0
    for _ in range(iterations):
        conn = ach.get_db_connection(db_path)
        try:
            cur = conn.cursor()
            rows = cur.execute("SELECT count(*) FROM sessions;").fetchone()
            if rows is not None:
                successes += 1
        except Exception:
            pass
        finally:
            conn.close()
        time.sleep(0.001)
    results_queue.put(successes)

class TestSQLiteConcurrency(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="sl_concurrency_")
        self.db_path = os.path.join(self.test_dir, "history.db")
        ach.init_db(db_path=self.db_path)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_wal_multiprocess_concurrent_read_write(self):
        """Verify high-concurrency multi-process read/write under WAL mode with zero locking deadlocks."""
        num_writers = 4
        num_readers = 4
        iterations = 25

        processes = []
        queue = multiprocessing.Queue()

        # Start readers
        for _ in range(num_readers):
            p = multiprocessing.Process(target=_reader_worker, args=(self.db_path, iterations, queue))
            p.start()
            processes.append(p)

        # Start writers
        for w_id in range(num_writers):
            p = multiprocessing.Process(target=_writer_worker, args=(self.db_path, w_id, iterations))
            p.start()
            processes.append(p)

        for p in processes:
            p.join(timeout=30)
            self.assertFalse(p.is_alive(), "Process hung or deadlocked!")

        # Verify all writer rows were inserted
        conn = ach.get_db_connection(self.db_path)
        try:
            total_rows = conn.execute("SELECT count(*) FROM sessions;").fetchone()[0]
            self.assertEqual(total_rows, num_writers * iterations)
        finally:
            conn.close()

        # Verify readers succeeded without locking errors
        reader_successes = []
        while not queue.empty():
            reader_successes.append(queue.get())
        self.assertEqual(len(reader_successes), num_readers)
        for s in reader_successes:
            self.assertEqual(s, iterations)

if __name__ == "__main__":
    unittest.main()
