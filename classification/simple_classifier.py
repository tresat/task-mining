import os
import json
import requests
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any
import sys
import re

# Add parent directory to path to import from mining
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from mining.mine_common import load_env

class SimpleClassifier:
    """
    Simple classifier that categorizes changes based on dependency file modifications.
    Only tags things as Dependency Changes vs. Others.
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

    def get_commit_diff(self, commit_sha: str) -> Dict[str, Any]:
        """Fetches the diff for a commit using REST API."""
        url = f"{self.api_url}/repos/{self.owner}/{self.name}/commits/{commit_sha}"
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            if response.status_code == 200:
                return response.json()
            else:
                print(f"Failed to fetch commit {commit_sha}: {response.status_code}")
                return {}
        except Exception as e:
            print(f"Error fetching commit {commit_sha}: {e}")
            return {}

    def check_dependencies_block(self, patch: str) -> bool:
        """
        Checks if changes occur within a dependencies {} block in build.gradle files.
        Returns True if changes are inside a dependencies block.
        """
        if not patch:
            return False
        
        # Look for lines that are added or removed (start with + or -)
        # and check if they appear after a "dependencies {" line
        lines = patch.split('\n')
        in_dependencies_block = False
        brace_count = 0
        has_dependency_changes = False
        
        for line in lines:
            stripped = line.strip()
            
            # Track dependencies block
            if re.match(r'dependencies\s*\{', stripped):
                in_dependencies_block = True
                brace_count = 1
                continue
            
            # Track braces within dependencies block
            if in_dependencies_block:
                brace_count += stripped.count('{')
                brace_count -= stripped.count('}')
                
                # Check if we're still in the dependencies block
                if brace_count <= 0:
                    in_dependencies_block = False
                    continue
                
                # Check for actual changes (additions or removals)
                if line.startswith('+') or line.startswith('-'):
                    # Ignore diff metadata lines
                    if not line.startswith('+++') and not line.startswith('---'):
                        has_dependency_changes = True
        
        return has_dependency_changes

    def classify_pair(self, pair: Dict[str, Any]) -> Dict[str, Any]:
        """
        Classifies a pair based on changed files.
        
        Rules:
        1. If ONLY libs.versions.toml was changed -> Category = "Dependency Update"
        2. If any dependency-related file was changed -> add "dependencies" tag
        3. Dependencies files include:
           - libs.versions.toml
           - changes within dependencies {} block in build.gradle or build.gradle.kts
        """
        to_commit = pair.get("to_commit") or pair.get("good_commit")  # Support both formats for backward compatibility
        
        # Fetch the full commit diff
        commit_data = self.get_commit_diff(to_commit)
        files = commit_data.get("files", [])
        
        # Initialize tags as empty list
        tags = []
        category = None
        
        # Track what types of changes we found
        libs_versions_changed = False
        gradle_dependencies_changed = False
        other_files_changed = False
        
        for file_obj in files:
            filename = file_obj.get("filename", "")
            patch = file_obj.get("patch", "")
            
            if "libs.versions.toml" in filename:
                libs_versions_changed = True
            elif filename.endswith("build.gradle") or filename.endswith("build.gradle.kts"):
                # Check if changes are within dependencies {} block
                if self.check_dependencies_block(patch):
                    gradle_dependencies_changed = True
                else:
                    other_files_changed = True
            else:
                other_files_changed = True
        
        # Apply classification rules
        has_dependency_changes = libs_versions_changed or gradle_dependencies_changed
        
        if has_dependency_changes:
            tags.append("dependencies")
        
        # Only set category to "Dependency Update" if ONLY libs.versions.toml changed
        if libs_versions_changed and not gradle_dependencies_changed and not other_files_changed:
            category = "Dependency Update"
        
        # Update pair with classification results
        pair["category"] = category
        pair["tags"] = tags
        
        return pair

    def analyze(self, input_file: str):
        """Analyzes pairs in-place, updating the category and tags fields."""
        with open(input_file, 'r') as f:
            pairs = json.load(f)
            
        print(f"Analyzing {len(pairs)} pairs...")
        
        analyzed_pairs = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_pair = {executor.submit(self.classify_pair, pair): pair for pair in pairs}
            
            for future in as_completed(future_to_pair):
                try:
                    result = future.result()
                    analyzed_pairs.append(result)
                    to_commit = result.get('to_commit') or result.get('good_commit')
                    category = result.get('category', 'None')
                    tags = result.get('tags', [])
                    print(f"Analyzed {to_commit[:7]} -> Category: {category}, Tags: {tags}")
                except Exception as e:
                    print(f"Analysis failed for a pair: {e}")
                    
        # Write back to the same file (in-place edit)
        with open(input_file, 'w') as f:
            json.dump(analyzed_pairs, f, indent=2)
        print(f"Updated {input_file} with category and tags classifications")

def main():
    load_env()
    parser = argparse.ArgumentParser(
        description="Simple Classifier - Categorizes changes based on dependency file modifications"
    )
    parser.add_argument("repo", help="owner/name")
    parser.add_argument("--input", help="Input file path (default: results/per_repo/{owner}_{name}.json)")
    
    args = parser.parse_args()
    
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("Error: GITHUB_TOKEN not set.")
        return
        
    owner, name = args.repo.split("/", 1)
    
    # Use per_repo structure if input not specified
    if args.input:
        input_file = args.input
    else:
        input_file = os.path.join("results", "per_repo", f"{owner}_{name}.json")
    
    if not os.path.exists(input_file):
        print(f"Error: Input file {input_file} not found.")
        return
    
    classifier = SimpleClassifier(token, owner, name)
    classifier.analyze(input_file)

if __name__ == "__main__":
    main()
