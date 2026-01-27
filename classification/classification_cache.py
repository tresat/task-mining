"""
Classification cache management for avoiding redundant AI classifications.

This module provides functionality to:
1. Hash the contents of classification/categories and classification/tags directories
2. Store classification results per PR/commit per repo for each AI classifier type
3. Automatically invalidate cache when classification configuration changes
"""

import os
import hashlib
import json
from typing import Dict, Optional, Any


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
    Manages classification cache for a specific AI classifier type and repository.
    
    Cache structure:
    {
        "classification_hash": "abc123...",
        "classifications": {
            "item_id": {
                "category": "Feature",
                "tags": ["documentation"],
                "error": null
            }
        }
    }
    """
    
    def __init__(self, classifier_type: str, repo_owner: str, repo_name: str):
        """
        Initialize cache manager for a specific classifier type and repository.
        
        Args:
            classifier_type: Type of classifier (e.g., 'gemini', 'gpt', 'claude')
            repo_owner: Repository owner
            repo_name: Repository name
        """
        self.classifier_type = classifier_type
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.repo_key = f"{repo_owner}_{repo_name}"
        
        # Cache directory per repo
        self.cache_dir = os.path.join(".cache", "agents", self.repo_key)
        self.cache_file = os.path.join(self.cache_dir, f"{classifier_type}.json")
        
        # Cache structure: {"classification_hash": str, "classifications": dict}
        self._cache: Dict[str, Any] = {
            "classification_hash": None,
            "classifications": {}
        }
        self._load_cache()
    
    def _load_cache(self):
        """Load cache from disk."""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r') as f:
                    self._cache = json.load(f)
                    # Ensure structure
                    if "classification_hash" not in self._cache:
                        self._cache["classification_hash"] = None
                    if "classifications" not in self._cache:
                        self._cache["classifications"] = {}
            except Exception as e:
                print(f"Warning: Could not load classification cache for {self.classifier_type}: {e}")
                self._cache = {
                    "classification_hash": None,
                    "classifications": {}
                }
        else:
            self._cache = {
                "classification_hash": None,
                "classifications": {}
            }
    
    def _save_cache(self):
        """Save cache to disk."""
        try:
            os.makedirs(self.cache_dir, exist_ok=True)
            with open(self.cache_file, 'w') as f:
                json.dump(self._cache, f, indent=2)
        except Exception as e:
            print(f"Warning: Could not save classification cache for {self.classifier_type}: {e}")
    
    def check_and_update_hash(self, current_hash: str) -> bool:
        """
        Check if classification hash has changed and update cache if needed.
        If hash changed, clears all cached classifications.
        
        Args:
            current_hash: Current classification configuration hash
            
        Returns:
            True if hash changed (cache was cleared), False otherwise
        """
        cached_hash = self._cache.get("classification_hash")
        
        if cached_hash != current_hash:
            # Hash changed, clear all classifications
            self._cache["classification_hash"] = current_hash
            self._cache["classifications"] = {}
            self._save_cache()
            return True
        
        return False
    
    def get_cached_result(self, item_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the cached classification result for a specific item.
        
        Args:
            item_id: PR ID or commit hash
            
        Returns:
            Classification result dict if cached, None otherwise
        """
        return self._cache["classifications"].get(item_id)
    
    def set_cached_result(self, item_id: str, category: str, tags: list, summary: Optional[str], error: Optional[str]):
        """
        Store the classification result for a specific item.
        
        Args:
            item_id: PR ID or commit hash
            category: Classification category
            tags: List of tags
            summary: Summary text (for AI classifiers)
            error: Error message if classification failed, None otherwise
        """
        self._cache["classifications"][item_id] = {
            "category": category,
            "tags": tags,
            "summary": summary,
            "error": error
        }
        self._save_cache()
    
    def clear_cache(self):
        """Clear all cached classifications but keep the hash."""
        self._cache["classifications"] = {}
        self._save_cache()
