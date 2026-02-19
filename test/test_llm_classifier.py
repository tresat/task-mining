import unittest
import json
import os
import sys
from unittest.mock import Mock, patch, MagicMock
import tempfile

# Add parent directory to path to import classification module
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from classification.llm_classifier import LLMClassifier


class TestLLMClassifier(unittest.TestCase):
    """Test the LLM classifier using LiteLLM."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.test_owner = "test_owner"
        self.test_name = "test_repo"
        self.test_github_token = "test_github_token"
        self.test_model = "gemini/gemini-2.0-flash"
        
        # Mock categories and tags directory/files if needed
        # But LLMClassifier loads them from the filesystem, so we might need to mock that logic 
        # or rely on existing files if they are present in the environment.
        
    def test_classifier_initialization(self):
        """Test that classifier initializes correctly."""
        classifier = LLMClassifier(
            self.test_github_token,
            self.test_model,
            self.test_owner,
            self.test_name
        )
        
        self.assertEqual(classifier.owner, self.test_owner)
        self.assertEqual(classifier.name, self.test_name)
        self.assertEqual(classifier.token, self.test_github_token)
        self.assertEqual(classifier.model, self.test_model)
        # cache_dir is .cache/agents/test_owner_test_repo
        self.assertIn("test_owner_test_repo", classifier.cache_manager.cache_dir)
        # cache_file is .cache/agents/test_owner_test_repo/llm_gemini_gemini-2.0-flash.json
        self.assertIn("llm_gemini_gemini-2.0-flash.json", classifier.cache_manager.cache_file)

    @patch('litellm.completion')
    def test_call_ai_api_success(self, mock_completion):
        """Test successful AI API call via LiteLLM."""
        classifier = LLMClassifier(
            self.test_github_token,
            self.test_model,
            self.test_owner,
            self.test_name
        )
        
        # Mock categories
        classifier.categories = {"Bug Fix": "Fixes a bug"}
        classifier.tags = {"tests": "Changes related to tests"}
        
        # Mock LiteLLM response
        mock_choice = MagicMock()
        mock_choice.message.content = """Category: Bug Fix
Tags: [tests]
Summary: Fixed a critical bug in the login flow."""
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_completion.return_value = mock_response
        
        result = classifier._call_ai_api("Fix login bug", "diff content")
        
        self.assertEqual(result["category"], "Bug Fix")
        self.assertEqual(result["tags"], ["tests"])
        self.assertEqual(result["summary"], "Fixed a critical bug in the login flow.")
        self.assertIsNone(result["error"])

    @patch('litellm.completion')
    def test_call_ai_api_failure(self, mock_completion):
        """Test LiteLLM API failure handling."""
        classifier = LLMClassifier(
            self.test_github_token,
            self.test_model,
            self.test_owner,
            self.test_name
        )
        classifier.categories = {"Other": "Other changes"}
        
        mock_completion.side_effect = Exception("API Key Error")
        
        result = classifier._call_ai_api("Message", "diff")
        
        self.assertEqual(result["category"], "Other")
        self.assertIn("LiteLLM error", result["error"])
        self.assertEqual(result["summary"], "Message")

    @patch('classification.llm_classifier.LLMClassifier.get_commit_diff')
    @patch('litellm.completion')
    def test_classify_pair(self, mock_completion, mock_get_diff):
        """Test classification of a single commit pair."""
        classifier = LLMClassifier(
            self.test_github_token,
            self.test_model,
            self.test_owner,
            self.test_name
        )
        classifier.categories = {"Feature": "New feature"}
        classifier.tags = {"ui": "UI changes"}
        
        mock_get_diff.return_value = "diff content"
        
        mock_choice = MagicMock()
        mock_choice.message.content = """Category: Feature
Tags: [ui]
Summary: Added a new button."""
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_completion.return_value = mock_response
        
        pair = {
            "to_commit": "abc123",
            "to_msg": "Add button",
            "tags": []
        }
        
        result = classifier.classify(pair)
        
        self.assertEqual(result["category"], "Feature")
        self.assertIn("ui", result["tags"])
        self.assertEqual(result["summary"], "Added a new button.")

    def test_one_line_tag_detection(self):
        """Test that 'one-line' tag is added for single line changes."""
        classifier = LLMClassifier(
            self.test_github_token,
            self.test_model,
            self.test_owner,
            self.test_name
        )
        classifier.categories = {"Other": "Other"}
        
        # Mock _call_ai_api to avoid actual LLM call
        classifier._call_ai_api = MagicMock(return_value={
            "category": "Other", 
            "tags": [], 
            "summary": "summary", 
            "error": None
        })
        
        # Single line change diff
        single_line_diff = """diff --git a/file b/file
-old
+new"""
        with patch('classification.llm_classifier.LLMClassifier.get_commit_diff', return_value=single_line_diff):
            pair = {"to_commit": "abc", "to_msg": "msg", "tags": []}
            result = classifier.classify(pair)
            self.assertIn("one-line", result["tags"])
        
        # Multi line change diff
        multi_line_diff = """diff --git a/file b/file
-old1
-old2
+new1
+new2"""
        with patch('classification.llm_classifier.LLMClassifier.get_commit_diff', return_value=multi_line_diff):
            pair = {"to_commit": "def", "to_msg": "msg", "tags": []}
            result = classifier.classify(pair)
            self.assertNotIn("one-line", result["tags"])

if __name__ == '__main__':
    unittest.main()
