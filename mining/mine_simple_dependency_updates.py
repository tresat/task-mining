import os
import json
import time
import argparse
import requests
import re
from typing import List, Dict, Optional, Any
from .common import load_env, ensure_directory, process_repo_list

# GraphQL Query to fetch commits (not PRs)
COMMITS_QUERY = """
query ($owner: String!, $name: String!, $ref: String!, $cursor: String, $limit: Int!) {
  repository(owner: $owner, name: $name) {
    ref(qualifiedName: $ref) {
      target {
        ... on Commit {
          history(first: $limit, after: $cursor) {
            pageInfo {
              hasNextPage
              endCursor
            }
            nodes {
              oid
              message
              committedDate
              statusCheckRollup {
                state
              }
              status {
                state
              }
              parents(first: 1) {
                nodes {
                  oid
                  statusCheckRollup {
                    state
                  }
                  status {
                    state
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
"""

# Query to get the diff between parent and commit
COMMIT_DIFF_QUERY = """
query ($owner: String!, $name: String!, $oid: String!) {
  repository(owner: $owner, name: $name) {
    object(oid: $oid) {
      ... on Commit {
        changedFiles
        additions
        deletions
      }
    }
  }
}
"""

class SimpleDependencyMiner:
    def __init__(self, token: str, repo_owner: str, repo_name: str):
        self.token = token
        self.owner = repo_owner
        self.name = repo_name
        self.headers = {"Authorization": f"Bearer {token}"}
        self.graphql_url = "https://api.github.com/graphql"
        self.rest_api_url = "https://api.github.com"
    
    def _query(self, query: str, variables: Dict[str, Any]) -> Dict[str, Any]:
        """Executes a GraphQL query with retry logic."""
        max_retries = 5
        for attempt in range(max_retries):
            try:
                response = requests.post(
                    self.graphql_url,
                    json={"query": query, "variables": variables},
                    headers=self.headers,
                    timeout=30
                )
                if response.status_code == 200:
                    data = response.json()
                    if "errors" in data:
                        print(f"GraphQL Error: {data['errors']}")
                        return data
                    return data
                elif response.status_code in [502, 503, 504, 403]:
                    wait_time = 2 ** attempt
                    print(f"API Error {response.status_code}. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    response.raise_for_status()
            except requests.RequestException as e:
                wait_time = 2 ** attempt
                print(f"Request failed: {e}. Retrying in {wait_time}s...")
                time.sleep(wait_time)
        raise Exception("Max retries exceeded")
    
    def _rest_get(self, url: str) -> Any:
        """Execute REST API call with retry logic."""
        max_retries = 5
        for attempt in range(max_retries):
            try:
                response = requests.get(
                    url,
                    headers=self.headers,
                    timeout=30
                )
                if response.status_code == 200:
                    return response
                elif response.status_code in [502, 503, 504, 403]:
                    wait_time = 2 ** attempt
                    print(f"API Error {response.status_code}. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    response.raise_for_status()
            except requests.RequestException as e:
                wait_time = 2 ** attempt
                print(f"Request failed: {e}. Retrying in {wait_time}s...")
                time.sleep(wait_time)
        raise Exception("Max retries exceeded")

    def get_default_branch(self) -> str:
        """
        Detect the default branch for the repository.
        Tries 'main' first, then 'master' if main doesn't exist.
        Returns the ref string (e.g., 'refs/heads/main').
        """
        for branch in ['main', 'master']:
            ref = f'refs/heads/{branch}'
            # Quick check with a simple query
            test_query = """
            query ($owner: String!, $name: String!, $ref: String!) {
              repository(owner: $owner, name: $name) {
                ref(qualifiedName: $ref) {
                  name
                }
              }
            }
            """
            variables = {
                "owner": self.owner,
                "name": self.name,
                "ref": ref
            }
            try:
                data = self._query(test_query, variables)
                if data.get("data", {}).get("repository", {}).get("ref"):
                    print(f"Using branch: {branch}")
                    return ref
            except Exception:
                continue
        
        # Default to main if detection fails
        print("Could not detect default branch, defaulting to 'main'")
        return "refs/heads/main"

    def is_build_successful(self, commit_data: Dict[str, Any]) -> bool:
        """
        Determines if a commit build was successful.
        Checks both statusCheckRollup (Check Runs) and legacy status.
        """
        # Priority 1: StatusCheckRollup (Modern Check Runs + Statuses)
        rollup = commit_data.get("statusCheckRollup")
        if rollup:
            state = rollup.get("state")
            return state == "SUCCESS"
            
        # Priority 2: Legacy Status
        status = commit_data.get("status")
        if status:
            state = status.get("state")
            return state == "SUCCESS"
            
        # If no status info, assume it's NOT a success (we only want proven successes)
        return False

    def get_commit_diff(self, commit_sha: str) -> Optional[Dict[str, Any]]:
        """Fetches the diff for a commit using REST API."""
        url = f"{self.rest_api_url}/repos/{self.owner}/{self.name}/commits/{commit_sha}"
        try:
            response = self._rest_get(url)
            return response.json()
        except Exception as e:
            print(f"Error fetching diff for {commit_sha}: {e}")
            return None

    def is_single_line_change(self, commit_diff: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Checks if the commit changes only a single line in a dependency file.
        Returns the file info if valid, None otherwise.
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
        
        # Check if only one line changed (1 addition, 1 deletion)
        additions = file.get("additions", 0)
        deletions = file.get("deletions", 0)
        
        if additions != 1 or deletions != 1:
            return None
        
        return file

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

    def load_state(self, state_file: str) -> Optional[str]:
        if os.path.exists(state_file):
            try:
                with open(state_file, 'r') as f:
                    state = json.load(f)
                    return state.get("cursor")
            except Exception as e:
                print(f"Warning: Could not load state file: {e}")
        return None

    def save_state(self, state_file: str, cursor: str):
        with open(state_file, 'w') as f:
            json.dump({"cursor": cursor}, f)

    def mine(self, search_limit: Optional[int], results_limit: Optional[int], output_file: str, state_file: str, ref: str = "refs/heads/main", cache_manager=None) -> List[Dict[str, Any]]:
        """
        Mines the repository for simple dependency update commits with resumability and caching.
        
        Args:
            search_limit: Maximum number of commits to search through (None for unlimited)
            results_limit: Maximum number of valid updates to find (None for unlimited)
            output_file: Path to output JSON file
            state_file: Path to state file for resumability
            ref: Git ref to scan
            cache_manager: Optional CacheManager instance for commit caching
        """
        results = []
        
        # Create results directory if it doesn't exist
        output_dir = os.path.dirname(output_file)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # Load existing results if they exist, to avoid overwriting
        if os.path.exists(output_file):
            try:
                with open(output_file, 'r') as f:
                    results = json.load(f)
                    print(f"Loaded {len(results)} existing updates from {output_file}")
            except Exception:
                print("Warning: Could not load existing results, starting fresh list.")
        
        cursor = self.load_state(state_file)
        if cursor:
            print(f"Resuming from cursor: {cursor}")
            
        processed_count = 0
        
        # If using cache, try to mine from cache first
        if cache_manager:
            print(f"\nMining from cache ({cache_manager.size()} commits available)...")
            cached_commits = cache_manager.get_all()
            
            # Get commit OIDs sorted (most recent first based on cache order)
            commit_oids = list(cached_commits.keys())
            
            for oid in commit_oids:
                # Check results limit
                if results_limit and len(results) >= results_limit:
                    print(f"Reached results limit of {results_limit} updates.")
                    with open(output_file, "w") as f:
                        json.dump(results, f, indent=2)
                    return results
                
                # Check search limit
                if search_limit and processed_count >= search_limit:
                    print(f"Reached search limit of {search_limit} commits.")
                    with open(output_file, "w") as f:
                        json.dump(results, f, indent=2)
                    return results
                
                commit = cached_commits[oid]
                msg = commit["message"].split('\n')[0]
                
                # Check if current commit has successful build
                if not self.is_build_successful(commit):
                    processed_count += 1
                    continue
                
                # Check if parent commit has successful build
                parents = commit.get("parents", {}).get("nodes", [])
                if not parents:
                    processed_count += 1
                    continue
                
                parent = parents[0]
                if not self.is_build_successful(parent):
                    processed_count += 1
                    continue
                
                parent_oid = parent["oid"]
                
                # Fetch the diff for this commit
                commit_diff = self.get_commit_diff(oid)
                if not commit_diff:
                    processed_count += 1
                    continue
                
                # Check if it's a single line change in a dependency file
                file_info = self.is_single_line_change(commit_diff)
                if not file_info:
                    processed_count += 1
                    continue
                
                # Extract version change
                patch = file_info.get("patch", "")
                version_change = self.extract_version_change(patch)
                if not version_change:
                    processed_count += 1
                    continue
                
                # Create result entry
                result = {
                    "repo_url": f"https://github.com/{self.owner}/{self.name}",
                    "from_commit": parent_oid,
                    "from_msg": "",  # We don't have parent message easily
                    "to_commit": oid,
                    "to_msg": msg,
                    "files_changed": [{
                        "filename": file_info.get("filename"),
                        "line_number": version_change["line_number"],
                        "from_line_contents": version_change["from_line"],
                        "to_line_contents": version_change["to_line"]
                    }]
                }
                
                # Check for duplicates before adding
                if not any(r['to_commit'] == oid for r in results):
                    results.append(result)
                    print(f"Found update: {parent_oid[:7]} -> {oid[:7]} in {file_info.get('filename')}")
                
                processed_count += 1
            
            # Save results after cache mining
            with open(output_file, "w") as f:
                json.dump(results, f, indent=2)
            print(f"\nCache exhausted. Saved {len(results)} updates from cache.")
            
            # If we've hit limits, return
            if results_limit and len(results) >= results_limit:
                return results
            if search_limit and processed_count >= search_limit:
                return results
            
            print(f"Fetching more commits from GitHub...\n")
        
        # Continue with GitHub API queries
        while True:
            # Check results limit
            if results_limit and len(results) >= results_limit:
                print(f"Reached results limit of {results_limit} updates.")
                break
            
            # Check search limit
            if search_limit and processed_count >= search_limit:
                print(f"Reached search limit of {search_limit} commits.")
                break
            
            # Determine batch size
            from .cache import COMMIT_BATCH_SIZE
            if search_limit:
                batch_size = min(COMMIT_BATCH_SIZE, search_limit - processed_count)
            else:
                batch_size = COMMIT_BATCH_SIZE
                
            variables = {
                "owner": self.owner,
                "name": self.name,
                "ref": ref,
                "cursor": cursor,
                "limit": batch_size
            }
            
            print(f"Fetching commits from GitHub (cursor={cursor})...")
            data = self._query(COMMITS_QUERY, variables)
            
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
            
            batch_results = []
            for commit in nodes:
                oid = commit["oid"]
                msg = commit["message"].split('\n')[0]
                
                # Cache the commit if cache manager is available
                if cache_manager:
                    from .cache import MAX_CACHE_ITEMS
                    if cache_manager.size() < MAX_CACHE_ITEMS:
                        cache_manager.set(oid, commit)
                
                # Check if current commit has successful build
                if not self.is_build_successful(commit):
                    continue
                
                # Check if parent commit has successful build
                parents = commit.get("parents", {}).get("nodes", [])
                if not parents:
                    continue
                
                parent = parents[0]
                if not self.is_build_successful(parent):
                    continue
                
                parent_oid = parent["oid"]
                
                # Fetch the diff for this commit
                commit_diff = self.get_commit_diff(oid)
                if not commit_diff:
                    continue
                
                # Check if it's a single line change in a dependency file
                file_info = self.is_single_line_change(commit_diff)
                if not file_info:
                    continue
                
                # Extract version change
                patch = file_info.get("patch", "")
                version_change = self.extract_version_change(patch)
                if not version_change:
                    continue
                
                # Create result entry
                result = {
                    "repo_url": f"https://github.com/{self.owner}/{self.name}",
                    "from_commit": parent_oid,
                    "from_msg": "",  # We don't have parent message easily
                    "to_commit": oid,
                    "to_msg": msg,
                    "files_changed": [{
                        "filename": file_info.get("filename"),
                        "line_number": version_change["line_number"],
                        "from_line_contents": version_change["from_line"],
                        "to_line_contents": version_change["to_line"]
                    }]
                }
                
                # Check for duplicates before adding
                if not any(r['to_commit'] == oid for r in results) and not any(r['to_commit'] == oid for r in batch_results):
                    batch_results.append(result)
                    print(f"Found update: {parent_oid[:7]} -> {oid[:7]} in {file_info.get('filename')}")
            
            results.extend(batch_results)
            
            # Save progress after each batch
            processed_count += len(nodes)
            cursor = history["pageInfo"]["endCursor"]
            self.save_state(state_file, cursor)
            
            with open(output_file, "w") as f:
                json.dump(results, f, indent=2)
            print(f"Saved {len(results)} updates (total) to {output_file}")
            
            if not history["pageInfo"]["hasNextPage"]:
                print("Reached end of commits.")
                break
                
        return results

def process_repo(repo: str, token: str, search_limit: Optional[int], results_limit: Optional[int], output_dir: str, state_dir: str, ref: Optional[str] = None, use_cache: bool = True):
    """Process a single repository with optional caching."""
    print(f"\n{'#'*60}")
    print(f"PROCESSING REPO: {repo}")
    print(f"{'#'*60}\n")
    
    if "/" not in repo:
        print(f"Skipping invalid repo format: {repo}")
        return
        
    owner, name = repo.split("/", 1)
    
    # Create repo-specific output directory
    repo_output_dir = os.path.join(output_dir, f"{owner}_{name}")
    ensure_directory(repo_output_dir)
    
    # Create state directory if it doesn't exist
    ensure_directory(state_dir)
    
    output_file = os.path.join(repo_output_dir, "simple_dependency_updates.json")
    state_file = os.path.join(state_dir, f"{owner}_{name}_simple_dependency_state.json")
    
    miner = SimpleDependencyMiner(token, owner, name)
    
    # Detect default branch if not specified
    if ref is None:
        ref = miner.get_default_branch()
    
    # Initialize cache manager if caching is enabled
    cache_manager = None
    if use_cache:
        from .cache import CacheManager
        cache_manager = CacheManager(owner, name, "commits")
        print(f"Cache contains {cache_manager.size()} commits for {owner}/{name}")
    
    limit_desc = []
    if search_limit:
        limit_desc.append(f"search limit: {search_limit} commits")
    if results_limit:
        limit_desc.append(f"results limit: {results_limit} updates")
    print(f"Mining {repo} ({', '.join(limit_desc) if limit_desc else 'no limits'})...")
    
    miner.mine(search_limit, results_limit, output_file, state_file, ref, cache_manager)
    print(f"Mining complete for {repo}.")

def main():
    load_env()
    
    parser = argparse.ArgumentParser(description="Mine Simple Dependency Updates from GitHub")
    parser.add_argument("repo_or_file", help="GitHub repository in 'owner/name' format OR path to a text file with a list of repos")
    parser.add_argument("--token", help="GitHub PAT (optional if GITHUB_TOKEN env var is set)")
    parser.add_argument("--search-limit", type=int, help="Maximum number of commits to search through")
    parser.add_argument("--results-limit", type=int, help="Maximum number of valid updates to find")
    parser.add_argument("--output", default="results", help="Output directory for results")
    parser.add_argument("--state", default=".state", help="Directory for state files (default: .state)")
    parser.add_argument("--ref", default=None, help="Git ref to scan (e.g., refs/heads/main). If not specified, auto-detects main or master")
    
    args = parser.parse_args()
    
    # Validate that at least one limit is specified
    if not args.search_limit and not args.results_limit:
        parser.error("At least one of --search-limit or --results-limit must be specified")
    
    token = args.token or os.environ.get("GITHUB_TOKEN")
    if not token:
        print("Error: No GitHub token provided. Set GITHUB_TOKEN or use --token.")
        return

    repos = process_repo_list(args.repo_or_file)
    
    for repo in repos:
        try:
            process_repo(repo, token, args.search_limit, args.results_limit, args.output, args.state, args.ref)
        except Exception as e:
            print(f"Failed to process {repo}: {e}")
            # Continue to next repo
    
    print("\nAll mining complete!")

if __name__ == "__main__":
    main()
