import unittest
import json
import os
import sys
from unittest.mock import Mock, patch, MagicMock
import tempfile

# Add parent directory to path to import classification module
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from classification.gemini_classifier import GeminiClassifier


class TestGeminiClassifier(unittest.TestCase):
    """Test the Gemini AI classifier with commit pairs and PRs."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.test_owner = "android"
        self.test_name = "nowinandroid"
        self.test_github_token = "test_github_token"
        self.test_gemini_key = "test_gemini_key"
        
        # Example commit pair (dependency update)
        self.test_commit_pair = {
            "from_commit": "0c47deeb23fa3650f55639317c95b55027768d3c",
            "from_msg": "",
            "to_commit": "27644a06d52c74824a4ff8f0e80ca65e36a539a0",
            "to_msg": "Update Roborazzi 1.56.0, compatible with AGP 9",
            "files_changed": [
                {
                    "filename": "gradle/libs.versions.toml",
                    "line_number": 60,
                    "from_line_contents": "roborazzi = \"1.51.0\"",
                    "to_line_contents": "roborazzi = \"1.56.0\""
                }
            ]
        }
        
        # Example PR (for testing backward compatibility)
        self.test_pr = {
            "pr_id": 123,
            "from_commit": "abc123",
            "from_msg": "Initial implementation",
            "to_commit": "def456",
            "to_msg": "Update dependency version",
            "files_changed": []
        }
        
    def test_classifier_initialization(self):
        """Test that classifier initializes correctly."""
        classifier = GeminiClassifier(
            self.test_github_token,
            self.test_gemini_key,
            self.test_owner,
            self.test_name
        )
        
        self.assertEqual(classifier.owner, self.test_owner)
        self.assertEqual(classifier.name, self.test_name)
        self.assertEqual(classifier.github_token, self.test_github_token)
        self.assertEqual(classifier.gemini_key, self.test_gemini_key)
        self.assertIn("Authorization", classifier.headers)
        
    @patch('classification.gemini_classifier.requests.get')
    def test_get_commit_diff(self, mock_get):
        """Test fetching commit diff from GitHub."""
        classifier = GeminiClassifier(
            self.test_github_token,
            self.test_gemini_key,
            self.test_owner,
            self.test_name
        )
        
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "diff --git a/file.txt b/file.txt\n+new line"
        mock_get.return_value = mock_response
        
        diff = classifier.get_commit_diff("abc123")
        
        self.assertIn("diff --git", diff)
        self.assertIn("+new line", diff)
        mock_get.assert_called_once()
        
    @patch('classification.gemini_classifier.requests.get')
    def test_get_commit_diff_failure(self, mock_get):
        """Test handling of failed diff fetch."""
        classifier = GeminiClassifier(
            self.test_github_token,
            self.test_gemini_key,
            self.test_owner,
            self.test_name
        )
        
        # Mock failed response
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response
        
        diff = classifier.get_commit_diff("abc123")
        
        self.assertEqual(diff, "")
        
    @patch('classification.gemini_classifier.requests.post')
    def test_classify_with_gemini_yes(self, mock_post):
        """Test Gemini classification returning YES for dependency update."""
        classifier = GeminiClassifier(
            self.test_github_token,
            self.test_gemini_key,
            self.test_owner,
            self.test_name
        )
        
        # Mock Gemini API response saying YES
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "text": "YES"
                    }]
                }
            }]
        }
        mock_post.return_value = mock_response
        
        result = classifier.classify_with_gemini(
            "Update Roborazzi 1.56.0",
            "roborazzi = \"1.51.0\" -> roborazzi = \"1.56.0\""
        )
        
        self.assertEqual(result, "YES")
        
    @patch('classification.gemini_classifier.requests.post')
    def test_classify_with_gemini_no(self, mock_post):
        """Test Gemini classification returning NO for non-dependency change."""
        classifier = GeminiClassifier(
            self.test_github_token,
            self.test_gemini_key,
            self.test_owner,
            self.test_name
        )
        
        # Mock Gemini API response saying NO
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "text": "NO"
                    }]
                }
            }]
        }
        mock_post.return_value = mock_response
        
        result = classifier.classify_with_gemini(
            "Add new feature",
            "function newFeature() { }"
        )
        
        self.assertEqual(result, "NO")
        
    def test_classify_with_gemini_no_diff(self):
        """Test classification with empty diff."""
        classifier = GeminiClassifier(
            self.test_github_token,
            self.test_gemini_key,
            self.test_owner,
            self.test_name
        )
        
        result = classifier.classify_with_gemini("Some message", "")
        
        self.assertEqual(result, "Unknown (No Diff)")
        
    @patch('classification.gemini_classifier.requests.post')
    @patch('classification.gemini_classifier.requests.get')
    def test_run_with_commit_pair(self, mock_get, mock_post):
        """Test running classifier with commit pair (not PR)."""
        classifier = GeminiClassifier(
            self.test_github_token,
            self.test_gemini_key,
            self.test_owner,
            self.test_name
        )
        
        # Mock diff response
        mock_diff_response = Mock()
        mock_diff_response.status_code = 200
        mock_diff_response.text = """diff --git a/gradle/libs.versions.toml b/gradle/libs.versions.toml
