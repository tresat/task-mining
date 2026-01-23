import os
import json
import requests
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any
import sys

# Add parent directory to path to import from mining
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from mining.mine_common import load_env

class PairAnalyzer:
    def __init__(self, token: str, repo_owner: str, repo_name: str):
        self.token = token
        self.owner = repo_owner
        self.name = repo_name
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json"
        }
        self.api_url = "https://api.github.com"

    def get_changed_files(self, commit_sha: str) -> List[str]:
        """Fetches list of changed files for a commit using REST API."""
        url = f"{self.api_url}/repos/{self.owner}/{self.name}/commits/{commit_sha}"
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                return [f['filename'] for f in data.get('files', [])]
            else:
                print(f"Failed to fetch commit {commit_sha}: {response.status_code}")
                return []
        except Exception as e:
            print(f"Error fetching commit {commit_sha}: {e}")
            return []

    def classify_pair(self, pair: Dict[str, Any]) -> Dict[str, Any]:
        """Classifies a pair based on changed files."""
        to_commit = pair.get("to_commit") or pair.get("good_commit")  # Support both formats for backward compatibility
        files = self.get_changed_files(to_commit)
        
        is_dependency_update = False
        for f in files:
            if "libs.versions.toml" in f or f.endswith("build.gradle") or f.endswith("build.gradle.kts"):
                is_dependency_update = True
                break
        
        pair["files_changed"] = files
        pair["category"] = "Dependency Update" if is_dependency_update else "Other"
        return pair

    def analyze(self, input_file: str):
        """Analyzes pairs in-place, updating the category field."""
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
                    print(f"Analyzed {to_commit[:7]} -> {result['category']}")
                except Exception as e:
                    print(f"Analysis failed for a pair: {e}")
                    
        # Write back to the same file (in-place edit)
        with open(input_file, 'w') as f:
            json.dump(analyzed_pairs, f, indent=2)
        print(f"Updated {input_file} with category classifications")

def main():
    load_env()
    parser = argparse.ArgumentParser(description="Analyze Mined Pairs")
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
    
    analyzer = PairAnalyzer(token, owner, name)
    analyzer.analyze(input_file)

if __name__ == "__main__":
    main()
