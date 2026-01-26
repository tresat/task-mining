import os
import json
import time
import argparse
import requests
import re
from typing import List, Dict, Optional, Any
from .mine_common import load_env, ensure_directory, process_repo_list

# Configuration constants
CURSOR_DISPLAY_LENGTH = 20      # Number of characters to show in cursor display

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
                  committedDate  # Needed for from_date field in output
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

class CommitMiner:
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
        Mines the repository for commit pairs with successful builds.
        
        Args:
            search_limit: Maximum number of commits to search through (None for unlimited)
            results_limit: Maximum number of valid pairs to find (None for unlimited)
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
                    print(f"Loaded {len(results)} existing pairs from {output_file}")
            except Exception:
                print("Warning: Could not load existing results, starting fresh list.")
        
        cursor = self.load_state(state_file)
        if cursor:
            print(f"Resuming from cursor: {cursor}")
            
        processed_count = 0
        initial_results_count = len(results)  # Track starting count for cache reporting
        
        # If using cache, try to mine from cache first
        if cache_manager:
            print(f"\nMining from cache ({cache_manager.size()} commits available)...")
            cached_commits = cache_manager.get_all()
            
            # Get commit OIDs sorted (most recent first based on cache order)
            commit_oids = list(cached_commits.keys())
            
            for oid in commit_oids:
                # Check results limit
                if results_limit and len(results) >= results_limit:
                    print(f"Reached results limit of {results_limit} pairs.")
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
                
                # Create result entry - CommitMiner only checks for successful builds
                result = {
                    "pr_id": None,  # Not available for commit-based mining
                    "repo_url": f"https://github.com/{self.owner}/{self.name}",
                    "from_commit": parent_oid,
                    "from_msg": "",  # Parent message not available without additional API call
                    "from_date": parent.get("committedDate", ""),
                    "to_commit": oid,
                    "to_msg": msg,
                    "to_date": commit["committedDate"],
                    "files_changed": [],  # Will be populated by classifier
                    "category": None,
                    "tags": [],
                    "error": None
                }
                
                # Check for duplicates before adding
                if not any(r['to_commit'] == oid for r in results):
                    results.append(result)
                    print(f"Found pair: {parent_oid[:7]} -> {oid[:7]}")
                
                processed_count += 1
            
            # Save results after cache mining
            with open(output_file, "w") as f:
                json.dump(results, f, indent=2)
            new_from_cache = len(results) - initial_results_count
            print(f"\nCache exhausted. Found {new_from_cache} new pairs from cache.")
            
            # If we've hit limits, return
            if results_limit and len(results) >= results_limit:
                return results
            if search_limit and processed_count >= search_limit:
                return results
            
            print(f"Fetching more commits from GitHub...\n")
        
        # Continue with GitHub API queries
        while True:
            # Check results limit BEFORE fetching
            if results_limit and len(results) >= results_limit:
                print(f"Reached results limit of {results_limit} pairs.")
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
            
            # Abbreviate cursor for display
            cursor_display = f"{cursor[:CURSOR_DISPLAY_LENGTH]}" if cursor and len(cursor) > CURSOR_DISPLAY_LENGTH else cursor
            print(f"Fetching commits from GitHub (cursor={cursor_display}, processed={processed_count})...")
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
            
            # ALWAYS add fetched commits to cache FIRST
            if cache_manager:
                for commit in nodes:
                    oid = commit["oid"]
                    cache_manager.set(oid, commit)
                total_cache_size = cache_manager.size()
                print(f"Added {len(nodes)} commits to cache (total: {total_cache_size})")
            
            # Now process commits FROM CACHE
            for commit in nodes:
                # Check results limit immediately
                if results_limit and len(results) >= results_limit:
                    print(f"Reached results limit of {results_limit} pairs.")
                    with open(output_file, "w") as f:
                        json.dump(results, f, indent=2)
                    return results
                
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
                
                # Create result entry - CommitMiner only checks for successful builds
                result = {
                    "pr_id": None,  # Not available for commit-based mining
                    "repo_url": f"https://github.com/{self.owner}/{self.name}",
                    "from_commit": parent_oid,
                    "from_msg": "",  # Parent message not available without additional API call
                    "from_date": parent.get("committedDate", ""),
                    "to_commit": oid,
                    "to_msg": msg,
                    "to_date": commit["committedDate"],
                    "files_changed": [],  # Will be populated by classifier
                    "category": None,
                    "tags": [],
                    "error": None
                }
                
                # Check for duplicates before adding
                if not any(r['to_commit'] == oid for r in results):
                    results.append(result)
                    print(f"Found pair: {parent_oid[:7]} -> {oid[:7]}")
            
            # Save progress after each batch
            processed_count += len(nodes)
            cursor = history["pageInfo"]["endCursor"]
            self.save_state(state_file, cursor)
            
            with open(output_file, "w") as f:
                json.dump(results, f, indent=2)
            print(f"Saved {len(results)} pairs (total) to {output_file}")
            
            if not history["pageInfo"]["hasNextPage"]:
                print("Reached end of commits.")
                break
                
        return results

def process_repo(repo: str, token: str, search_limit: Optional[int], results_limit: Optional[int], output_dir: str, state_dir: str, ref: Optional[str] = None, use_cache: bool = True):
    """Process a single repository with optional caching."""
    # Note: PROCESSING REPO message is printed by run_pipeline.py, not here
    
    if "/" not in repo:
        print(f"Skipping invalid repo format: {repo}")
        return
        
    owner, name = repo.split("/", 1)
    
    # Create per_repo output directory
    per_repo_dir = os.path.join(output_dir, "per_repo")
    ensure_directory(per_repo_dir)
    
    # Create state directory if it doesn't exist
    ensure_directory(state_dir)
    
    output_file = os.path.join(per_repo_dir, f"{owner}_{name}.json")
    state_file = os.path.join(state_dir, f"{owner}_{name}_commit_pairs_state.json")
    
    miner = CommitMiner(token, owner, name)
    
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
        limit_desc.append(f"results limit: {results_limit} pairs")
    print(f"Mining {repo} ({', '.join(limit_desc) if limit_desc else 'no limits'})...")
    
    miner.mine(search_limit, results_limit, output_file, state_file, ref, cache_manager)
    print(f"Mining complete for {repo}.")

def main():
    load_env()
    
    parser = argparse.ArgumentParser(description="Mine Commit Pairs with Successful Builds from GitHub")
    parser.add_argument("repo_or_file", help="GitHub repository in 'owner/name' format OR path to a text file with a list of repos")
    parser.add_argument("--token", help="GitHub PAT (optional if GITHUB_TOKEN env var is set)")
    parser.add_argument("--search-limit", type=int, help="Maximum number of commits to search through")
    parser.add_argument("--results-limit", type=int, help="Maximum number of valid pairs to find")
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
    


if __name__ == "__main__":
    main()
