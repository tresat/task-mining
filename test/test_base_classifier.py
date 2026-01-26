import unittest
import os
import sys

# Add parent directory to path to allow importing classification package
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from classification.base_classifier import BaseClassifier

class SimpleTestClassifier(BaseClassifier):
    """Simple test implementation of BaseClassifier"""
    
    def check_dependencies(self, pair):
        return False
    
    def check_version_update(self, pair, file_info):
        return None
    
    def classify(self, pair):
        return pair

class TestBaseClassifier(unittest.TestCase):
    def setUp(self):
        self.classifier = SimpleTestClassifier("fake_token", "owner", "repo")

    def test_single_line_change_valid(self):
        """Test that a true single-line change is detected"""
        commit_diff = {
            "files": [{
                "filename": "libs.versions.toml",
                "patch": """@@ -1,3 +1,3 @@
 [versions]
-androidxCore = "1.9.0"
+androidxCore = "1.10.0"
 androidxCompose = "1.5.0\""""
            }]
        }
        result = self.classifier.is_single_line_change(commit_diff)
        self.assertIsNotNone(result)
        self.assertEqual(result["filename"], "libs.versions.toml")

    def test_single_line_change_multiple_lines(self):
        """Test that multiple line changes are not tagged as single-line"""
        commit_diff = {
            "files": [{
                "filename": "libs.versions.toml",
                "patch": """@@ -1,4 +1,4 @@
 [versions]
-androidxCore = "1.9.0"
-androidxCompose = "1.5.0"
+androidxCore = "1.10.0"
+androidxCompose = "1.6.0\""""
            }]
        }
        result = self.classifier.is_single_line_change(commit_diff)
        self.assertIsNone(result, "Should return None for multi-line changes")

    def test_single_line_change_multiple_files(self):
        """Test that changes to multiple files are not tagged as single-line"""
        commit_diff = {
            "files": [
                {
                    "filename": "libs.versions.toml",
                    "patch": """@@ -1,3 +1,3 @@
 [versions]
-androidxCore = "1.9.0"
+androidxCore = "1.10.0\""""
                },
                {
                    "filename": "build.gradle",
                    "patch": """@@ -1,3 +1,3 @@
 dependencies {
-    implementation "androidx.core:core:1.9.0"
+    implementation "androidx.core:core:1.10.0\""""
                }
            ]
        }
        result = self.classifier.is_single_line_change(commit_diff)
        self.assertIsNone(result, "Should return None for multi-file changes")

    def test_single_line_change_non_dependency_file(self):
        """Test that changes to non-dependency files are not tagged as single-line"""
        commit_diff = {
            "files": [{
                "filename": "src/main/java/Example.java",
                "patch": """@@ -1,3 +1,3 @@
 public class Example {
-    private int version = 1;
+    private int version = 2;
 }"""
            }]
        }
        result = self.classifier.is_single_line_change(commit_diff)
        self.assertIsNone(result, "Should return None for non-dependency files")

    def test_single_line_change_no_patch(self):
        """Test that files without patches are not tagged as single-line"""
        commit_diff = {
            "files": [{
                "filename": "libs.versions.toml",
                "patch": ""
            }]
        }
        result = self.classifier.is_single_line_change(commit_diff)
        self.assertIsNone(result, "Should return None when no patch is available")

    def test_single_line_change_only_additions(self):
        """Test that only additions (no deletions) are not tagged as single-line"""
        commit_diff = {
            "files": [{
                "filename": "libs.versions.toml",
                "patch": """@@ -1,2 +1,3 @@
 [versions]
 androidxCore = "1.9.0"
+androidxCompose = "1.5.0\""""
            }]
        }
        result = self.classifier.is_single_line_change(commit_diff)
        self.assertIsNone(result, "Should return None when only adding lines")

    def test_single_line_change_gradle_file(self):
        """Test that build.gradle files are recognized"""
        commit_diff = {
            "files": [{
                "filename": "app/build.gradle",
                "patch": """@@ -10,3 +10,3 @@
 dependencies {
-    implementation 'androidx.core:core:1.9.0'
+    implementation 'androidx.core:core:1.10.0'
 }"""
            }]
        }
        result = self.classifier.is_single_line_change(commit_diff)
        self.assertIsNotNone(result)
        self.assertEqual(result["filename"], "app/build.gradle")

    def test_single_line_change_gradle_kts_file(self):
        """Test that build.gradle.kts files are recognized"""
        commit_diff = {
            "files": [{
                "filename": "app/build.gradle.kts",
                "patch": """@@ -10,3 +10,3 @@
 dependencies {
-    implementation("androidx.core:core:1.9.0")
+    implementation("androidx.core:core:1.10.0")
 }"""
            }]
        }
        result = self.classifier.is_single_line_change(commit_diff)
        self.assertIsNotNone(result)
        self.assertEqual(result["filename"], "app/build.gradle.kts")

if __name__ == '__main__':
    unittest.main()
