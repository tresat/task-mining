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
from classification.base_ai_classifier import BaseAIClassifier

class GeminiClassifier(BaseAIClassifier):
    def __init__(self, github_token: str, gemini_key: str, repo_owner: str, repo_name: str):
        super().__init__(github_token, gemini_key, repo_owner, repo_name)
        self.gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={gemini_key}"
    
    def _call_ai_api(self, message: str, diff: str) -> dict:
        """Asks Gemini for sub-categorization using REST API.
        
        Returns:
            dict with 'sub_category' and 'error' keys. 
            If successful, error is None. If failed, sub_category is None and error contains descriptive message.
        """
        if not diff:
            return {"sub_category": "Unknown (No Diff)", "error": None}
        
        if not self.categories:
            return {"sub_category": "Other", "error": "No categories loaded"}
        
        # Build category descriptions dynamically
        category_descriptions = []
        for category_name, description in self.categories.items():
            category_descriptions.append(f"**{category_name}**: {description}")
        
        prompt_text = f"""
        Analyze the following commit to determine its sub-category.
        
        Commit Message:
        {message}
        
        Diff Snippet:
        {diff}
        
        Classify this commit into ONE of these categories:
        
        {chr(10).join(category_descriptions)}
        
        Answer with ONLY the category name from the list above.
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
                    # Extract the sub-category from the response by checking against known categories
                    for category_name in self.categories.keys():
                        if category_name in answer:
                            return {"sub_category": category_name, "error": None}
                    # If no match, return Other as fallback (or first category if Other doesn't exist)
                    if "Other" in self.categories:
                        return {"sub_category": "Other", "error": None}
                    elif self.categories:
                        return {"sub_category": list(self.categories.keys())[0], "error": None}
                    else:
                        return {"sub_category": "Unknown", "error": None}
                except (KeyError, IndexError) as e:
                    error_msg = f"Error parsing Gemini response: {e}"
                    print(error_msg)
                    return {"sub_category": None, "error": error_msg}
            else:
                error_msg = f"{response.status_code}: {response.text}"
                print(f"Gemini API Error {response.status_code}")
                return {"sub_category": None, "error": error_msg}
        except Exception as e:
            error_msg = f"Request error: {str(e)}"
            print(f"Gemini Request Error: {e}")
            return {"sub_category": None, "error": error_msg}
    
    def classify(self, pair: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main classification method for GeminiClassifier.
        
        Classifies using AI and handles tagging.
        """
        to_commit = pair.get("to_commit") or pair.get("good_commit")
        msg = pair.get("to_msg") or pair.get("good_msg")
        
        # Get commit diff
        diff = self.get_commit_diff(to_commit)
        
        # Call AI API
        result = self._call_ai_api(msg, diff)
        ai_tag = result["sub_category"]
        error = result["error"]
        
        # Add AI tag to tags list if it's not None
        if ai_tag:
            if "tags" not in pair or pair["tags"] is None:
                pair["tags"] = []
            if ai_tag not in pair["tags"]:
                pair["tags"].append(ai_tag)
        
        # If there was an error, set category to "Unknown"
        if error:
            pair["category"] = "Unknown"
        
        pair["error"] = error
        
        return pair

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
            result = self._call_ai_api(msg, diff)
            ai_tag = result["sub_category"]
            error = result["error"]
            print(f"  Assigned Category: {ai_tag}")
            
            # Add AI tag to tags list if it's not None
            if ai_tag:
                if "tags" not in pair or pair["tags"] is None:
                    pair["tags"] = []
                if ai_tag not in pair["tags"]:
                    pair["tags"].append(ai_tag)
                print(f"  Assigned Tags: {', '.join(pair['tags'])}")
            
            # If there was an error, set category to "Unknown"
            if error:
                pair["category"] = "Unknown"
            
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
        print(f"Updated {input_file} with AI tag classifications")

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
