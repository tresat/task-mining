"""
GitHub API Caching System

This module provides a comprehensive caching system for GitHub API responses.
Cache structure: .cache/{owner}_{name}/ with prs_cache.json and commits_cache.json
"""
import os
import json
from typing import Dict, List, Any, Optional

# Cache configuration constants
MAX_CACHE_ITEMS = 100  # Maximum number of items to cache per repository
PR_BATCH_SIZE = 50     # Number of PRs to fetch per batch when priming
COMMIT_BATCH_SIZE = 100  # Number of commits to fetch per batch when priming


class CacheManager:
    """Manages caching of GitHub API responses for a specific repository."""
    
    def __init__(self, owner: str, name: str, cache_type: str):
        """
        Initialize cache manager for a repository.
        
        Args:
            owner: Repository owner
            name: Repository name
            cache_type: Type of cache ('prs' or 'commits')
        """
        self.owner = owner
        self.name = name
        self.cache_type = cache_type
        
        # Cache directory structure: .cache/{owner}_{name}/
        self.cache_dir = os.path.join(".cache", f"{owner}_{name}")
        
        # Cache file based on type
        if cache_type == "prs":
            self.cache_file = os.path.join(self.cache_dir, "prs_cache.json")
        elif cache_type == "commits":
            self.cache_file = os.path.join(self.cache_dir, "commits_cache.json")
        else:
            raise ValueError(f"Invalid cache type: {cache_type}. Must be 'prs' or 'commits'.")
        
        # Initialize cache storage
        self._cache: Dict[str, Any] = {}
        self._load_cache()
    
    def _load_cache(self):
        """Load cache from disk if it exists."""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r') as f:
                    self._cache = json.load(f)
            except Exception as e:
                print(f"Warning: Could not load cache from {self.cache_file}: {e}")
                self._cache = {}
        else:
            self._cache = {}
    
    def _save_cache(self):
        """Save cache to disk."""
        os.makedirs(self.cache_dir, exist_ok=True)
        try:
            with open(self.cache_file, 'w') as f:
                json.dump(self._cache, f, indent=2)
        except Exception as e:
            print(f"Warning: Could not save cache to {self.cache_file}: {e}")
    
    def get(self, item_id: str) -> Optional[Any]:
        """
        Get an item from cache by ID.
        
        Args:
            item_id: ID of the item (PR number or commit SHA)
            
        Returns:
            Cached item data or None if not found
        """
        return self._cache.get(str(item_id))
    
    def set(self, item_id: str, data: Any):
        """
        Store an item in cache.
        
        Args:
            item_id: ID of the item (PR number or commit SHA)
            data: Data to cache
        """
        self._cache[str(item_id)] = data
        self._save_cache()
    
    def has(self, item_id: str) -> bool:
        """
        Check if an item exists in cache.
        
        Args:
            item_id: ID of the item (PR number or commit SHA)
            
        Returns:
            True if item is cached, False otherwise
        """
        return str(item_id) in self._cache
    
    def size(self) -> int:
        """
        Get the number of items in cache.
        
        Returns:
            Number of cached items
        """
        return len(self._cache)
    
    def get_all(self) -> Dict[str, Any]:
        """
        Get all cached items.
        
        Returns:
            Dictionary of all cached items
        """
        return self._cache.copy()
    
    def clear(self):
        """Clear all cached items."""
        self._cache = {}
        if os.path.exists(self.cache_file):
            os.remove(self.cache_file)
    
    @staticmethod
    def clear_all_caches():
        """Clear all caches for all repositories."""
        cache_root = ".cache"
        if os.path.exists(cache_root):
            import shutil
            shutil.rmtree(cache_root)
            print(f"Cleared all caches from {cache_root}/")


