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

class GPTClassifier:
    def __init__(self, github_token: str, openai_key: str, repo_owner: str, repo_name: str):
        self.github_token = github_token
        self.openai_key = openai_key
        self.owner = repo_owner
        self.name = repo_name
        self.headers = {
            "Authorization": f"Bearer {github_token}",
            "Accept": "application/vnd.github.v3.diff"
        }
        self.openai_url = "https://api.openai.com/v1/chat/completions"
        self.openai_headers = {
            "Authorization": f"Bearer {openai_key}",
            "Content-Type": "application/json"
        }
        
        # Load categories from files
        self.categories = self._load_categories()
    
    def _load_categories(self) -> Dict[str, str]:
        """Loads category definitions from .txt files in classification/categories/"""
        categories = {}
        categories_dir = os.path.join(os.path.dirname(__file__), "categories")
        
        if not os.path.exists(categories_dir):
            print(f"Warning: Categories directory not found at {categories_dir}")
            return categories
        
        try:
            for filename in os.listdir(categories_dir):
                if filename.endswith(".txt"):
                    category_name = filename[:-4]  # Remove .txt extension
                    filepath = os.path.join(categories_dir, filename)
                    try:
                        with open(filepath, 'r') as f:
                            description = f.read().strip()
                            # Validate description: limit length and remove potentially harmful content
                            if len(description) > 500:
                                print(f"Warning: Description in {filename} exceeds 500 characters, truncating")
                                description = description[:500]
                            # Store sanitized description
                            categories[category_name] = description
                    except Exception as e:
                        print(f"Warning: Could not read category file {filename}: {e}")
        except Exception as e:
            print(f"Warning: Error reading categories directory: {e}")
        
        return categories

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

    def classify_with_gpt(self, message: str, diff: str) -> dict:
        """Asks GPT for sub-categorization using OpenAI API.
        
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
        
        prompt_text = f"""Analyze the following commit to determine its sub-category.

Commit Message:
{message}

Diff Snippet:
{diff}

Classify this commit into ONE of these categories:

{chr(10).join(category_descriptions)}

Answer with ONLY the category name from the list above."""
        
        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": "You are a code classification assistant. Respond with only the category name."},
                {"role": "user", "content": prompt_text}
            ],
            "temperature": 0.3,
            "max_tokens": 50
        }
        
        try:
            response = requests.post(self.openai_url, json=payload, headers=self.openai_headers, timeout=30)
            if response.status_code == 200:
                data = response.json()
                try:
                    answer = data["choices"][0]["message"]["content"].strip()
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
                    error_msg = f"Error parsing GPT response: {e}"
                    print(error_msg)
                    return {"sub_category": None, "error": error_msg}
            else:
                error_msg = f"{response.status_code}: {response.text}"
                print(f"OpenAI API Error {response.status_code}")
                return {"sub_category": None, "error": error_msg}
        except Exception as e:
            error_msg = f"Request error: {str(e)}"
            print(f"GPT Request Error: {e}")
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
        print(f"Classifying {len(pairs) - len(processed_commits)} remaining pairs with GPT...")
        
        new_count = 0
        
        for i, pair in enumerate(pairs):
            to_commit = pair.get("to_commit") or pair.get("good_commit")  # Support both formats
            
            if to_commit in processed_commits:
                print(f"[{i+1}/{len(pairs)}] Skipping {to_commit[:7]} (Already processed)")
                continue
                
            msg = pair.get("to_msg") or pair.get("good_msg")  # Support both formats
            
            print(f"[{i+1}/{len(pairs)}] Fetching diff for {to_commit[:7]}...")
            diff = self.get_commit_diff(to_commit)
            
            print(f"  Asking GPT...")
            result = self.classify_with_gpt(msg, diff)
            ai_tag = result["sub_category"]  # Still using sub_category key in return for now
            error = result["error"]
            print(f"  Assigned Category: {ai_tag}")
            
            # Add AI tag to tags list if it's not None
            if ai_tag:
                if "tags" not in pair or pair["tags"] is None:
                    pair["tags"] = []
                if ai_tag not in pair["tags"]:
                    pair["tags"].append(ai_tag)
                print(f"  Tagged: {', '.join(pair['tags'])}")
            
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
        print(f"Updated {input_file} with GPT tag classifications")

def main():
    load_env()
    parser = argparse.ArgumentParser(description="GPT Classifier")
    parser.add_argument("repo", help="owner/name")
    parser.add_argument("--input", help="Input file path (default: results/per_repo/{owner}_{name}.json)")
    
    args = parser.parse_args()
    
    gh_token = os.environ.get("GITHUB_TOKEN")
    openai_key = os.environ.get("OPENAI_API_KEY")
    
    if not gh_token or not openai_key:
        print("Error: GITHUB_TOKEN and OPENAI_API_KEY must be set.")
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
    
    classifier = GPTClassifier(gh_token, openai_key, owner, name)
    classifier.run(input_file)

if __name__ == "__main__":
    main()
