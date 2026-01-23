import os
import json
import time
import argparse
import requests
from typing import List, Dict, Any
import sys

# Add parent directory to path to import from mining
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from mining.mine_common import load_env

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

    def classify_with_gemini(self, message: str, diff: str) -> dict:
        """Asks Gemini for sub-categorization using REST API.
        
        Returns:
            dict with 'sub_category' and 'error' keys. 
            If successful, error is None. If failed, sub_category is None and error contains descriptive message.
        """
        if not diff:
            return {"sub_category": "Unknown (No Diff)", "error": None}
            
        prompt_text = f"""
        Analyze the following commit to determine its sub-category.
        
        Commit Message:
        {message}
        
        Diff Snippet:
        {diff}
        
        Classify this commit into one of these sub-categories:
        - "Dependency Update" - Version updates, library changes
        - "Bug Fix" - Fixing errors or issues
        - "Feature" - Adding new functionality
        - "Refactor" - Code restructuring without changing functionality
        - "Other" - Doesn't fit other categories
        
        Answer with ONLY the sub-category name from the list above.
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
                    answer = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                    # Extract the sub-category from the response
                    if "Dependency Update" in answer:
                        return {"sub_category": "Dependency Update", "error": None}
                    elif "Bug Fix" in answer:
                        return {"sub_category": "Bug Fix", "error": None}
                    elif "Feature" in answer:
                        return {"sub_category": "Feature", "error": None}
                    elif "Refactor" in answer:
                        return {"sub_category": "Refactor", "error": None}
                    else:
                        return {"sub_category": "Other", "error": None}
                except (KeyError, IndexError) as e:
                    error_msg = f"Error parsing Gemini response: {e}"
                    print(error_msg)
                    return {"sub_category": None, "error": error_msg}
            else:
                error_msg = f"{response.status_code}: {response.text}"
                print(f"Gemini API Error {error_msg}")
                return {"sub_category": None, "error": error_msg}
        except Exception as e:
            error_msg = f"Request error: {str(e)}"
            print(f"Gemini Request Error: {e}")
            return {"sub_category": None, "error": error_msg}

    def run(self, input_file: str):
        """Classifies pairs in-place, updating the sub_category field."""
        if not os.path.exists(input_file):
            print(f"Error: Input file {input_file} not found.")
            return

        with open(input_file, 'r') as f:
            pairs = json.load(f)
            
        # Track which commits have been processed with sub_category
        # We check for not None and not empty string to handle all edge cases
        processed_commits = set()
        for pair in pairs:
            to_commit = pair.get("to_commit") or pair.get("good_commit")
            sub_cat = pair.get("sub_category")
            if sub_cat is not None and sub_cat != "":
                processed_commits.add(to_commit)
                
        print(f"Found {len(processed_commits)} already classified pairs.")
        print(f"Classifying {len(pairs) - len(processed_commits)} remaining pairs with Gemini...")
        
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
            result = self.classify_with_gemini(msg, diff)
            ai_verdict = result["sub_category"]
            error = result["error"]
            print(f"  Sub-category: {ai_verdict}")
            
            pair["sub_category"] = ai_verdict
            pair["error"] = error
            processed_commits.add(to_commit)
            new_count += 1
            
            # Save incrementally every 5 items
            if new_count % 5 == 0:
                with open(input_file, 'w') as f:
                    json.dump(pairs, f, indent=2)
                print(f"  [Saved progress to {input_file}]")
            
            time.sleep(1) # Rate limit niceness
            
        # Final save
        with open(input_file, 'w') as f:
            json.dump(pairs, f, indent=2)
        print(f"Updated {input_file} with AI sub-category classifications")

def main():
    load_env()
    parser = argparse.ArgumentParser(description="Gemini Classifier")
    parser.add_argument("repo", help="owner/name")
    parser.add_argument("--input", help="Input file path (default: results/per_repo/{owner}_{name}.json)")
    
    args = parser.parse_args()
    
    gh_token = os.environ.get("GITHUB_TOKEN")
    gemini_key = os.environ.get("GEMINI_API_KEY")
    
    if not gh_token or not gemini_key:
        print("Error: GITHUB_TOKEN and GEMINI_API_KEY must be set.")
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
    
    classifier = GeminiClassifier(gh_token, gemini_key, owner, name)
    classifier.run(input_file)

if __name__ == "__main__":
    main()