def prime_pr_cache(miner, cache_manager: CacheManager, max_items: int = MAX_CACHE_ITEMS):
    """
    Prime the PR cache by fetching recent PRs from GitHub.
    
    Fetches PRs from most recent to least recent. Stops when:
    1. Finding a PR already in cache, OR
    2. Reaching max_items in cache
    
    Args:
        miner: GitHubMiner instance
        cache_manager: CacheManager instance for PRs
        max_items: Maximum number of items to cache (default: MAX_CACHE_ITEMS)
    """
    print(f"Priming PR cache for {miner.owner}/{miner.name}...")
    
    initial_size = cache_manager.size()
    print(f"Cache contains {initial_size} PRs")
    
    if initial_size >= max_items:
        print(f"Cache already contains {initial_size} PRs (>= {max_items}), skipping priming")
        return
    
    # Import the PR query from mine_prs
    from .mine_prs import PR_QUERY
    
    cursor = None
    items_fetched = 0
    
    while cache_manager.size() < max_items:
        batch_size = min(PR_BATCH_SIZE, max_items - cache_manager.size())
        
        variables = {
            "owner": miner.owner,
            "name": miner.name,
            "cursor": cursor,
            "limit": batch_size
        }
        
        print(f"Fetching PR list from GitHub (cursor={cursor})...")
        data = miner._query(PR_QUERY, variables)
        
        if not data.get("data") or not data["data"].get("repository"):
            print("No data returned or repository not found.")
            break
        
        prs = data["data"]["repository"]["pullRequests"]
        nodes = prs["nodes"]
        
        if not nodes:
            print("No more PRs found.")
            break
        
        # Check each PR
        found_cached = False
        for pr_node in nodes:
            pr_number = str(pr_node["number"])
            
            # If already cached, stop priming
            if cache_manager.has(pr_number):
                print(f"Found PR #{pr_number} already in cache, stopping priming")
                found_cached = True
                break
            
            # Fetch full PR details (with all commits)
            print(f"Fetching PR #{pr_number} details from GitHub...")
            full_commits = miner.get_all_commits_for_pr(pr_node)
            
            # Store PR with full commit details
            pr_data = pr_node.copy()
            pr_data["commits"]["nodes"] = full_commits
            cache_manager.set(pr_number, pr_data)
            items_fetched += 1
            
            if cache_manager.size() >= max_items:
                print(f"Reached cache limit of {max_items} PRs")
                break
        
        if found_cached or cache_manager.size() >= max_items:
            break
        
        if not prs["pageInfo"]["hasNextPage"]:
            print("Reached end of PRs.")
            break
        
        cursor = prs["pageInfo"]["endCursor"]
    
    final_size = cache_manager.size()
    print(f"Cache priming complete: {items_fetched} new PRs cached ({initial_size} -> {final_size})")


def prime_commit_cache(miner, cache_manager: CacheManager, ref: str, max_items: int = MAX_CACHE_ITEMS):
    """
    Prime the commit cache by fetching recent commits from GitHub.
    
    Fetches commits from most recent to least recent. Stops when:
    1. Finding a commit already in cache, OR
    2. Reaching max_items in cache
    
    Args:
        miner: SimpleDependencyMiner instance
        cache_manager: CacheManager instance for commits
        ref: Git ref to scan
        max_items: Maximum number of items to cache (default: MAX_CACHE_ITEMS)
    """
    print(f"Priming commit cache for {miner.owner}/{miner.name}...")
    
    initial_size = cache_manager.size()
    print(f"Cache contains {initial_size} commits")
    
    if initial_size >= max_items:
        print(f"Cache already contains {initial_size} commits (>= {max_items}), skipping priming")
        return
    
    # Import the commits query from mine_dep_update_commits
    from .mine_dep_update_commits import COMMITS_QUERY
    
    cursor = None
    items_fetched = 0
    
    while cache_manager.size() < max_items:
        batch_size = min(COMMIT_BATCH_SIZE, max_items - cache_manager.size())
        
        variables = {
            "owner": miner.owner,
            "name": miner.name,
            "ref": ref,
            "cursor": cursor,
            "limit": batch_size
        }
        
        print(f"Fetching commit list from GitHub (cursor={cursor})...")
        data = miner._query(COMMITS_QUERY, variables)
        
        if not data.get("data") or not data["data"].get("repository"):
            print("No data returned or repository not found.")
            break
        
        ref_data = data["data"]["repository"].get("ref")
        if not ref_data or not ref_data.get("target"):
            print(f"Branch/ref '{ref}' not found.")
            break
        
        history = ref_data["target"]["history"]
        nodes = history["nodes"]
        
        if not nodes:
            print("No more commits found.")
            break
        
        # Check each commit
        found_cached = False
        for commit_node in nodes:
            oid = commit_node["oid"]
            
            # If already cached, stop priming
            if cache_manager.has(oid):
                print(f"Found commit {oid[:7]} already in cache, stopping priming")
                found_cached = True
                break
            
            # Store commit data
            cache_manager.set(oid, commit_node)
            items_fetched += 1
            
            if cache_manager.size() >= max_items:
                print(f"Reached cache limit of {max_items} commits")
                break
        
        if found_cached or cache_manager.size() >= max_items:
            break
        
        if not history["pageInfo"]["hasNextPage"]:
            print("Reached end of commits.")
            break
        
        cursor = history["pageInfo"]["endCursor"]
    
    final_size = cache_manager.size()
    print(f"Cache priming complete: {items_fetched} new commits cached ({initial_size} -> {final_size})")
