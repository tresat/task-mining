from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import re


class BaseClassifier(ABC):
    """
    Abstract base class for all classifiers.
    
    Provides common functionality:
    - is_single_line_change() - concrete implementation available to all classifiers
    
    Requires subclasses to implement:
    - check_dependencies() - for checking if change is dependency-related
    - check_version_update() - for checking if change is version update
    - classify() - main classification method
    """
    
    def __init__(self, token: str, repo_owner: str, repo_name: str):
        self.token = token
        self.owner = repo_owner
        self.name = repo_name
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json"
        }
        self.api_url = "https://api.github.com"
    
    def is_single_line_change(self, commit_diff: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Checks if the commit changes only a single line in a dependency file.
        Returns the file info if valid, None otherwise.
        
        This is a concrete method available to ALL classifiers.
        """
        files = commit_diff.get("files", [])
        
        # Must have exactly one file changed
        if len(files) != 1:
            return None
        
        file = files[0]
        filename = file.get("filename", "")
        
        # Check if it's a dependency file
        valid_files = ["build.gradle", "build.gradle.kts", "libs.versions.toml"]
        if not any(filename.endswith(vf) for vf in valid_files):
            return None
        
        # Count actual changed lines by parsing the patch
        patch = file.get("patch", "")
        if not patch:
            return None
        
        # Count lines that start with + or - (excluding +++ and ---)
        added_lines = 0
        removed_lines = 0
        for line in patch.split('\n'):
            if line.startswith('+') and not line.startswith('+++'):
                added_lines += 1
            elif line.startswith('-') and not line.startswith('---'):
                removed_lines += 1
        
        # Single line change means exactly 1 addition and 1 deletion
        if added_lines != 1 or removed_lines != 1:
            return None
        
        return file
    
    @abstractmethod
    def check_dependencies(self, pair: Dict[str, Any]) -> bool:
        """
        Check if the change is dependency-related.
        
        Args:
            pair: The commit pair to check
            
        Returns:
            True if the change is dependency-related, False otherwise
        """
        pass
    
    @abstractmethod
    def check_version_update(self, pair: Dict[str, Any], file_info: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Check if the change is a version update.
        
        Args:
            pair: The commit pair to check
            file_info: File information from is_single_line_change()
            
        Returns:
            Version change information if valid, None otherwise
        """
        pass
    
    @abstractmethod
    def classify(self, pair: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main classification method that must be implemented by all classifiers.
        
        Args:
            pair: The commit pair to classify
            
        Returns:
            The classified pair with updated category and tags
        """
        pass
