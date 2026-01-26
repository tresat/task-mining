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
        self.original_cache_dir = os.path.join(".cache", "agents")
        
        # Patch the cache directory
        self.test_cache_dir = os.path.join(self.temp_dir, "agents")
        os.makedirs(self.test_cache_dir, exist_ok=True)
    
    def tearDown(self):
        """Clean up test fixtures."""
        # Remove temporary directory
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def test_cache_manager_initialization(self):
        """Test cache manager initialization."""
        # Temporarily patch the cache directory
        import classification.classification_cache as cache_module
        original_cache_dir = cache_module.ClassificationCacheManager.__init__
        
        # Create manager with test cache directory
        manager = ClassificationCacheManager("test_classifier")
        manager.cache_dir = self.test_cache_dir
        manager.cache_file = os.path.join(self.test_cache_dir, "test_classifier.json")
        
        self.assertEqual(manager.classifier_type, "test_classifier")
        self.assertIsInstance(manager._cache, dict)
    
    def test_set_and_get_cached_hash(self):
        """Test setting and getting cached hash."""
        manager = ClassificationCacheManager("test")
        manager.cache_dir = self.test_cache_dir
        manager.cache_file = os.path.join(self.test_cache_dir, "test.json")
        
        test_hash = "abc123def456"
        test_item_id = "test_pr_123"
        
        # Initially, should return None
        self.assertIsNone(manager.get_cached_hash(test_item_id))
        
        # Set the hash
        manager.set_cached_hash(test_item_id, test_hash)
        
        # Now should return the hash
        self.assertEqual(manager.get_cached_hash(test_item_id), test_hash)
    
    def test_needs_classification_no_cache(self):
        """Test needs_classification when item is not cached."""
        manager = ClassificationCacheManager("test")
        manager.cache_dir = self.test_cache_dir
        manager.cache_file = os.path.join(self.test_cache_dir, "test.json")
        
        # Should need classification when not cached
        self.assertTrue(manager.needs_classification("item1", "hash1"))
    
    def test_needs_classification_cached_same_hash(self):
        """Test needs_classification when cached with same hash."""
        manager = ClassificationCacheManager("test")
        manager.cache_dir = self.test_cache_dir
        manager.cache_file = os.path.join(self.test_cache_dir, "test.json")
        
        test_hash = "hash1"
        test_item = "item1"
        
        # Cache the item
        manager.set_cached_hash(test_item, test_hash)
        
        # Should not need classification with same hash
        self.assertFalse(manager.needs_classification(test_item, test_hash))
    
    def test_needs_classification_cached_different_hash(self):
        """Test needs_classification when cached with different hash."""
        manager = ClassificationCacheManager("test")
        manager.cache_dir = self.test_cache_dir
        manager.cache_file = os.path.join(self.test_cache_dir, "test.json")
        
        old_hash = "hash1"
        new_hash = "hash2"
        test_item = "item1"
        
        # Cache the item with old hash
        manager.set_cached_hash(test_item, old_hash)
        
        # Should need classification with different hash
        self.assertTrue(manager.needs_classification(test_item, new_hash))
    
    def test_needs_classification_with_reclassify_flag(self):
        """Test needs_classification with reclassify=True."""
        manager = ClassificationCacheManager("test")
        manager.cache_dir = self.test_cache_dir
        manager.cache_file = os.path.join(self.test_cache_dir, "test.json")
        
        test_hash = "hash1"
        test_item = "item1"
        
        # Cache the item
        manager.set_cached_hash(test_item, test_hash)
        
        # Should need classification when reclassify=True
        self.assertTrue(manager.needs_classification(test_item, test_hash, reclassify=True))
    
    def test_cache_persistence(self):
        """Test that cache is persisted to disk."""
        cache_file = os.path.join(self.test_cache_dir, "test.json")
        
        # Create manager and add item
        manager1 = ClassificationCacheManager("test")
        manager1.cache_dir = self.test_cache_dir
        manager1.cache_file = cache_file
        manager1.set_cached_hash("item1", "hash1")
        
        # Create new manager and verify it loads the cache
        manager2 = ClassificationCacheManager("test")
        manager2.cache_dir = self.test_cache_dir
        manager2.cache_file = cache_file
        manager2._load_cache()
        
        self.assertEqual(manager2.get_cached_hash("item1"), "hash1")
    
    def test_clear_cache(self):
        """Test clearing the cache."""
        manager = ClassificationCacheManager("test")
        manager.cache_dir = self.test_cache_dir
        manager.cache_file = os.path.join(self.test_cache_dir, "test.json")
        
        # Add some items
        manager.set_cached_hash("item1", "hash1")
        manager.set_cached_hash("item2", "hash2")
        
        # Clear cache
        manager.clear_cache()
        
        # Verify cache is empty
        self.assertIsNone(manager.get_cached_hash("item1"))
        self.assertIsNone(manager.get_cached_hash("item2"))


if __name__ == "__main__":
    unittest.main()
