import os
import sys
import unittest
import subprocess

class TestSessionListCLI(unittest.TestCase):
    def setUp(self):
        self.script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "sessionlist.py"))

    def test_version_flags(self):
        for flag in ["--version", "-v"]:
            proc = subprocess.run([sys.executable, self.script_path, flag], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0)
            self.assertIn("v2.2.0", proc.stdout)

    def test_help_flags(self):
        for flag in ["--help", "-h"]:
            proc = subprocess.run([sys.executable, self.script_path, flag], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0)
            self.assertIn("-d, --delete, --del, rm", proc.stdout)
            self.assertIn("-x, --export", proc.stdout)
            self.assertIn("-s, --search", proc.stdout)
            self.assertIn("-l, --list", proc.stdout)
            self.assertIn("-a, --all", proc.stdout)

    def test_list_and_all_flags(self):
        for flag in ["-l", "--list", "-a", "--all", "--list-all"]:
            proc = subprocess.run([sys.executable, self.script_path, flag], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0)

    def test_search_flags(self):
        for flag in ["-s", "--search", "--search-cli"]:
            proc = subprocess.run([sys.executable, self.script_path, flag, "nonexistent_query_xyz"], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0)

    def test_export_short_flag_help(self):
        proc = subprocess.run([sys.executable, self.script_path, "-x", "nonexistent_id_9999"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("Error: ", proc.stdout)

    def test_delete_flags_validation(self):
        for flag in ["-d", "--delete", "rm", "--del"]:
            proc = subprocess.run([sys.executable, self.script_path, flag], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0)
            self.assertIn("Error: Missing session ID(s) to delete", proc.stdout)

    def test_delete_nonexistent_ids(self):
        for cmd in [
            ["-d", "999999,999998"],
            ["rm", "999991", "999992"],
            ["rm", "999980-999985"],
            ["--delete", "999990"]
        ]:
            proc = subprocess.run([sys.executable, self.script_path] + cmd, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0)
            self.assertIn("No chats matched", proc.stdout)

if __name__ == "__main__":
    unittest.main()
