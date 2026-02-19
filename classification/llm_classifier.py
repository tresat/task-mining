import os
import json
import time
import argparse
import requests
from abc import abstractmethod
from typing import List, Dict, Any, Optional
import sys
import litellm

# Add parent directory to path to import from mining
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from mining.mine_common import load_env
from classification.base_classifier import BaseClassifier
from classification.classification_cache import ClassificationCacheManager, compute_classification_hash

# Maximum characters to fetch from commit diff (to avoid excessive API response sizes)
COMMIT_DIFF_MAX_LENGTH = 10000

class LLMClassifier(BaseClassifier):
    """
    LLM-powered classifier using LiteLLM for categorization and tagging.
    
    This classifier uses AI to:
    - Categorize commits based on their message and diff
    - Add descriptive tags
    - Provide a brief summary of changes
    """
    
    def __init__(self, github_token: str, model: str, repo_owner: str, repo_name: str):
        super().__init__(github_token, repo_owner, repo_name)
        self.model = model
        
        # Load category and tag definitions
        self.categories = self._load_categories()
        self.tags = self._load_tags()
        
        # Per-repo cache directory for commit diffs
        self.commit_diff_cache_dir = os.path.join(".cache", "repos", f"{self.owner}_{self.name}", "commit_contents")
        
        # Classification cache management
        cache_name = f"llm_{model.replace('/', '_')}"
        self.cache_manager = ClassificationCacheManager(cache_name, repo_owner, repo_name)
    
    def _load_categories(self) -> Dict[str, str]:
        """
        Loads category definitions from .txt files in classification/categories/.
        """
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
                            # Validate description: limit length
                            if len(description) > 500:
                                print(f"Warning: Description in {filename} exceeds 500 characters, truncating")
                                description = description[:500]
                            categories[category_name] = description
                    except Exception as e:
                        print(f"Warning: Could not read category file {filename}: {e}")
        except Exception as e:
            print(f"Warning: Error reading categories directory: {e}")
        
        return categories
    
    def _load_tags(self) -> Dict[str, str]:
        """
        Loads tag definitions from .txt files in classification/tags/.
        """
        tags = {}
        tags_dir = os.path.join(os.path.dirname(__file__), "tags")
        
        if not os.path.exists(tags_dir):
            print(f"Warning: Tags directory not found at {tags_dir}")
            return tags
        
        try:
            for filename in os.listdir(tags_dir):
                if filename.endswith(".txt"):
                    tag_name = filename[:-4]  # Remove .txt extension
                    filepath = os.path.join(tags_dir, filename)
                    try:
                        with open(filepath, 'r') as f:
                            description = f.read().strip()
                            # Validate description: limit length
                            if len(description) > 500:
                                print(f"Warning: Description in {filename} exceeds 500 characters, truncating")
                                description = description[:500]
                            tags[tag_name] = description
                    except Exception as e:
                        print(f"Warning: Could not read tag file {filename}: {e}")
        except Exception as e:
            print(f"Warning: Error reading tags directory: {e}")
        
        return tags
    
    def get_commit_diff(self, commit_sha: str) -> str:
        """
        Fetches the diff of a commit from GitHub.
        
        This method uses caching to avoid redundant API calls.
        Cache location: .cache/repos/{owner}_{name}/commit_contents/{commit_sha}.txt
        """
        # Validate commit_sha to prevent path traversal attacks
        if not commit_sha or not all(c in '0123456789abcdefABCDEF' for c in commit_sha):
            print(f"Invalid commit SHA format: {commit_sha}")
            return ""
        
        # Define cache path
        cache_file = os.path.join(self.commit_diff_cache_dir, f"{commit_sha}.txt")
        
        # Check if diff exists in cache
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    diff_content = f.read()
                print(f"Using cached diff for {commit_sha}")
                return diff_content
            except Exception as e:
                print(f"Error reading cached diff for {commit_sha}: {e}")
        
        # Fetch from GitHub API
        url = f"https://api.github.com/repos/{self.owner}/{self.name}/commits/{commit_sha}"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github.v3.diff"
        }
        try:
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code == 200:
                diff_content = response.text[:COMMIT_DIFF_MAX_LENGTH]  # Truncate
                
                # Save to cache
                try:
                    os.makedirs(self.commit_diff_cache_dir, exist_ok=True)
                    with open(cache_file, 'w', encoding='utf-8') as f:
                        f.write(diff_content)
                    print(f"Cached diff for {commit_sha}")
                except Exception as e:
                    print(f"Warning: Could not cache diff for {commit_sha}: {e}")
                
                return diff_content
            else:
                print(f"Failed to fetch diff for {commit_sha}: {response.status_code}")
                return ""
        except Exception as e:
            print(f"Error fetching diff for {commit_sha}: {e}")
            return ""

    def check_dependencies(self, pair: Dict[str, Any]) -> bool:
        """
        Uses AI API to determine if the change is dependency-related.
        
        For LLM classifier, this is handled in the classify method
        by adding tags based on AI response.
        """
        return False
    
    def check_version_update(self, pair: Dict[str, Any], file_info: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Uses AI API to determine if the change is a version update.
        
        For LLM classifier, this is handled in the classify method
        by adding tags based on AI response.
        """
        return None

    def _call_ai_api(self, message: str, diff: str) -> dict:
        """Asks the LLM for categorization, tags, and summary using LiteLLM.
        
        Returns:
            dict with 'category', 'tags', 'summary', and 'error' keys. 
            If successful, error is None. If failed, category defaults to "Other" and error contains descriptive message.
        """
        if not diff:
            return {"category": "Other", "tags": [], "summary": message, "error": "No diff available"}
        
        if not self.categories:
            return {"category": "Other", "tags": [], "summary": message, "error": "No categories loaded"}
        
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
        (3) A brief summary (maximum 3 sentences) of the changes
        
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
        Summary: [brief summary in 3 sentences or less]
        """
        
        try:
            response = litellm.completion(
                model=self.model,
                messages=[{"role": "user", "content": prompt_text}],
                temperature=0.3,
                max_tokens=500
            )
            
            answer = response.choices[0].message.content.strip()
            
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
            
            # Parse summary
            summary = message  # Default to message if summary not found
            summary_lines = []
            in_summary = False
            for line in answer.split('\n'):
                if line.lower().startswith('summary:'):
                    summary_text = line.split(':', 1)[1].strip()
                    if summary_text:
                        summary_lines.append(summary_text)
                    in_summary = True
                elif in_summary and line.strip():
                    # Continue capturing summary lines
                    summary_lines.append(line.strip())
            
            if summary_lines:
                summary = ' '.join(summary_lines)
            
            return {"category": category, "tags": tags, "summary": summary, "error": None}
            
        except Exception as e:
            error_msg = f"LiteLLM error ({self.model}): {str(e)}"
            print(error_msg)
            return {"category": "Other", "tags": [], "summary": message, "error": error_msg}
    
    def classify(self, pair: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main classification method for LLMClassifier.
        """
        to_commit = pair.get("to_commit") or pair.get("good_commit")
        msg = pair.get("to_msg") or pair.get("good_msg")
        
        # Get commit diff
        diff = self.get_commit_diff(to_commit)
        
        # Call AI API
        result = self._call_ai_api(msg, diff)
        
        # Set category and summary
        pair["category"] = result["category"]
        pair["summary"] = result["summary"]
        
        # Initialize tags if not present
        if "tags" not in pair or pair["tags"] is None:
            pair["tags"] = []
        
        # Add AI tags
        for tag in result["tags"]:
            if tag not in pair["tags"]:
                pair["tags"].append(tag)
        
        # Check for single-line changes
        if diff:
            lines = diff.split('\n')
            additions = sum(1 for line in lines if line.startswith('+') and not line.startswith('+++'))
            deletions = sum(1 for line in lines if line.startswith('-') and not line.startswith('---'))
            if additions == 1 and deletions == 1:
                if "one-line" not in pair["tags"]:
                    pair["tags"].append("one-line")
        
        pair["error"] = result["error"]
        
        return pair

    def run(self, input_file: str, reclassify: bool = False):
        """Classifies pairs in-place."""
        if not os.path.exists(input_file):
            print(f"Error: Input file {input_file} not found.")
            return

        with open(input_file, 'r') as f:
            pairs = json.load(f)
        
        current_hash = compute_classification_hash()
        
        if not reclassify:
            hash_changed = self.cache_manager.check_and_update_hash(current_hash)
            if hash_changed:
                print(f"Configuration changed - cache cleared for {self.owner}/{self.name}")
        else:
            self.cache_manager.clear_cache()
            print(f"Reclassification requested - cache cleared for {self.owner}/{self.name}")
        
        classified_count = 0
        skipped_count = 0
        
        for pair in pairs:
            to_commit = pair.get("to_commit") or pair.get("good_commit")
            pr_id = pair.get("pr_id")
            item_id = str(pr_id) if pr_id else to_commit
            
            cached_result = self.cache_manager.get_cached_result(item_id)
            
            if cached_result is not None and not reclassify:
                pair["category"] = cached_result["category"]
                pair["tags"] = cached_result["tags"]
                pair["summary"] = cached_result.get("summary")
                pair["error"] = cached_result["error"]
                skipped_count += 1
            else:
                msg = pair.get("to_msg") or pair.get("good_msg")
                print(f"[{classified_count + 1}] Classifying {to_commit[:7]} with {self.model}...")
                
                # Use the logic from self.classify() but with logging
                diff = self.get_commit_diff(to_commit)
                result = self._call_ai_api(msg, diff)
                
                pair["category"] = result["category"]
                pair["summary"] = result["summary"]
                if "tags" not in pair or pair["tags"] is None:
                    pair["tags"] = []
                
                for tag in result["tags"]:
                    if tag not in pair["tags"]:
                        pair["tags"].append(tag)
                
                if diff:
                    lines = diff.split('\n')
                    adds = sum(1 for l in lines if l.startswith('+') and not l.startswith('+++'))
                    dels = sum(1 for l in lines if l.startswith('-') and not l.startswith('---'))
                    if adds == 1 and dels == 1:
                        if "one-line" not in pair["tags"]:
                            pair["tags"].append("one-line")
                
                pair["error"] = result["error"]
                print(f"  Category: {pair['category']}, Tags: {pair['tags']}")
                
                classified_count += 1
                self.cache_manager.set_cached_result(item_id, pair["category"], pair["tags"], pair.get("summary"), pair["error"])
                
                if classified_count % 5 == 0:
                    with open(input_file, 'w') as f:
                        json.dump(pairs, f, indent=2)
                
                time.sleep(0.5) # LiteLLM might need a bit of pacing for some APIs
        
        if skipped_count > 0:
            print(f"Skipped {skipped_count} items (cached)")
        print(f"Classified {classified_count} items with {self.model}")
        
        with open(input_file, 'w') as f:
            json.dump(pairs, f, indent=2)

def main():
    load_env()
    parser = argparse.ArgumentParser(description="LLM Classifier using LiteLLM")
    parser.add_argument("repo", help="owner/name")
    parser.add_argument("--model", default="gemini/gemini-2.0-flash", help="Model name for LiteLLM")
    parser.add_argument("--input", help="Input file path")
    parser.add_argument("--reclassify", action="store_true", help="Force reclassification")
    
    args = parser.parse_args()
    
    gh_token = os.environ.get("GITHUB_TOKEN")
    if not gh_token:
        print("Error: GITHUB_TOKEN must be set.")
        return
        
    owner, name = args.repo.split("/", 1)
    input_file = args.input or os.path.join("results", "per_repo", f"{owner}_{name}.json")
    
    if not os.path.exists(input_file):
        print(f"Error: Input file {input_file} not found.")
        return
    
    classifier = LLMClassifier(gh_token, args.model, owner, name)
    classifier.run(input_file, reclassify=args.reclassify)

if __name__ == "__main__":
    main()
