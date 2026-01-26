import unittest
import os
import sys

# Add parent directory to path to allow importing classification package
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from classification.simple_classifier import SimpleClassifier


class TestNewClassifications(unittest.TestCase):
    def setUp(self):
        self.classifier = SimpleClassifier("fake_token", "owner", "repo")

    def test_gradle_wrapper_update_detection(self):
        """Test that gradle wrapper changes are detected"""
        files = [{
            "filename": "gradle/wrapper/gradle-wrapper.properties",
            "patch": """@@ -1,3 +1,3 @@
 distributionBase=GRADLE_USER_HOME
-distributionUrl=https\\://services.gradle.org/distributions/gradle-7.5-bin.zip
+distributionUrl=https\\://services.gradle.org/distributions/gradle-8.0-bin.zip
"""
        }]
        
        result = self.classifier.check_gradle_wrapper_update(files)
        self.assertTrue(result, "Should detect gradle wrapper update")

    def test_configuration_cache_detection(self):
        """Test that configuration cache changes are detected"""
        files = [{
            "filename": "gradle.properties",
            "patch": """@@ -1,2 +1,3 @@
 org.gradle.jvmargs=-Xmx2048m
+org.gradle.configuration-cache=true
"""
        }]
        
        result = self.classifier.check_configuration_cache_update(files)
        self.assertTrue(result, "Should detect configuration cache update")

    def test_configuration_cache_unsafe_detection(self):
        """Test that unsafe configuration cache changes are detected"""
        files = [{
            "filename": "gradle.properties",
            "patch": """@@ -1,2 +1,3 @@
 org.gradle.jvmargs=-Xmx2048m
+org.gradle.unsafe.configuration-cache=true
"""
        }]
        
        result = self.classifier.check_configuration_cache_update(files)
        self.assertTrue(result, "Should detect unsafe configuration cache update")

    def test_plugin_update_detection(self):
        """Test that plugin updates are detected"""
        files = [{
            "filename": "build.gradle",
            "patch": """@@ -1,4 +1,4 @@
 plugins {
-    id 'com.android.application' version '7.0.0'
+    id 'com.android.application' version '8.0.0'
 }
"""
        }]
        
        result = self.classifier.check_plugin_update(files)
        self.assertTrue(result, "Should detect plugin update")

    def test_plugin_update_kotlin_dsl(self):
        """Test that plugin updates in Kotlin DSL are detected"""
        files = [{
            "filename": "build.gradle.kts",
            "patch": """@@ -1,4 +1,4 @@
 plugins {
-    id("com.android.application") version "7.0.0"
+    id("com.android.application") version "8.0.0"
 }
"""
        }]
        
        result = self.classifier.check_plugin_update(files)
        self.assertTrue(result, "Should detect plugin update in Kotlin DSL")

    def test_warning_suppression_detection(self):
        """Test that warning suppression is detected"""
        files = [{
            "filename": "src/main/java/Example.java",
            "patch": """@@ -1,3 +1,4 @@
 public class Example {
+    @SuppressWarnings("unchecked")
     private List list;
 }
"""
        }]
        
        result = self.classifier.check_warning_suppression(files)
        self.assertTrue(result, "Should detect @SuppressWarnings")

    def test_warning_suppression_kotlin(self):
        """Test that Kotlin warning suppression is detected"""
        files = [{
            "filename": "src/main/kotlin/Example.kt",
            "patch": """@@ -1,3 +1,4 @@
 class Example {
+    @Suppress("UNCHECKED_CAST")
     val list: List<Any>
 }
"""
        }]
        
        result = self.classifier.check_warning_suppression(files)
        self.assertTrue(result, "Should detect @Suppress")

    def test_warning_suppression_lint(self):
        """Test that lint suppression is detected"""
        files = [{
            "filename": "src/main/java/Example.java",
            "patch": """@@ -1,3 +1,4 @@
 public class Example {
+    @SuppressLint("SetTextI18n")
     void setText() {}
 }
"""
        }]
        
        result = self.classifier.check_warning_suppression(files)
        self.assertTrue(result, "Should detect @SuppressLint")

    def test_gradle_update_category(self):
        """Test that Gradle Update category is assigned when wrapper changes"""
        # Mock the get_commit_diff method to return test data
        def mock_get_commit_diff(commit_sha):
            return {
                "files": [{
                    "filename": "gradle/wrapper/gradle-wrapper.properties",
                    "patch": """@@ -1,3 +1,3 @@
 distributionBase=GRADLE_USER_HOME
-distributionUrl=https\\://services.gradle.org/distributions/gradle-7.5-bin.zip
+distributionUrl=https\\://services.gradle.org/distributions/gradle-8.0-bin.zip
"""
                }]
            }
        
        self.classifier.get_commit_diff = mock_get_commit_diff
        
        pair = {
            "to_commit": "abc123",
            "tags": [],
            "category": None
        }
        
        result = self.classifier.classify_pair(pair)
        
        self.assertEqual(result["category"], "Gradle Update", "Should assign Gradle Update category")
        self.assertIn("wrapper-update", result["tags"], "Should add wrapper-update tag")

    def test_gradle_update_with_minor_changes(self):
        """Test that Gradle Update category is assigned even with minor other changes"""
        def mock_get_commit_diff(commit_sha):
            return {
                "files": [
                    {
                        "filename": "gradle/wrapper/gradle-wrapper.properties",
                        "patch": """@@ -1,3 +1,3 @@
 distributionBase=GRADLE_USER_HOME
-distributionUrl=https\\://services.gradle.org/distributions/gradle-7.5-bin.zip
+distributionUrl=https\\://services.gradle.org/distributions/gradle-8.0-bin.zip
"""
                    },
                    {
                        "filename": "build.gradle",
                        "patch": """@@ -1,3 +1,3 @@
 plugins {
-    id 'com.android.application' version '7.0.0'
+    id 'com.android.application' version '8.0.0'
 }
"""
                    }
                ]
            }
        
        self.classifier.get_commit_diff = mock_get_commit_diff
        
        pair = {
            "to_commit": "abc123",
            "tags": [],
            "category": None
        }
        
        result = self.classifier.classify_pair(pair)
        
        self.assertEqual(result["category"], "Gradle Update", "Should assign Gradle Update category even with other changes")
        self.assertIn("wrapper-update", result["tags"], "Should add wrapper-update tag")
        self.assertIn("plugin-update", result["tags"], "Should add plugin-update tag")

    def test_all_new_tags_together(self):
        """Test that multiple new tags can be detected in one commit"""
        def mock_get_commit_diff(commit_sha):
            return {
                "files": [
                    {
                        "filename": "gradle/wrapper/gradle-wrapper.properties",
                        "patch": """@@ -1,3 +1,3 @@
-distributionUrl=https\\://services.gradle.org/distributions/gradle-7.5-bin.zip
+distributionUrl=https\\://services.gradle.org/distributions/gradle-8.0-bin.zip
"""
                    },
                    {
                        "filename": "gradle.properties",
                        "patch": """@@ -1,2 +1,3 @@
 org.gradle.jvmargs=-Xmx2048m
+org.gradle.configuration-cache=true
"""
                    },
                    {
                        "filename": "build.gradle",
                        "patch": """@@ -1,4 +1,4 @@
 plugins {
-    id 'com.android.application' version '7.0.0'
+    id 'com.android.application' version '8.0.0'
 }
"""
                    },
                    {
                        "filename": "src/main/java/Example.java",
                        "patch": """@@ -1,3 +1,4 @@
 public class Example {
+    @SuppressWarnings("deprecation")
     private Object obj;
 }
"""
                    }
                ]
            }
        
        self.classifier.get_commit_diff = mock_get_commit_diff
        
        pair = {
            "to_commit": "abc123",
            "tags": [],
            "category": None
        }
        
        result = self.classifier.classify_pair(pair)
        
        self.assertEqual(result["category"], "Gradle Update")
        self.assertIn("wrapper-update", result["tags"])
        self.assertIn("configuration-cache-update", result["tags"])
        self.assertIn("plugin-update", result["tags"])
        self.assertIn("warning-suppression", result["tags"])


if __name__ == '__main__':
    unittest.main()
