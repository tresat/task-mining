import os
import json
import time
import argparse
import requests
from typing import List, Dict, Optional, Generator, Any
from .mine_common import load_env, ensure_directory, process_repo_list

# Configuration constants
CURSOR_DISPLAY_LENGTH = 20      # Number of characters to show in cursor display
CACHE_SIZE_THRESHOLD = 100      # Don't fetch from GitHub if cache >= this size

# GraphQL Queries
PR_QUERY = """
query ($owner: String!, $name: String!, $cursor: String, $limit: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequests(first: $limit, states: MERGED, after: $cursor, orderBy: {field: UPDATED_AT, direction: DESC}) {
      pageInfo {
        hasNextPage
        endCursor
      }
      nodes {
        number
        title
        body
        url
        commits(first: 100) {
          pageInfo {
            hasNextPage
            endCursor
          }
          nodes {
            commit {
              oid
              message
              committedDate
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
"""

# Additional query for fetching more commits if a PR has > 100
COMMITS_QUERY = """
query ($owner: String!, $name: String!, $pr_number: Int!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $pr_number) {
      commits(first: 100, after: $cursor) {
        pageInfo {
          hasNextPage
          endCursor
        }
        nodes {
          commit {
            oid
            message
            committedDate
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
"""

class PRMiner:
    def __init__(self, token: str, repo_owner: str, repo_name: str):
        self.token = token
        self.owner = repo_owner
        self.name = repo_name
        self.headers = {"Authorization": f"Bearer {token}"}
        self.api_url = "https://api.github.com/graphql"

    def _query(self, query: str, variables: Dict[str, Any]) -> Dict[str, Any]:
        """Executes a GraphQL query with retry logic."""
        max_retries = 5
        for attempt in range(max_retries):
            try:
                response = requests.post(
                    self.api_url,
                    json={"query": query, "variables": variables},
                    headers=self.headers,
                    timeout=30
                )
                if response.status_code == 200:
                    data = response.json()
                    if "errors" in data:
                        # Handle GraphQL errors (some might be transient)
                        print(f"GraphQL Error: {data['errors']}")
                        # If it's a rate limit or server error, we might want to retry
                        # For now, just return data and let caller handle or fail
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

    def is_build_successful(self, commit_node: Dict[str, Any]) -> bool:
        """
        Determines if a commit build was successful.
        Checks both statusCheckRollup (Check Runs) and legacy status.
        """
        commit = commit_node.get("commit", {})
        
        # Priority 1: StatusCheckRollup (Modern Check Runs + Statuses)
        rollup = commit.get("statusCheckRollup")
        if rollup:
            state = rollup.get("state")
            return state == "SUCCESS"
            
        # Priority 2: Legacy Status
        status = commit.get("status")
        if status:
            state = status.get("state")
            return state == "SUCCESS"
            
        # If no status info, assume it's NOT a success (we only want proven successes)
        return False

    def is_build_failed(self, commit_node: Dict[str, Any]) -> bool:
        """
        Determines if a commit build failed.
        """
        commit = commit_node.get("commit", {})
        
        rollup = commit.get("statusCheckRollup")
        if rollup:
            state = rollup.get("state")
            return state in ["FAILURE", "ERROR"]
            
        status = commit.get("status")
        if status:
            state = status.get("state")
            return state in ["FAILURE", "ERROR"]
            
        return False
    
    def _build_pr_description(self, pr_data: Dict[str, Any]) -> str:
        """Builds a PR description from title and body."""
        pr_title = pr_data.get("title", "")
        pr_body = pr_data.get("body", "")
        
        if pr_body:
            return f"{pr_title}\n\n{pr_body}"
        else:
            return pr_title

    def get_all_commits_for_pr(self, pr_node: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Fetches all commits for a PR, handling pagination if > 100."""
        commits_data = pr_node["commits"]
        all_commits = commits_data["nodes"]
        
        page_info = commits_data["pageInfo"]
        cursor = page_info["endCursor"]
        has_next = page_info["hasNextPage"]
        pr_number = pr_node["number"]

        while has_next:
            print(f"Fetching more commits for PR #{pr_number}...")
            variables = {
                "owner": self.owner,
                "name": self.name,
                "pr_number": pr_number,
                "cursor": cursor
            }
            data = self._query(COMMITS_QUERY, variables)
            pr_data = data["data"]["repository"]["pullRequest"]
            new_commits = pr_data["commits"]
            
            all_commits.extend(new_commits["nodes"])
            
            page_info = new_commits["pageInfo"]
            cursor = page_info["endCursor"]
            has_next = page_info["hasNextPage"]
            
        return all_commits

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

    def mine(self, search_limit: Optional[int], results_limit: Optional[int], output_file: str, state_file: str, cache_manager=None) -> List[Dict[str, Any]]:
        """
        Mines the repository for Bad -> Good commit pairs with resumability and caching.
        
        Args:
            search_limit: Maximum number of PRs to search through (None for unlimited)
            results_limit: Maximum number of valid pairs to find (None for unlimited)
            output_file: Path to output JSON file
            state_file: Path to state file for resumability
            cache_manager: Optional CacheManager instance for PR caching
        """
        results = []
        
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
            cache_size = cache_manager.size()
            print(f"\nMining from cache ({cache_size} PRs available)...")
            cached_prs = cache_manager.get_all()
            
            # Sort PR numbers to process in order
            pr_numbers = sorted([int(k) for k in cached_prs.keys()], reverse=True)
            
            for pr_number in pr_numbers:
                # Check results limit
                if results_limit and len(results) >= results_limit:
                    print(f"Reached results limit of {results_limit} pairs.")
                    return results
                
                # Check search limit
                if search_limit and processed_count >= search_limit:
                    print(f"Reached search limit of {search_limit} PRs.")
                    return results
                
                pr_data = cached_prs[str(pr_number)]
                commits = pr_data["commits"]["nodes"]
                pr_description = self._build_pr_description(pr_data)
                
                last_bad_commit = None
                
                for commit_node in commits:
                    commit = commit_node["commit"]
                    oid = commit["oid"]
                    msg = commit["message"].split('\n')[0]
                    
                    if self.is_build_failed(commit_node):
                        last_bad_commit = commit_node
                    elif self.is_build_successful(commit_node):
                        if last_bad_commit:
                            bad_commit = last_bad_commit["commit"]
                            pair = {
                                "pr_id": pr_number,
                                "repo_url": f"https://github.com/{self.owner}/{self.name}",
                                "from_commit": bad_commit["oid"],
                                "from_msg": bad_commit["message"].split('\n')[0],
                                "from_date": bad_commit["committedDate"],
                                "to_commit": oid,
                                "to_msg": pr_description,
                                "to_date": commit["committedDate"],
                                "files_changed": [],  # Not available for PR-based mining; can be populated by classification
                                "category": None,
                                "tags": [],
                                "error": None
                            }
                            # Check for duplicates before adding
                            if not any(r['to_commit'] == oid for r in results):
                                results.append(pair)
                            
                            last_bad_commit = None
                
                processed_count += 1
            
            # Save results after cache mining
            with open(output_file, "w") as f:
                json.dump(results, f, indent=2)
            new_from_cache = len(results) - initial_results_count
            
            # Report cache processing results
            if new_from_cache > 0:
                print(f"\nProcessed {processed_count} PRs from cache. Found {new_from_cache} new pairs.")
            else:
                print(f"\nProcessed {processed_count} PRs from cache. No new valid pairs found.")
            
            # If we've hit limits, return
            if results_limit and len(results) >= results_limit:
                print(f"Reached results limit of {results_limit} pairs.")
                return results
            if search_limit and processed_count >= search_limit:
                print(f"Reached search limit of {search_limit} PRs.")
                return results
            
            # Only fetch more from GitHub if cache was small (< CACHE_SIZE_THRESHOLD PRs)
            # If we have a large cache but no results, the repo likely doesn't have many valid pairs
            if cache_manager.size() < CACHE_SIZE_THRESHOLD:
                print(f"Cache has fewer than {CACHE_SIZE_THRESHOLD} PRs. Fetching more from GitHub...\n")
            else:
                print(f"Cache has {cache_manager.size()} PRs. Stopping search (found {len(results)} pairs total).")
                return results
        
        # Continue with GitHub API queries
        while True:
            # Check results limit BEFORE fetching
            if results_limit and len(results) >= results_limit:
                print(f"Reached results limit of {results_limit} pairs.")
                break
            
            # Check search limit
            if search_limit and processed_count >= search_limit:
                print(f"Reached search limit of {search_limit} PRs.")
                break
            
            # Determine batch size
            from .cache import PR_BATCH_SIZE
            if search_limit:
                batch_size = min(PR_BATCH_SIZE, search_limit - processed_count)
            else:
                batch_size = PR_BATCH_SIZE
                
            variables = {
                "owner": self.owner,
                "name": self.name,
                "cursor": cursor,
                "limit": batch_size
            }
            
            # Abbreviate cursor for display
            cursor_display = f"{cursor[:CURSOR_DISPLAY_LENGTH]}..." if cursor and len(cursor) > CURSOR_DISPLAY_LENGTH else cursor
            print(f"Fetching PRs from GitHub (cursor={cursor_display}, processed={processed_count})...")
            data = self._query(PR_QUERY, variables)
            
            if not data.get("data") or not data["data"].get("repository"):
                print("No data returned or repository not found.")
                break

            prs = data["data"]["repository"]["pullRequests"]
            nodes = prs["nodes"]
            
            if not nodes:
                print("No more PRs found.")
                break
            
            # ALWAYS add fetched PRs to cache FIRST
            if cache_manager:
                for pr in nodes:
                    pr_number = pr["number"]
                    commits = self.get_all_commits_for_pr(pr)
                    pr_data = pr.copy()
                    pr_data["commits"]["nodes"] = commits
                    cache_manager.set(str(pr_number), pr_data)
                total_cache_size = cache_manager.size()
                print(f"Added {len(nodes)} PRs to cache (total: {total_cache_size})")
            
            # Track results count before processing this batch
            batch_start_count = len(results)
            
            # Now process PRs FROM CACHE
            for pr in nodes:
                # Check results limit immediately
                if results_limit and len(results) >= results_limit:
                    print(f"Reached results limit of {results_limit} pairs.")
                    with open(output_file, "w") as f:
                        json.dump(results, f, indent=2)
                    return results
                
                pr_number = pr["number"]
                commits = self.get_all_commits_for_pr(pr)
                pr_description = self._build_pr_description(pr)
                
                last_bad_commit = None
                
                for commit_node in commits:
                    commit = commit_node["commit"]
                    oid = commit["oid"]
                    msg = commit["message"].split('\n')[0]
                    
                    if self.is_build_failed(commit_node):
                        last_bad_commit = commit_node
                    elif self.is_build_successful(commit_node):
                        if last_bad_commit:
                            bad_commit = last_bad_commit["commit"]
                            pair = {
                                "pr_id": pr_number,
                                "repo_url": f"https://github.com/{self.owner}/{self.name}",
                                "from_commit": bad_commit["oid"],
                                "from_msg": bad_commit["message"].split('\n')[0],
                                "from_date": bad_commit["committedDate"],
                                "to_commit": oid,
                                "to_msg": pr_description,
                                "to_date": commit["committedDate"],
                                "files_changed": [],  # Not available for PR-based mining; can be populated by classification
                                "category": None,
                                "tags": [],
                                "error": None
                            }
                            # Check for duplicates before adding
                            if not any(r['to_commit'] == oid for r in results):
                                results.append(pair)
                                
                                # Check limit immediately after adding
                                if results_limit and len(results) >= results_limit:
                                    print(f"Reached results limit of {results_limit} pairs.")
                                    with open(output_file, "w") as f:
                                        json.dump(results, f, indent=2)
                                    return results
                            
                            last_bad_commit = None
            
            # Save progress after each batch
            processed_count += len(nodes)
            cursor = prs["pageInfo"]["endCursor"]
            self.save_state(state_file, cursor)
            
            # Save to file (always)
            with open(output_file, "w") as f:
                json.dump(results, f, indent=2)
            
            # Only print save message if new pairs were added in this batch
            batch_pairs_added = len(results) - batch_start_count
            if batch_pairs_added > 0:
                print(f"Saved {len(results)} pairs (total) to {output_file}")
            
            if not prs["pageInfo"]["hasNextPage"]:
                print("Reached end of PRs.")
                break
                
        return results

def process_repo(repo: str, token: str, search_limit: Optional[int], results_limit: Optional[int], output_dir: str, state_dir: str, use_cache: bool = True):
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
    state_file = os.path.join(state_dir, f"{owner}_{name}_mining_state.json")
    
    miner = PRMiner(token, owner, name)
    
    # Initialize cache manager if caching is enabled
    cache_manager = None
    if use_cache:
        from .cache import CacheManager
        cache_manager = CacheManager(owner, name, "prs")
        print(f"Cache contains {cache_manager.size()} PRs for {owner}/{name}")
    
    limit_desc = []
    if search_limit:
        limit_desc.append(f"search limit: {search_limit} PRs")
    if results_limit:
        limit_desc.append(f"results limit: {results_limit} pairs")
    print(f"Mining {repo} ({', '.join(limit_desc) if limit_desc else 'no limits'})...")
    
    results = miner.mine(search_limit, results_limit, output_file, state_file, cache_manager)
    
    # Check if fewer results than requested were found
    if results_limit and len(results) < results_limit:
        print(f"⚠ Only found {len(results)} pair(s) for {repo} (requested {results_limit})")
    
    print(f"Mining complete for {repo}.")

def main():
    load_env()
    
    parser = argparse.ArgumentParser(description="Mine Self-Correction Pairs from GitHub")
    parser.add_argument("repo_or_file", help="GitHub repository in 'owner/name' format OR path to a text file with a list of repos")
    parser.add_argument("--token", help="GitHub PAT (optional if GITHUB_TOKEN env var is set)")
    parser.add_argument("--search-limit", type=int, help="Maximum number of PRs to search through")
    parser.add_argument("--results-limit", type=int, help="Maximum number of valid pairs to find")
    parser.add_argument("--output", default="results", help="Output directory for results")
    parser.add_argument("--state", default=".state", help="Directory for state files (default: .state)")
    
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
            process_repo(repo, token, args.search_limit, args.results_limit, args.output, args.state)
        except Exception as e:
            print(f"Failed to process {repo}: {e}")
            # Continue to next repo
    


if __name__ == "__main__":
    main()
