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
from classification.classification_cache import ClassificationCacheManager, compute_classification_hash

class GeminiClassifier(BaseAIClassifier):
    def __init__(self, github_token: str, gemini_key: str, repo_owner: str, repo_name: str):
        super().__init__(github_token, gemini_key, repo_owner, repo_name)
        self.gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={gemini_key}"
        self.cache_manager = ClassificationCacheManager("gemini")
    
    def _call_ai_api(self, message: str, diff: str) -> dict:
        """Asks Gemini for categorization and tags using REST API.
        
        Returns:
            dict with 'category', 'tags', and 'error' keys. 
            If successful, error is None. If failed, category defaults to "Other" and error contains descriptive message.
        """
        if not diff:
            return {"category": "Other", "tags": [], "error": "No diff available"}
        
        if not self.categories:
            return {"category": "Other", "tags": [], "error": "No categories loaded"}
        
        # Build category descriptions dynamically
        category_descriptions = []
        for category_name, description in self.categories.items():
            category_descriptions.append(f"**{category_name}**: {description}")
        
        # Build tag descriptions dynamically
        tag_descriptions = []
        for tag_name, description in self.tags.items():
            tag_descriptions.append(f"**{tag_name}**: {description}")
        
        prompt_text = f"""
        Analyze the following commit and provide:
        (1) ONE category from the list below
        (2) ALL applicable tags from the tag list below
        
        Commit Message:
        {message}
        
        Diff Snippet:
        {diff}
        
        CATEGORIES (choose exactly ONE):
        {chr(10).join(category_descriptions)}
        
        TAGS (choose ALL that apply):
        {chr(10).join(tag_descriptions)}
        
        Respond in this format:
        Category: [category name]
        Tags: [tag1, tag2, tag3] (or "none" if no tags apply)
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
                    
                    # Parse category
                    category = "Other"
                    for line in answer.split('\n'):
                        if line.lower().startswith('category:'):
                            cat_text = line.split(':', 1)[1].strip()
                            for category_name in self.categories.keys():
                                if category_name.lower() in cat_text.lower():
                                    category = category_name
                                    break
                            break
                    
                    # Parse tags
                    tags = []
                    for line in answer.split('\n'):
                        if line.lower().startswith('tags:'):
                            tags_text = line.split(':', 1)[1].strip()
                            if tags_text.lower() != 'none' and tags_text != '[]':
                                # Extract tags from comma-separated list or bracketed list
                                tags_text = tags_text.strip('[]')
                                for tag_candidate in tags_text.split(','):
                                    tag_candidate = tag_candidate.strip()
                                    for tag_name in self.tags.keys():
                                        if tag_name.lower() in tag_candidate.lower():
                                            if tag_name not in tags:
                                                tags.append(tag_name)
                            break
                    
                    return {"category": category, "tags": tags, "error": None}
                except (KeyError, IndexError) as e:
                    error_msg = f"Error parsing Gemini response: {e}"
                    print(error_msg)
                    return {"category": "Other", "tags": [], "error": error_msg}
            else:
                error_msg = f"{response.status_code}: {response.text}"
                print(f"Gemini API Error {response.status_code}")
                return {"category": "Other", "tags": [], "error": error_msg}
        except Exception as e:
            error_msg = f"Request error: {str(e)}"
            print(f"Gemini Request Error: {e}")
            return {"category": "Other", "tags": [], "error": error_msg}
    
    def classify(self, pair: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main classification method for GeminiClassifier.
        
        Classifies using AI and handles tagging.
        """
        to_commit = pair.get("to_commit") or pair.get("good_commit")
        msg = pair.get("to_msg") or pair.get("good_msg")
        
        # Get commit diff
        diff = self.get_commit_diff(to_commit)
        
        # Call AI API - this returns both category and tags in one call
        result = self._call_ai_api(msg, diff)
        category = result["category"]
        ai_tags = result["tags"]
        error = result["error"]
        
        # Set category
        pair["category"] = category
        
        # Initialize tags if not present
        if "tags" not in pair or pair["tags"] is None:
            pair["tags"] = []
        
        # Add AI tags
        for tag in ai_tags:
            if tag not in pair["tags"]:
                pair["tags"].append(tag)
        
        # Check for single-line changes and add "one-line" tag if applicable
        if diff:
            # Simple heuristic: check if diff contains only one + and one - line
            lines = diff.split('\n')
            additions = sum(1 for line in lines if line.startswith('+') and not line.startswith('+++'))
            deletions = sum(1 for line in lines if line.startswith('-') and not line.startswith('---'))
            if additions == 1 and deletions == 1:
                if "one-line" not in pair["tags"]:
                    pair["tags"].append("one-line")
        
        pair["error"] = error
        
        return pair

    def run(self, input_file: str, reclassify: bool = False):
        """Classifies pairs in-place, updating the category and tags fields.
        
        Args:
            input_file: Path to the JSON file containing pairs to classify
            reclassify: If True, ignore cache and reclassify all items
        """
        if not os.path.exists(input_file):
            print(f"Error: Input file {input_file} not found.")
            return

        with open(input_file, 'r') as f:
            pairs = json.load(f)
        
        # Compute current classification hash
        current_hash = compute_classification_hash()
        print(f"Current classification hash: {current_hash[:8]}...")
            
        # Track which commits have been processed with category
        processed_commits = set()
        for pair in pairs:
            to_commit = pair.get("to_commit") or pair.get("good_commit")
            category = pair.get("category")
            if category is not None and category != "":
                processed_commits.add(to_commit)
        
        # Count how many need classification based on cache
        items_to_classify = []
        items_skipped = 0
        
        for pair in pairs:
            to_commit = pair.get("to_commit") or pair.get("good_commit")
            pr_id = pair.get("pr_id")
            
            # Use PR ID if available, otherwise use commit hash as identifier
            item_id = str(pr_id) if pr_id else to_commit
            
            # Skip if already has category and cache says no reclassification needed
            if to_commit in processed_commits:
                if not self.cache_manager.needs_classification(item_id, current_hash, reclassify):
                    items_skipped += 1
                    continue
            
            items_to_classify.append((item_id, pair))
        
        if items_skipped > 0:
            print(f"Skipping classification for {items_skipped} items (no changes to classification configuration)")
                
        print(f"Found {len(processed_commits)} already classified pairs.")
        print(f"Classifying {len(items_to_classify)} pairs with Gemini...")
        
        new_count = 0
        
        for i, (item_id, pair) in enumerate(items_to_classify):
            to_commit = pair.get("to_commit") or pair.get("good_commit")
            msg = pair.get("to_msg") or pair.get("good_msg")
            
            print(f"[{i+1}/{len(items_to_classify)}] Fetching diff for {to_commit[:7]}...")
            diff = self.get_commit_diff(to_commit)
            
            print(f"  Asking Gemini...")
            result = self._call_ai_api(msg, diff)
            category = result["category"]
            ai_tags = result["tags"]
            error = result["error"]
            
            print(f"  Assigned Category: {category}")
            
            # Set category
            pair["category"] = category
            
            # Initialize tags if not present
            if "tags" not in pair or pair["tags"] is None:
                pair["tags"] = []
            
            # Add AI tags
            for tag in ai_tags:
                if tag not in pair["tags"]:
                    pair["tags"].append(tag)
            
            # Check for single-line changes and add "one-line" tag if applicable
            if diff:
                lines = diff.split('\n')
                additions = sum(1 for line in lines if line.startswith('+') and not line.startswith('+++'))
                deletions = sum(1 for line in lines if line.startswith('-') and not line.startswith('---'))
                if additions == 1 and deletions == 1:
                    if "one-line" not in pair["tags"]:
                        pair["tags"].append("one-line")
            
            print(f"  Assigned Tags: {', '.join(pair['tags'])}")
            
            pair["error"] = error
            processed_commits.add(to_commit)
            new_count += 1
            
            # Update cache with current hash for this item
            self.cache_manager.set_cached_hash(item_id, current_hash)
            
            # Save incrementally every 5 items
            if new_count % 5 == 0:
                with open(input_file, 'w') as f:
                    json.dump(pairs, f, indent=2)
                print(f"  [Saved progress to {input_file}]")
            
            time.sleep(1)
            
        # Final save
        with open(input_file, 'w') as f:
            json.dump(pairs, f, indent=2)
        print(f"Updated {input_file} with category and tag classifications")

def main():
    load_env()
    parser = argparse.ArgumentParser(description="Gemini Classifier")
    parser.add_argument("repo", help="owner/name")
    parser.add_argument("--input", help="Input file path (default: results/per_repo/{owner}_{name}.json)")
    parser.add_argument("--reclassify", action="store_true", help="Force reclassification even if already classified")
    
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
    classifier.run(input_file, reclassify=args.reclassify)

if __name__ == "__main__":
    main()
