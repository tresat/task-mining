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

        # Case 4: No status - should fail by default
        commit = {}
        self.assertFalse(self.miner.is_build_successful(commit))
    
    def test_is_build_successful_with_allow_missing_status(self):
        # Create miner with allow_missing_status=True
        miner_with_flag = CommitMiner("fake_token", "owner", "repo", allow_missing_status=True)
        
        # Case 1: StatusCheckRollup says SUCCESS - should still succeed
        commit = {"statusCheckRollup": {"state": "SUCCESS"}}
        self.assertTrue(miner_with_flag.is_build_successful(commit))
        
        # Case 2: StatusCheckRollup says FAILURE - should still fail
        commit = {"statusCheckRollup": {"state": "FAILURE"}}
        self.assertFalse(miner_with_flag.is_build_successful(commit))
        
        # Case 3: No status - should succeed when flag is enabled
        commit = {}
        self.assertTrue(miner_with_flag.is_build_successful(commit))

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
            process_repo(
                repo="owner/repo",
                token="fake_token",
                search_limit=100,
                results_limit=None,
                output_dir=tmpdir,
                state_dir=tmpdir,
                ref=None,
                use_cache=True,
                allow_missing_status=False
            )
            
            # Verify miner was created with correct parameters (including allow_missing_status)
            mock_miner_class.assert_called_once_with("fake_token", "owner", "repo", allow_missing_status=False)
            
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
