import os
import requests
from abc import abstractmethod
from typing import Dict, Any, Optional
from classification.base_classifier import BaseClassifier


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
    
    def get_commit_diff(self, commit_sha: str) -> str:
        """
        Fetches the diff of a commit from GitHub.
        
        This is a concrete method shared by all AI classifiers.
        """
        url = f"https://api.github.com/repos/{self.owner}/{self.name}/commits/{commit_sha}"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github.v3.diff"
        }
        try:
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code == 200:
                return response.text[:10000]  # Truncate
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
            dict with 'sub_category' and 'error' keys
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
