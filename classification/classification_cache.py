"""
Classification cache management for avoiding redundant AI classifications.

This module provides functionality to:
1. Hash the contents of classification/categories and classification/tags directories
2. Store classification hashes per PR/commit for each AI classifier type
3. Check if a PR/commit needs reclassification based on hash changes
"""

import os
import hashlib
import json
from typing import Dict, Optional, Set


def compute_classification_hash() -> str:
    """
    Compute a hash of the classification configuration (categories + tags).
    
    This hash changes whenever category or tag definitions are modified,
    indicating that previous classifications should be re-done.
    
    Returns:
        str: Hexadecimal hash string
    """
    hash_obj = hashlib.sha256()
    
    # Get the classification directory
    classification_dir = os.path.dirname(__file__)
    
    # Hash all category files
    categories_dir = os.path.join(classification_dir, "categories")
    if os.path.exists(categories_dir):
        for filename in sorted(os.listdir(categories_dir)):
            if filename.endswith(".txt"):
                filepath = os.path.join(categories_dir, filename)
                with open(filepath, 'rb') as f:
                    hash_obj.update(filename.encode('utf-8'))
                    hash_obj.update(f.read())
    
    # Hash all tag files
    tags_dir = os.path.join(classification_dir, "tags")
    if os.path.exists(tags_dir):
        for filename in sorted(os.listdir(tags_dir)):
            if filename.endswith(".txt"):
                filepath = os.path.join(tags_dir, filename)
                with open(filepath, 'rb') as f:
                    hash_obj.update(filename.encode('utf-8'))
                    hash_obj.update(f.read())
    
    return hash_obj.hexdigest()


class ClassificationCacheManager:
    """
    Manages classification cache for a specific AI classifier type.
    
    Stores which PR IDs or commit hashes have been classified with
    which classification configuration hash.
    """
    
    def __init__(self, classifier_type: str):
        """
        Initialize cache manager for a specific classifier type.
        
        Args:
            classifier_type: Type of classifier (e.g., 'gemini', 'gpt', 'claude')
        """
        self.classifier_type = classifier_type
        self.cache_dir = os.path.join(".cache", "agents")
        self.cache_file = os.path.join(self.cache_dir, f"{classifier_type}.json")
        self._cache: Dict[str, str] = {}
        self._load_cache()
    
    def _load_cache(self):
        """Load cache from disk."""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r') as f:
                    self._cache = json.load(f)
            except Exception as e:
                print(f"Warning: Could not load classification cache for {self.classifier_type}: {e}")
                self._cache = {}
        else:
            self._cache = {}
    
    def _save_cache(self):
        """Save cache to disk."""
        try:
            os.makedirs(self.cache_dir, exist_ok=True)
            with open(self.cache_file, 'w') as f:
                json.dump(self._cache, f, indent=2)
        except Exception as e:
            print(f"Warning: Could not save classification cache for {self.classifier_type}: {e}")
    
    def get_cached_hash(self, item_id: str) -> Optional[str]:
        """
        Get the classification hash for a specific item (PR ID or commit hash).
        
        Args:
            item_id: PR ID or commit hash
            
        Returns:
            Classification hash if cached, None otherwise
        """
        return self._cache.get(item_id)
    
    def set_cached_hash(self, item_id: str, classification_hash: str):
        """
        Store the classification hash for a specific item.
        
        Args:
            item_id: PR ID or commit hash
            classification_hash: Hash of classification configuration used
        """
        self._cache[item_id] = classification_hash
        self._save_cache()
    
    def needs_classification(self, item_id: str, current_hash: str, reclassify: bool = False) -> bool:
        """
        Check if an item needs (re)classification.
        
        Args:
            item_id: PR ID or commit hash
            current_hash: Current classification configuration hash
            reclassify: If True, always classify regardless of cache
            
        Returns:
            True if classification is needed, False otherwise
        """
        if reclassify:
            return True
        
        cached_hash = self.get_cached_hash(item_id)
        if cached_hash is None:
            return True
        
        return cached_hash != current_hash
    
    def clear_cache(self):
        """Clear all cached classification hashes."""
        self._cache = {}
        self._save_cache()
