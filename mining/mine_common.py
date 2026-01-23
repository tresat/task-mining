"""
Common utilities for mining scripts.
"""
import os
from typing import Optional

def load_env():
    """Simple .env loader to avoid external dependencies."""
    # Look for .env in the project root (parent of mining directory)
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()

def ensure_directory(directory: str) -> None:
    """
    Ensure a directory exists, creating it if necessary.
    
    Args:
        directory: Path to the directory
    """
    os.makedirs(directory, exist_ok=True)

def process_repo_list(repo_or_file: str) -> list:
    """
    Process either a single repository or a file containing a list of repositories.
    
    Args:
        repo_or_file: Either a repository string in 'owner/name' format or a file path
        
    Returns:
        List of repository strings
    """
    repos = []
    if os.path.isfile(repo_or_file):
        with open(repo_or_file, 'r') as f:
            repos = [line.strip() for line in f if line.strip() and not line.startswith("#")]
        print(f"Loaded {len(repos)} repositories from {repo_or_file}")
    else:
        repos = [repo_or_file]
    return repos
