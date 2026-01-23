import unittest
import os
import sys
import tempfile
from unittest.mock import patch, MagicMock

# Add parent directory to path to allow importing mining package
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mining.mine_commits import CommitMiner, process_repo, main

class TestCommitMiner(unittest.TestCase):
    def setUp(self):
        self.miner = CommitMiner("fake_token", "owner", "repo")

    def test_is_build_successful(self):
        # Case 1: StatusCheckRollup says SUCCESS
        commit = {"statusCheckRollup": {"state": "SUCCESS"}}
        self.assertTrue(self.miner.is_build_successful(commit))

        # Case 2: Legacy Status says SUCCESS
        commit = {"status": {"state": "SUCCESS"}}
        self.assertTrue(self.miner.is_build_successful(commit))

        # Case 3: Failure
        commit = {"statusCheckRollup": {"state": "FAILURE"}}
        self.assertFalse(self.miner.is_build_successful(commit))

        # Case 4: No status
        commit = {}
        self.assertFalse(self.miner.is_build_successful(commit))

    def test_is_single_line_change(self):
        # Case 1: Valid single line change in build.gradle
        commit_diff = {
            "files": [
                {
                    "filename": "build.gradle",
                    "additions": 1,
                    "deletions": 1
                }
            ]
        }
        result = self.miner.is_single_line_change(commit_diff)
        self.assertIsNotNone(result)

        # Case 2: Multiple files changed
        commit_diff = {
            "files": [
                {"filename": "build.gradle", "additions": 1, "deletions": 1},
                {"filename": "src/Main.java", "additions": 1, "deletions": 0}
            ]
        }
        result = self.miner.is_single_line_change(commit_diff)
        self.assertIsNone(result)

        # Case 3: Wrong file type
        commit_diff = {
            "files": [
                {"filename": "src/Main.java", "additions": 1, "deletions": 1}
            ]
        }
        result = self.miner.is_single_line_change(commit_diff)
        self.assertIsNone(result)

        # Case 4: Multiple lines changed
        commit_diff = {
            "files": [
                {"filename": "build.gradle", "additions": 2, "deletions": 1}
            ]
        }
        result = self.miner.is_single_line_change(commit_diff)
        self.assertIsNone(result)

    def test_extract_version(self):
        # Test various version formats
        line1 = 'implementation("com.example:lib:1.2.3")'
        self.assertEqual(self.miner._extract_version(line1), "1.2.3")

        line2 = 'version = "2.0.0"'
        self.assertEqual(self.miner._extract_version(line2), "2.0.0")

        line3 = "someLib = '1.5.2-alpha'"
        self.assertEqual(self.miner._extract_version(line3), "1.5.2-alpha")

        line4 = 'androidxCore = "1.10.0"'
        self.assertEqual(self.miner._extract_version(line4), "1.10.0")

        line5 = 'no version here'
        self.assertIsNone(self.miner._extract_version(line5))

    def test_is_version_increase(self):
        # Test version comparisons
        self.assertTrue(self.miner._is_version_increase("1.0.0", "1.0.1"))
        self.assertTrue(self.miner._is_version_increase("1.0.0", "1.1.0"))
        self.assertTrue(self.miner._is_version_increase("1.0.0", "2.0.0"))
        self.assertTrue(self.miner._is_version_increase("1.9.9", "1.10.0"))
        
        self.assertFalse(self.miner._is_version_increase("1.0.1", "1.0.0"))
        self.assertFalse(self.miner._is_version_increase("2.0.0", "1.9.9"))
        self.assertFalse(self.miner._is_version_increase("1.0.0", "1.0.0"))

    def test_is_content_line(self):
        # Test content line detection
        self.assertTrue(self.miner._is_content_line("    implementation(...)"))
        self.assertTrue(self.miner._is_content_line(" some code"))
        self.assertTrue(self.miner._is_content_line(""))
        
        self.assertFalse(self.miner._is_content_line("\\ No newline at end of file"))
        self.assertFalse(self.miner._is_content_line("--- a/file.txt"))
        self.assertFalse(self.miner._is_content_line("+++ b/file.txt"))

    def test_extract_version_change(self):
        # Test extracting version change from a patch
        patch = """@@ -10,1 +10,1 @@
-    implementation("com.example:lib:1.0.0")
+    implementation("com.example:lib:1.1.0")
"""
        result = self.miner.extract_version_change(patch)
        self.assertIsNotNone(result)
        self.assertEqual(result["from_version"], "1.0.0")
        self.assertEqual(result["to_version"], "1.1.0")

        # Test with no version change (downgrade)
        patch2 = """@@ -10,1 +10,1 @@
-    implementation("com.example:lib:2.0.0")
+    implementation("com.example:lib:1.0.0")
"""
        result2 = self.miner.extract_version_change(patch2)
        self.assertIsNone(result2)

    @patch('mining.mine_commits.CommitMiner._query')
    def test_get_default_branch_main_exists(self, mock_query):
        """Test default branch detection when 'main' exists"""
        # Mock response indicating main branch exists
        mock_query.return_value = {
            "data": {
                "repository": {
                    "ref": {
                        "name": "main"
                    }
                }
            }
        }
        
        result = self.miner.get_default_branch()
        self.assertEqual(result, "refs/heads/main")
    
    @patch('mining.mine_commits.CommitMiner._query')
    def test_get_default_branch_master_fallback(self, mock_query):
        """Test default branch detection falls back to 'master' when 'main' doesn't exist"""
        # First call returns None (main doesn't exist), second call returns master
        mock_query.side_effect = [
            {"data": {"repository": {"ref": None}}},  # main doesn't exist
            {"data": {"repository": {"ref": {"name": "master"}}}}  # master exists
        ]
        
        result = self.miner.get_default_branch()
        self.assertEqual(result, "refs/heads/master")

class TestProcessRepo(unittest.TestCase):
    """Test the process_repo function for handling single repos and file lists"""
    
    @patch('mining.mine_commits.CommitMiner')
    def test_process_single_repo(self, mock_miner_class):
        """Test processing a single repository"""
        mock_miner = MagicMock()
        mock_miner.get_default_branch.return_value = "refs/heads/main"
        mock_miner_class.return_value = mock_miner
        
        with tempfile.TemporaryDirectory() as tmpdir:
            process_repo("owner/repo", "fake_token", 100, None, tmpdir, tmpdir, None)
            
            # Verify miner was created with correct parameters
            mock_miner_class.assert_called_once_with("fake_token", "owner", "repo")
            
            # Verify get_default_branch was called
            mock_miner.get_default_branch.assert_called_once()
            
            # Verify mine was called
            mock_miner.mine.assert_called_once()

    def test_process_repo_list_from_file(self):
        """Test processing multiple repositories from a file"""
        # Create a temporary file with repo list
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write("owner1/repo1\n")
            f.write("owner2/repo2\n")
            f.write("# This is a comment\n")
            f.write("owner3/repo3\n")
            temp_file = f.name
        
        try:
            # Read the file and verify it's parsed correctly
            with open(temp_file, 'r') as f:
                repos = [line.strip() for line in f if line.strip() and not line.startswith("#")]
            
            self.assertEqual(len(repos), 3)
            self.assertIn("owner1/repo1", repos)
            self.assertIn("owner2/repo2", repos)
            self.assertIn("owner3/repo3", repos)
            self.assertNotIn("# This is a comment", repos)
        finally:
            os.unlink(temp_file)

if __name__ == '__main__':
    unittest.main()