index abc123..def456 100644
--- a/gradle/libs.versions.toml
+++ b/gradle/libs.versions.toml
@@ -60,1 +60,1 @@
-roborazzi = "1.51.0"
+roborazzi = "1.56.0"
"""
        mock_get.return_value = mock_diff_response
        
        # Mock Gemini response
        mock_gemini_response = Mock()
        mock_gemini_response.status_code = 200
        mock_gemini_response.json.return_value = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "text": "YES, this is clearly a dependency update from Roborazzi 1.51.0 to 1.56.0."
                    }]
                }
            }]
        }
        mock_post.return_value = mock_gemini_response
        
        # Create temp files
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as input_file:
            json.dump([self.test_commit_pair], input_file)
            input_path = input_file.name
            
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as output_file:
            output_path = output_file.name
            
        try:
            # Run classifier
            classifier.run(input_path, output_path)
            
            # Verify output
            with open(output_path, 'r') as f:
                results = json.load(f)
                
            self.assertEqual(len(results), 1)
            self.assertIn("ai_is_dependency_update", results[0])
            self.assertEqual(results[0]["ai_is_dependency_update"], "YES")
            self.assertEqual(results[0]["to_commit"], self.test_commit_pair["to_commit"])
            self.assertEqual(results[0]["to_msg"], self.test_commit_pair["to_msg"])
            
        finally:
            # Cleanup temp files
            if os.path.exists(input_path):
                os.unlink(input_path)
            if os.path.exists(output_path):
                os.unlink(output_path)
                
    @patch('classification.gemini_classifier.requests.post')
    @patch('classification.gemini_classifier.requests.get')
    def test_run_with_pr_format(self, mock_get, mock_post):
        """Test running classifier with PR format (backward compatibility)."""
        classifier = GeminiClassifier(
            self.test_github_token,
            self.test_gemini_key,
            self.test_owner,
            self.test_name
        )
        
        # Mock diff response
        mock_diff_response = Mock()
        mock_diff_response.status_code = 200
        mock_diff_response.text = "diff --git a/file.txt b/file.txt"
        mock_get.return_value = mock_diff_response
        
        # Mock Gemini response
        mock_gemini_response = Mock()
        mock_gemini_response.status_code = 200
        mock_gemini_response.json.return_value = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "text": "YES"
                    }]
                }
            }]
        }
        mock_post.return_value = mock_gemini_response
        
        # Create temp files
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as input_file:
            json.dump([self.test_pr], input_file)
            input_path = input_file.name
            
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as output_file:
            output_path = output_file.name
            
        try:
            # Run classifier
            classifier.run(input_path, output_path)
            
            # Verify output
            with open(output_path, 'r') as f:
                results = json.load(f)
                
            self.assertEqual(len(results), 1)
            self.assertIn("ai_is_dependency_update", results[0])
            # Should handle PR format (to_commit)
            self.assertEqual(results[0]["to_commit"], self.test_pr["to_commit"])
            
        finally:
            # Cleanup temp files
            if os.path.exists(input_path):
                os.unlink(input_path)
            if os.path.exists(output_path):
                os.unlink(output_path)
                
    @patch('classification.gemini_classifier.requests.post')
    @patch('classification.gemini_classifier.requests.get')
    def test_run_skips_already_processed(self, mock_get, mock_post):
        """Test that classifier skips already processed commits."""
        classifier = GeminiClassifier(
            self.test_github_token,
            self.test_gemini_key,
            self.test_owner,
            self.test_name
        )
        
        # Create temp files with existing results
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as input_file:
            json.dump([self.test_commit_pair], input_file)
            input_path = input_file.name
            
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as output_file:
            # Pre-populate output with already processed result
            existing_result = self.test_commit_pair.copy()
            existing_result["ai_is_dependency_update"] = "YES"
            json.dump([existing_result], output_file)
            output_path = output_file.name
            
        try:
            # Run classifier
            classifier.run(input_path, output_path)
            
            # Verify no API calls were made (since commit was already processed)
            mock_get.assert_not_called()
            mock_post.assert_not_called()
            
            # Verify output still has the result
            with open(output_path, 'r') as f:
                results = json.load(f)
            self.assertEqual(len(results), 1)
            
        finally:
            # Cleanup temp files
            if os.path.exists(input_path):
                os.unlink(input_path)
            if os.path.exists(output_path):
                os.unlink(output_path)


if __name__ == '__main__':
    unittest.main()
