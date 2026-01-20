import unittest
from mine_simple_dependency_updates import SimpleDependencyMiner

class TestSimpleDependencyMiner(unittest.TestCase):
    def setUp(self):
        self.miner = SimpleDependencyMiner("fake_token", "owner", "repo")

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

if __name__ == '__main__':
    unittest.main()
