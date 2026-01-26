"""
Tests for the classification cache functionality.
"""

import unittest
import os
import sys
import json
import tempfile
import shutil

# Add parent directory to path to import classification module
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from classification.classification_cache import (
    compute_classification_hash,
    ClassificationCacheManager
)


class TestClassificationHash(unittest.TestCase):
    """Test classification hash computation."""
    
    def test_compute_classification_hash(self):
        """Test that hash computation returns a valid hash string."""
        hash_value = compute_classification_hash()
        
        # Hash should be a hex string of 64 characters (SHA-256)
        self.assertIsInstance(hash_value, str)
        self.assertEqual(len(hash_value), 64)
        self.assertTrue(all(c in '0123456789abcdef' for c in hash_value))
    
    def test_hash_is_consistent(self):
        """Test that hash is consistent for same content."""
        hash1 = compute_classification_hash()
        hash2 = compute_classification_hash()
        
        self.assertEqual(hash1, hash2)


class TestClassificationCacheManager(unittest.TestCase):
    """Test the ClassificationCacheManager class."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Create a temporary directory for cache
        self.temp_dir = tempfile.mkdtemp()
        self.test_owner = "test_owner"
        self.test_repo = "test_repo"
        self.test_cache_dir = os.path.join(self.temp_dir, "agents", f"{self.test_owner}_{self.test_repo}")
    
    def tearDown(self):
        """Clean up test fixtures."""
        # Remove temporary directory
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def test_cache_manager_initialization(self):
        """Test cache manager initialization."""
        manager = ClassificationCacheManager("test_classifier", self.test_owner, self.test_repo)
        manager.cache_dir = self.test_cache_dir
        manager.cache_file = os.path.join(self.test_cache_dir, "test_classifier.json")
        
        self.assertEqual(manager.classifier_type, "test_classifier")
        self.assertEqual(manager.repo_owner, self.test_owner)
        self.assertEqual(manager.repo_name, self.test_repo)
        self.assertIsInstance(manager._cache, dict)
        self.assertIn("classification_hash", manager._cache)
        self.assertIn("classifications", manager._cache)
    
    def test_check_and_update_hash(self):
        """Test checking and updating hash."""
        manager = ClassificationCacheManager("test", self.test_owner, self.test_repo)
        manager.cache_dir = self.test_cache_dir
        manager.cache_file = os.path.join(self.test_cache_dir, "test.json")
        
        test_hash = "abc123def456"
        
        # First time - hash should be updated
        changed = manager.check_and_update_hash(test_hash)
        self.assertTrue(changed)
        self.assertEqual(manager._cache["classification_hash"], test_hash)
        
        # Second time with same hash - no change
        changed = manager.check_and_update_hash(test_hash)
        self.assertFalse(changed)
        
        # Different hash - should change
        new_hash = "different_hash"
        changed = manager.check_and_update_hash(new_hash)
        self.assertTrue(changed)
        self.assertEqual(manager._cache["classification_hash"], new_hash)
        # Classifications should be cleared
        self.assertEqual(len(manager._cache["classifications"]), 0)
    
    def test_set_and_get_cached_result(self):
        """Test setting and getting cached results."""
        manager = ClassificationCacheManager("test", self.test_owner, self.test_repo)
        manager.cache_dir = self.test_cache_dir
        manager.cache_file = os.path.join(self.test_cache_dir, "test.json")
        
        test_item_id = "test_pr_123"
        test_category = "Feature"
        test_tags = ["documentation", "tests"]
        test_error = None
        
        # Initially, should return None
        self.assertIsNone(manager.get_cached_result(test_item_id))
        
        # Set the result
        manager.set_cached_result(test_item_id, test_category, test_tags, test_error)
        
        # Now should return the result
        result = manager.get_cached_result(test_item_id)
        self.assertIsNotNone(result)
        self.assertEqual(result["category"], test_category)
        self.assertEqual(result["tags"], test_tags)
        self.assertEqual(result["error"], test_error)
    
    def test_cache_persistence(self):
        """Test that cache is persisted to disk."""
        cache_file = os.path.join(self.test_cache_dir, "test.json")
        
        # Create manager and add item
        manager1 = ClassificationCacheManager("test", self.test_owner, self.test_repo)
        manager1.cache_dir = self.test_cache_dir
        manager1.cache_file = cache_file
        manager1.set_cached_result("item1", "Bug Fix", ["tests"], None)
        
        # Create new manager and verify it loads the cache
        manager2 = ClassificationCacheManager("test", self.test_owner, self.test_repo)
        manager2.cache_dir = self.test_cache_dir
        manager2.cache_file = cache_file
        manager2._load_cache()
        
        result = manager2.get_cached_result("item1")
        self.assertIsNotNone(result)
        self.assertEqual(result["category"], "Bug Fix")
        self.assertEqual(result["tags"], ["tests"])
    
    def test_clear_cache(self):
        """Test clearing the cache."""
        manager = ClassificationCacheManager("test", self.test_owner, self.test_repo)
        manager.cache_dir = self.test_cache_dir
        manager.cache_file = os.path.join(self.test_cache_dir, "test.json")
        
        # Add some items and set hash
        test_hash = "abc123"
        manager.check_and_update_hash(test_hash)
        manager.set_cached_result("item1", "Feature", [], None)
        manager.set_cached_result("item2", "Bug Fix", [], None)
        
        # Clear cache
        manager.clear_cache()
        
        # Verify classifications are empty but hash remains
        self.assertIsNone(manager.get_cached_result("item1"))
        self.assertIsNone(manager.get_cached_result("item2"))
        self.assertEqual(manager._cache["classification_hash"], test_hash)
    
    def test_hash_change_clears_classifications(self):
        """Test that changing hash clears all classifications."""
        manager = ClassificationCacheManager("test", self.test_owner, self.test_repo)
        manager.cache_dir = self.test_cache_dir
        manager.cache_file = os.path.join(self.test_cache_dir, "test.json")
        
        # Set initial hash and add classifications
        hash1 = "hash1"
        manager.check_and_update_hash(hash1)
        manager.set_cached_result("item1", "Feature", [], None)
        manager.set_cached_result("item2", "Bug Fix", [], None)
        
        # Verify items exist
        self.assertIsNotNone(manager.get_cached_result("item1"))
        self.assertIsNotNone(manager.get_cached_result("item2"))
        
        # Change hash
        hash2 = "hash2"
        changed = manager.check_and_update_hash(hash2)
        self.assertTrue(changed)
        
        # Verify classifications were cleared
        self.assertIsNone(manager.get_cached_result("item1"))
        self.assertIsNone(manager.get_cached_result("item2"))


if __name__ == "__main__":
    unittest.main()
