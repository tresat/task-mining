import os
import json
import requests
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any

def load_env():
    """Simple .env loader."""
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

    def analyze(self, input_file: str, output_file: str):
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
                    
        with open(output_file, 'w') as f:
            json.dump(analyzed_pairs, f, indent=2)
        print(f"Saved analyzed results to {output_file}")

def main():
    load_env()
    parser = argparse.ArgumentParser(description="Analyze Mined Pairs")
    parser.add_argument("repo", help="owner/name")
    parser.add_argument("--input", default="mining_results.json")
    parser.add_argument("--output", default="analyzed_results.json")
    
    args = parser.parse_args()
    
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("Error: GITHUB_TOKEN not set.")
        return
        
    owner, name = args.repo.split("/", 1)
    analyzer = PairAnalyzer(token, owner, name)
    analyzer.analyze(args.input, args.output)

if __name__ == "__main__":
    main()
