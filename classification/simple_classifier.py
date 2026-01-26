import os
import json
import requests
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional
import sys
import re

# Add parent directory to path to import from mining
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from mining.mine_common import load_env
from classification.base_classifier import BaseClassifier

class SimpleClassifier(BaseClassifier):
    """
    Simple classifier that categorizes changes based on dependency file modifications.
    Only tags things as Dependency Changes vs. Others.
    """
    def __init__(self, token: str, repo_owner: str, repo_name: str):
        super().__init__(token, repo_owner, repo_name)

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


    def _is_content_line(self, line: str) -> bool:
        """
        Check if a patch line is a content line (not a special marker).
        
        Returns True for context lines and False for special markers like:
        - \\ No newline at end of file
        - --- file headers
        - +++ file headers
        """
        return not line.startswith('\\') and not line.startswith('---') and not line.startswith('+++')

    def extract_version_change(self, patch: str) -> Optional[Dict[str, Any]]:
        """
        Extracts the line change and checks if it's a version increase.
        Returns dict with line info if valid, None otherwise.
        """
        lines = patch.split('\n')
        
        removed_line = None
        added_line = None
        added_line_number = 0
        
        # Parse the patch to find the changed line
        current_line = 0
        for line in lines:
            if line.startswith('@@'):
                # Parse hunk header to get line number
                # Format: @@ -old_start,old_count +new_start,new_count @@
                match = re.search(r'@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@', line)
                if match:
                    current_line = int(match.group(1))
            elif line.startswith('-') and not line.startswith('---'):
                removed_line = line[1:]  # Remove the '-' prefix
            elif line.startswith('+') and not line.startswith('+++'):
                added_line = line[1:]  # Remove the '+' prefix
                added_line_number = current_line
                current_line += 1
            elif self._is_content_line(line):
                current_line += 1
        
        if not removed_line or not added_line:
            return None
        
        # Try to extract version numbers from both lines
        from_version = self._extract_version(removed_line)
        to_version = self._extract_version(added_line)
        
        if not from_version or not to_version:
            return None
        
        # Check if version increased
        if not self._is_version_increase(from_version, to_version):
            return None
        
        return {
            "line_number": added_line_number,
            "from_line": removed_line,
            "to_line": added_line,
            "from_version": from_version,
            "to_version": to_version
        }

    def _extract_version(self, line: str) -> Optional[str]:
        """
        Extract version string from a line.
        
        Supports common version patterns in gradle and toml files:
        - Quoted versions: "1.2.3" or '1.2.3'
        - Colon-prefixed versions: :1.2.3"
        - Assignment versions: = 1.2.3
        
        Examples:
        - implementation("com.example:lib:1.2.3")
        - version = "2.0.0"
        - someLib = '1.5.2-alpha'
        - androidxCore = "1.10.0"
        """
        patterns = [
            # Matches "1.2.3" or '1.2.3' (with quotes)
            r'["\'](\d+\.\d+(?:\.\d+)?(?:[.-][a-zA-Z0-9]+)?)["\']',
            # Matches :1.2.3" (colon prefix with quote)
            r':(\d+\.\d+(?:\.\d+)?(?:[.-][a-zA-Z0-9]+)?)["\']',
            # Matches = 1.2.3 (assignment without quotes)
            r'=\s*(\d+\.\d+(?:\.\d+)?(?:[.-][a-zA-Z0-9]+)?)(?:\s|$)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, line)
            if match:
                return match.group(1)
        
        return None

    def _is_version_increase(self, from_version: str, to_version: str) -> bool:
        """
        Check if to_version is greater than from_version.
        
        Uses simple numeric comparison for the main version parts.
        Handles versions with different lengths and pre-release identifiers.
        
        Note: This is a simplified version comparison. For more complex
        scenarios, consider using packaging.version.parse().
        """
        def parse_version(v: str) -> list:
            """Parse version string into list of comparable parts."""
            # Split on dots and dashes to handle versions like "1.2.3-alpha"
            parts = re.split(r'[.-]', v)
            result = []
            for part in parts:
                if part.isdigit():
                    result.append(int(part))
                else:
                    # For non-numeric parts (like 'alpha', 'beta'), keep as lowercase string
                    result.append(part.lower())
            return result
        
        try:
            from_parts = parse_version(from_version)
            to_parts = parse_version(to_version)
            
            # Compare element by element
            max_len = max(len(from_parts), len(to_parts))
            for i in range(max_len):
                # Pad with 0 for numeric parts, empty string for non-numeric
                from_val = from_parts[i] if i < len(from_parts) else 0
                to_val = to_parts[i] if i < len(to_parts) else 0
                
                # Both are integers - compare numerically
                if isinstance(from_val, int) and isinstance(to_val, int):
                    if to_val > from_val:
                        return True
                    elif to_val < from_val:
                        return False
                # One or both are strings - convert both to strings and compare
                else:
                    from_str = str(from_val)
                    to_str = str(to_val)
                    if to_str > from_str:
                        return True
                    elif to_str < from_str:
                        return False
            
            # All parts are equal
            return False
        except Exception as e:
            print(f"Error comparing versions {from_version} vs {to_version}: {e}")
            return False

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
    
    def check_dependencies(self, pair: Dict[str, Any]) -> bool:
        """
        Check if the change is dependency-related using heuristic logic.
        
        Checks for:
        - Changes to libs.versions.toml
        - Changes within dependencies {} blocks in gradle files
        """
        to_commit = pair.get("to_commit") or pair.get("good_commit")
        commit_data = self.get_commit_diff(to_commit)
        files = commit_data.get("files", [])
        
        for file_obj in files:
            filename = file_obj.get("filename", "")
            patch = file_obj.get("patch", "")
            
            if "libs.versions.toml" in filename:
                return True
            elif filename.endswith("build.gradle") or filename.endswith("build.gradle.kts"):
                if self.check_dependencies_block(patch):
                    return True
        
        return False
    
    def check_version_update(self, pair: Dict[str, Any], file_info: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Check if the change is a version update using version comparison logic.
        
        Returns version change information if valid, None otherwise.
        """
        if not file_info:
            return None
        
        patch = file_info.get("patch", "")
        return self.extract_version_change(patch)

    def classify(self, pair: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main classification method for SimpleClassifier.
        
        Alias for classify_pair to maintain compatibility.
        """
        return self.classify_pair(pair)

    def classify_pair(self, pair: Dict[str, Any]) -> Dict[str, Any]:
        """
        Classifies a pair based on changed files.
        
        Rules:
        1. If ONLY libs.versions.toml was changed -> Category = "Dependency Update"
        2. If any dependency-related file was changed -> add "dependencies" tag
        3. If exactly one line changed in a dependency file -> add "one-line" tag
        4. If version increased -> add "version-update" tag and populate files_changed
        5. Dependencies files include:
           - libs.versions.toml
           - changes within dependencies {} block in build.gradle or build.gradle.kts
        """
        to_commit = pair.get("to_commit") or pair.get("good_commit")  # Support both formats for backward compatibility
        
        # Fetch the full commit diff
        commit_data = self.get_commit_diff(to_commit)
        files = commit_data.get("files", [])
        
        # Initialize tags from existing tags (preserve any existing tags)
        tags = pair.get("tags", [])[:]
        category = pair.get("category")
        
        # Track what types of changes we found
        libs_versions_changed = False
        gradle_dependencies_changed = False
        other_files_changed = False
        
        # Check for single-line change
        file_info = self.is_single_line_change(commit_data)
        if file_info:
            if "one-line" not in tags:
                tags.append("one-line")
            
            # Check for version increase using the check_version_update method
            version_change = self.check_version_update(pair, file_info)
            if version_change:
                if "version-update" not in tags:
                    tags.append("version-update")
                    
                # Populate files_changed if empty
                if not pair.get("files_changed"):
                    pair["files_changed"] = [{
                        "filename": file_info.get("filename"),
                        "line_number": version_change["line_number"],
                        "from_line_contents": version_change["from_line"],
                        "to_line_contents": version_change["to_line"]
                    }]
        
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
            if "dependencies" not in tags:
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
