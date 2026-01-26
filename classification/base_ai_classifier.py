import os
import requests
from abc import abstractmethod
from typing import Dict, Any, Optional
from classification.base_classifier import BaseClassifier

# Maximum characters to fetch from commit diff (to avoid excessive API response sizes)
COMMIT_DIFF_MAX_LENGTH = 10000


class BaseAIClassifier(BaseClassifier):
    """
    Abstract base class for AI-powered classifiers (Gemini, GPT).
    
    Provides common functionality:
    - _load_categories() - loads category definitions from files
    - get_commit_diff() - fetches commit diff from GitHub
    - check_dependencies() - uses AI API to determine if dependency-related
    - check_version_update() - uses AI API to determine if version update
    
    Requires subclasses to implement:
    - _call_ai_api() - for making the actual AI API call (differs per provider)
    - classify() - main classification method
    """
    
    def __init__(self, github_token: str, api_key: str, repo_owner: str, repo_name: str):
        super().__init__(github_token, repo_owner, repo_name)
        self.api_key = api_key
        self.categories = self._load_categories()
        self.tags = self._load_tags()
        # Per-repo cache directory for commit diffs
        self.commit_diff_cache_dir = os.path.join(".cache", f"{self.owner}_{self.name}", "commit_contents")
    
    def _load_categories(self) -> Dict[str, str]:
        """
        Loads category definitions from .txt files in classification/categories/.
        
        This is a concrete method shared by all AI classifiers.
        """
        categories = {}
        categories_dir = os.path.join(os.path.dirname(__file__), "categories")
        
        if not os.path.exists(categories_dir):
            print(f"Warning: Categories directory not found at {categories_dir}")
            return categories
        
        try:
            for filename in os.listdir(categories_dir):
                if filename.endswith(".txt"):
                    category_name = filename[:-4]  # Remove .txt extension
                    filepath = os.path.join(categories_dir, filename)
                    try:
                        with open(filepath, 'r') as f:
                            description = f.read().strip()
                            # Validate description: limit length
                            if len(description) > 500:
                                print(f"Warning: Description in {filename} exceeds 500 characters, truncating")
                                description = description[:500]
                            categories[category_name] = description
                    except Exception as e:
                        print(f"Warning: Could not read category file {filename}: {e}")
        except Exception as e:
            print(f"Warning: Error reading categories directory: {e}")
        
        return categories
    
    def _load_tags(self) -> Dict[str, str]:
        """
        Loads tag definitions from .txt files in classification/tags/.
        
        This is a concrete method shared by all AI classifiers.
        """
        tags = {}
        tags_dir = os.path.join(os.path.dirname(__file__), "tags")
        
        if not os.path.exists(tags_dir):
            print(f"Warning: Tags directory not found at {tags_dir}")
            return tags
        
        try:
            for filename in os.listdir(tags_dir):
                if filename.endswith(".txt"):
                    tag_name = filename[:-4]  # Remove .txt extension
                    filepath = os.path.join(tags_dir, filename)
                    try:
                        with open(filepath, 'r') as f:
                            description = f.read().strip()
                            # Validate description: limit length
                            if len(description) > 500:
                                print(f"Warning: Description in {filename} exceeds 500 characters, truncating")
                                description = description[:500]
                            tags[tag_name] = description
                    except Exception as e:
                        print(f"Warning: Could not read tag file {filename}: {e}")
        except Exception as e:
            print(f"Warning: Error reading tags directory: {e}")
        
        return tags
    
    def get_commit_diff(self, commit_sha: str) -> str:
        """
        Fetches the diff of a commit from GitHub.
        
        This method uses caching to avoid redundant API calls.
        Cache location: .cache/{owner}_{name}/commit_contents/{commit_sha}.txt
        
        This is a concrete method shared by all AI classifiers.
        """
        # Validate commit_sha to prevent path traversal attacks
        # Git commit SHAs are 40 hexadecimal characters (or 7+ for short form)
        if not commit_sha or not all(c in '0123456789abcdefABCDEF' for c in commit_sha):
            print(f"Invalid commit SHA format: {commit_sha}")
            return ""
        
        # Define cache path
        cache_file = os.path.join(self.commit_diff_cache_dir, f"{commit_sha}.txt")
        
        # Check if diff exists in cache
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    diff_content = f.read()
                print(f"Using cached diff for {commit_sha}")
                return diff_content
            except Exception as e:
                print(f"Error reading cached diff for {commit_sha}: {e}")
                # Fall through to fetch from API
        
        # Fetch from GitHub API
        url = f"https://api.github.com/repos/{self.owner}/{self.name}/commits/{commit_sha}"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github.v3.diff"
        }
        try:
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code == 200:
                diff_content = response.text[:COMMIT_DIFF_MAX_LENGTH]  # Truncate
                
                # Save to cache
                try:
                    os.makedirs(self.commit_diff_cache_dir, exist_ok=True)
                    with open(cache_file, 'w', encoding='utf-8') as f:
                        f.write(diff_content)
                    print(f"Cached diff for {commit_sha}")
                except Exception as e:
                    print(f"Warning: Could not cache diff for {commit_sha}: {e}")
                
                return diff_content
            else:
                print(f"Failed to fetch diff for {commit_sha}: {response.status_code}")
                return ""
        except Exception as e:
            print(f"Error fetching diff for {commit_sha}: {e}")
            return ""
    
    @abstractmethod
    def _call_ai_api(self, message: str, diff: str) -> dict:
        """
        Make the actual AI API call (implementation differs per provider).
        
        Args:
            message: Commit message
            diff: Commit diff
            
        Returns:
            dict with 'category', 'tags', and 'error' keys
        """
        pass
    
    def check_dependencies(self, pair: Dict[str, Any]) -> bool:
        """
        Uses AI API to determine if the change is dependency-related.
        
        For AI classifiers, this delegates to the AI API call.
        """
        # For AI classifiers, this is handled in the classify method
        # by adding tags based on AI response
        return False
    
    def check_version_update(self, pair: Dict[str, Any], file_info: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Uses AI API to determine if the change is a version update.
        
        For AI classifiers, this is handled in the classify method
        by adding tags based on AI response.
        """
        # For AI classifiers, this is handled in the classify method
        # by adding tags based on AI response
        return None
