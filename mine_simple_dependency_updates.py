import os
import json
import time
import argparse
import requests
import re
from typing import List, Dict, Optional, Any

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

def load_env():
    """Simple .env loader to avoid external dependencies."""
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()

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
            elif not line.startswith('\\') and not line.startswith('---') and not line.startswith('+++'):  # Ignore "\ No newline at end of file" and file markers
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
        """Extract version string from a line."""
        # Common patterns for version numbers in gradle and toml files
        # Examples: 
        # - version = "1.2.3"
        # - implementation("com.example:lib:1.2.3")
        # - someLib = "1.2.3"
        
        # Try to find semantic version pattern
        patterns = [
            r'["\'](\d+\.\d+(?:\.\d+)?(?:[.-][a-zA-Z0-9]+)?)["\']',  # "1.2.3" or '1.2.3'
            r':(\d+\.\d+(?:\.\d+)?(?:[.-][a-zA-Z0-9]+)?)["\']',      # :1.2.3"
            r'=\s*(\d+\.\d+(?:\.\d+)?(?:[.-][a-zA-Z0-9]+)?)(?:\s|$)', # = 1.2.3
        ]
        
        for pattern in patterns:
            match = re.search(pattern, line)
            if match:
                return match.group(1)
        
        return None

    def _is_version_increase(self, from_version: str, to_version: str) -> bool:
        """Check if to_version is greater than from_version."""
        # Parse version strings
        def parse_version(v: str) -> tuple:
            # Split on dots and dashes
            parts = re.split(r'[.-]', v)
            numeric_parts = []
            for part in parts:
                if part.isdigit():
                    numeric_parts.append(int(part))
                else:
                    # For non-numeric parts (like 'alpha', 'beta'), keep as string
                    numeric_parts.append(part)
            return tuple(numeric_parts)
        
        try:
            from_parts = parse_version(from_version)
            to_parts = parse_version(to_version)
            
            # Compare element by element
            max_len = max(len(from_parts), len(to_parts))
            for i in range(max_len):
                from_val = from_parts[i] if i < len(from_parts) else 0
                to_val = to_parts[i] if i < len(to_parts) else 0
                
                # If both are integers, compare numerically
                if isinstance(from_val, int) and isinstance(to_val, int):
                    if to_val > from_val:
                        return True
                    elif to_val < from_val:
                        return False
                # If one is string, do string comparison
                elif str(to_val) > str(from_val):
                    return True
                elif str(to_val) < str(from_val):
                    return False
            
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

    def mine(self, limit: int, output_file: str, state_file: str, ref: str = "refs/heads/main") -> List[Dict[str, Any]]:
        """Mines the repository for simple dependency update commits with resumability."""
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
        
        while processed_count < limit:
            batch_size = min(100, limit - processed_count)
            variables = {
                "owner": self.owner,
                "name": self.name,
                "ref": ref,
                "cursor": cursor,
                "limit": batch_size
            }
            
            print(f"Fetching commits (cursor={cursor})...")
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
                    "from_commit": parent_oid,
                    "from_msg": "",  # We don't have parent message easily
                    "to_commit": oid,
                    "to_msg": msg,
                    "changed_file": file_info.get("filename"),
                    "changed_line_number": version_change["line_number"],
                    "from_line_contents": version_change["from_line"],
                    "to_line_contents": version_change["to_line"]
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

def main():
    load_env()
    
    parser = argparse.ArgumentParser(description="Mine Simple Dependency Updates from GitHub")
    parser.add_argument("repo", help="GitHub repository in 'owner/name' format")
    parser.add_argument("--token", help="GitHub PAT (optional if GITHUB_TOKEN env var is set)")
    parser.add_argument("--limit", type=int, default=1000, help="Number of commits to scan")
    parser.add_argument("--output", default="results/simple_dependency_updates.json", help="Output JSON file")
    parser.add_argument("--state", default="simple_dependency_state.json", help="State file for resumability")
    parser.add_argument("--ref", default="refs/heads/main", help="Git ref to scan (default: refs/heads/main)")
    
    args = parser.parse_args()
    
    token = args.token or os.environ.get("GITHUB_TOKEN")
    if not token:
        print("Error: No GitHub token provided. Set GITHUB_TOKEN or use --token.")
        return

    if "/" not in args.repo:
        print("Error: Repo must be in 'owner/name' format.")
        return
        
    owner, name = args.repo.split("/", 1)
    
    miner = SimpleDependencyMiner(token, owner, name)
    print(f"Mining {args.repo} for up to {args.limit} commits...")
    
    miner.mine(args.limit, args.output, args.state, args.ref)
    print("Mining complete.")

if __name__ == "__main__":
    main()
