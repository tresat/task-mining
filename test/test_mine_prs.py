import unittest
import os
import sys

# Add parent directory to path to allow importing mining package
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mining.mine_prs import PRMiner

class TestPRMiner(unittest.TestCase):
    def setUp(self):
        self.miner = PRMiner("fake_token", "owner", "repo")

    def test_is_build_successful(self):
        # Case 1: StatusCheckRollup says SUCCESS
        node = {"commit": {"statusCheckRollup": {"state": "SUCCESS"}}}
        self.assertTrue(self.miner.is_build_successful(node))

        # Case 2: Legacy Status says SUCCESS
        node = {"commit": {"status": {"state": "SUCCESS"}}}
        self.assertTrue(self.miner.is_build_successful(node))

        # Case 3: Failure
        node = {"commit": {"statusCheckRollup": {"state": "FAILURE"}}}
        self.assertFalse(self.miner.is_build_successful(node))

    def test_is_build_failed(self):
        # Case 1: StatusCheckRollup says FAILURE
        node = {"commit": {"statusCheckRollup": {"state": "FAILURE"}}}
        self.assertTrue(self.miner.is_build_failed(node))

        # Case 2: ERROR
        node = {"commit": {"statusCheckRollup": {"state": "ERROR"}}}
        self.assertTrue(self.miner.is_build_failed(node))

        # Case 3: SUCCESS is not failure
        node = {"commit": {"statusCheckRollup": {"state": "SUCCESS"}}}
        self.assertFalse(self.miner.is_build_failed(node))

    def test_mine_logic_mock(self):
        # We can't easily mock the full GraphQL flow without a lot of setup,
        # but we can verify the logic if we extracted the loop.
        # Since the loop is inside `mine`, we'll rely on the live test for full flow,
        # and these unit tests for the helper predicates.
        pass

if __name__ == '__main__':
    unittest.main()
