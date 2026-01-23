import os
import json
import time
import argparse
import requests
from typing import List, Dict, Any
import sys

# Add parent directory to path to import from mining
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from mining.common import load_env

class GeminiClassifier:
    def __init__(self, github_token: str, gemini_key: str, repo_owner: str, repo_name: str):
        self.github_token = github_token
        self.gemini_key = gemini_key
        self.owner = repo_owner
        self.name = repo_name
        self.headers = {
            "Authorization": f"Bearer {github_token}",
            "Accept": "application/vnd.github.v3.diff"
        }
        self.gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={gemini_key}"

    def get_commit_diff(self, commit_sha: str) -> str:
        """Fetches the diff of a commit."""
        url = f"https://api.github.com/repos/{self.owner}/{self.name}/commits/{commit_sha}"
        try:
            response = requests.get(url, headers=self.headers, timeout=15)
            if response.status_code == 200:
                return response.text[:10000]  # Truncate
            else:
                print(f"Failed to fetch diff for {commit_sha}: {response.status_code}")
                return ""
        except Exception as e:
            print(f"Error fetching diff for {commit_sha}: {e}")
            return ""

    def classify_with_gemini(self, message: str, diff: str) -> str:
        """Asks Gemini if this is a dependency update using REST API."""
        if not diff:
            return "Unknown (No Diff)"
            
        prompt_text = f"""
        Analyze the following commit to determine if it is purely a "Dependency Update" (updating libraries, versions, etc.).
        
        Commit Message:
        {message}
        
        Diff Snippet:
        {diff}
        
        Is this a dependency update? 
        Answer ONLY with "YES" or "NO".
        """
        
        payload = {
            "contents": [{
                "parts": [{"text": prompt_text}]
            }]
        }
        
        try:
            response = requests.post(self.gemini_url, json=payload, timeout=30)
            if response.status_code == 200:
                data = response.json()
                try:
                    answer = data["candidates"][0]["content"]["parts"][0]["text"].strip().upper()
                    if "YES" in answer:
                        return "YES"
                    elif "NO" in answer:
                        return "NO"
                    else:
                        return "UNCERTAIN"
                except (KeyError, IndexError) as e:
                    print(f"Error parsing Gemini response: {e}")
                    return "ERROR"
            else:
                print(f"Gemini API Error {response.status_code}: {response.text}")
                return "ERROR"
        except Exception as e:
            print(f"Gemini Request Error: {e}")
            return "ERROR"

    def run(self, input_file: str, output_file: str):
        if not os.path.exists(input_file):
            print(f"Error: Input file {input_file} not found.")
            return

        with open(input_file, 'r') as f:
            pairs = json.load(f)
            
        # Load existing results to skip already processed ones
        existing_results = []
        processed_commits = set()
        
        if os.path.exists(output_file):
            try:
                with open(output_file, 'r') as f:
                    existing_results = json.load(f)
                    processed_commits = {r.get("to_commit") or r.get("good_commit") for r in existing_results}
                    print(f"Loaded {len(existing_results)} existing classifications.")
            except Exception:
                print("Warning: Could not load existing results, starting fresh.")

        print(f"Classifying {len(pairs)} pairs with Gemini...")
        
        results = existing_results
        new_count = 0
        
        for i, pair in enumerate(pairs):
            to_commit = pair.get("to_commit") or pair.get("good_commit")  # Support both formats
            
            if to_commit in processed_commits:
                print(f"[{i+1}/{len(pairs)}] Skipping {to_commit[:7]} (Already processed)")
                continue
                
            msg = pair.get("to_msg") or pair.get("good_msg")  # Support both formats
            
            print(f"[{i+1}/{len(pairs)}] Fetching diff for {to_commit[:7]}...")
            diff = self.get_commit_diff(to_commit)
            
            print(f"  Asking Gemini...")
            ai_verdict = self.classify_with_gemini(msg, diff)
            print(f"  Verdict: {ai_verdict}")
            
            pair["ai_is_dependency_update"] = ai_verdict
            results.append(pair)
            processed_commits.add(to_commit)
            new_count += 1
            
            # Save incrementally every 5 items
            if new_count % 5 == 0:
                with open(output_file, 'w') as f:
                    json.dump(results, f, indent=2)
                print(f"  [Saved progress to {output_file}]")
            
            time.sleep(1) # Rate limit niceness
            
        # Final save
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"Saved all AI classification results to {output_file}")

def main():
    load_env()
    parser = argparse.ArgumentParser(description="Gemini Classifier")
    parser.add_argument("repo", help="owner/name")
    parser.add_argument("--input", default="analyzed_results.json")
    parser.add_argument("--output", default="ai_classified_results.json")
    
    args = parser.parse_args()
    
    gh_token = os.environ.get("GITHUB_TOKEN")
    gemini_key = os.environ.get("GEMINI_API_KEY")
    
    if not gh_token or not gemini_key:
        print("Error: GITHUB_TOKEN and GEMINI_API_KEY must be set.")
        return
        
    owner, name = args.repo.split("/", 1)
    classifier = GeminiClassifier(gh_token, gemini_key, owner, name)
    classifier.run(args.input, args.output)

if __name__ == "__main__":
    main()
