import argparse
import subprocess
import sys
import os
import json
import signal
from contextlib import contextmanager
from mining.mine_common import load_env

@contextmanager
def timeout_context(seconds, repo_name):
    """Context manager for timing out operations."""
    def timeout_handler(signum, frame):
        raise TimeoutError(f"Repository {repo_name} processing exceeded {seconds} second timeout")
    
    # Set up the timeout
    old_handler = signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        # Restore the old handler and cancel the alarm
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)

def run_step(command, description):
    try:
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error during '{description}': {e}")
        sys.exit(1)

def prime_cache_for_repo(repo, mining_type):
    """
    Prime the cache for a repository based on mining type.
    
    Args:
        repo: Repository in owner/name format
        mining_type: Type of mining ('prs' or 'commits')
    """
    if "/" not in repo:
        print(f"Skipping invalid repo format: {repo}")
        return
    
    owner, name = repo.split("/", 1)
    token = os.environ.get("GITHUB_TOKEN")
    
    if not token:
        print("Error: GITHUB_TOKEN not found")
        return
    
    print(f"\n*** CACHE PRIMING: {repo} ***")
    
    if mining_type == "prs":
        from mining.mine_prs import PRMiner
        from mining.cache import CacheManager, prime_pr_cache, MAX_CACHE_ITEMS_PRS
        
        miner = PRMiner(token, owner, name)
        cache_manager = CacheManager(owner, name, "prs")
        
        prime_pr_cache(miner, cache_manager, max_items=MAX_CACHE_ITEMS_PRS)
        
    elif mining_type == "commits":
        from mining.mine_commits import CommitMiner
        from mining.cache import CacheManager, prime_commit_cache, MAX_CACHE_ITEMS_COMMITS
        
        miner = CommitMiner(token, owner, name)
        cache_manager = CacheManager(owner, name, "commits")
        
        # Detect default branch
        ref = miner.get_default_branch()
        
        prime_commit_cache(miner, cache_manager, ref, max_items=MAX_CACHE_ITEMS_COMMITS)


def run_mining(repo, search_limit, results_limit, mining_type, output_dir, state_dir):
    """
    Run mining based on the specified type.
    
    Returns:
        Path to the mining output file to use for classification, or None
    """
    # Get owner and name for per_repo structure
    if "/" not in repo:
        return None
    owner, name = repo.split("/", 1)
    
    # Ensure per_repo directory exists before constructing path
    per_repo_dir = os.path.join(output_dir, "per_repo")
    os.makedirs(per_repo_dir, exist_ok=True)
    
    # New per_repo structure
    per_repo_output = os.path.join(per_repo_dir, f"{owner}_{name}.json")
    
    # Build limit arguments
    limit_args = []
    if search_limit:
        limit_args.extend(["--search-limit", str(search_limit)])
    if results_limit:
        limit_args.extend(["--results-limit", str(results_limit)])
    
    # Mine based on type (no header output)
    classification_input = None
    
    if mining_type == "prs":
        run_step(
            ["python3", "-m", "mining.mine_prs", repo] + limit_args + ["--output", "results", "--state", state_dir],
            f"Step 1: Mining 'Bad -> Good' Pairs for {repo}"
        )
        classification_input = per_repo_output
    elif mining_type == "commits":
        run_step(
            ["python3", "-m", "mining.mine_commits", repo] + limit_args + ["--output", "results", "--state", state_dir],
            f"Step 1: Mining Commit Pairs for {repo}"
        )
        classification_input = per_repo_output
    
    return classification_input

# Fields to clear during reclassification
RECLASSIFY_FIELDS = ['category', 'tags', 'error']

def run_classification(repo, classifier, classification_input, reclassify=False):
    """
    Run classification based on the specified classifier.
    Edits the per_repo file in-place.
    
    Args:
        repo: Repository name
        classifier: Type of classifier to use
        classification_input: Path to the input file
        reclassify: If True, clears category and tags fields before classification
    """
    if not classification_input or not os.path.exists(classification_input):
        return
    
    # If reclassify is enabled, clear category and tags fields
    if reclassify:
        try:
            with open(classification_input, 'r') as f:
                results = json.load(f)
            
            # Clear classification fields
            for result in results:
                for field in RECLASSIFY_FIELDS:
                    if field == 'tags':
                        result[field] = []
                    else:
                        result[field] = None
            
            # Save the cleared results
            with open(classification_input, 'w') as f:
                json.dump(results, f, indent=2)
            
            print(f"Cleared {', '.join(RECLASSIFY_FIELDS)} fields for {len(results)} results in {classification_input}")
        except Exception as e:
            print(f"Error clearing classification fields: {e}")
    
    # Simple/Heuristic Classification (runs on any mining type)
    if classifier == "simple":
        run_step(
            ["python3", "-m", "classification.simple_classifier", repo, "--input", classification_input],
            f"Running Simple Classifier for {repo}"
        )
    
    # Gemini Classification (runs on any mining type)
    elif classifier == "gemini":
        # AI classifier needs analyzed results, so run simple first as prerequisite
        run_step(
            ["python3", "-m", "classification.simple_classifier", repo, "--input", classification_input],
            f"Running Simple Classifier for {repo} (prerequisite for Gemini)"
        )
        run_step(
            ["python3", "-m", "classification.gemini_classifier", repo, "--input", classification_input],
            f"Running Gemini Classification for {repo}"
        )
    
    # GPT Classification (runs on any mining type)
    elif classifier == "gpt":
        # GPT classifier needs analyzed results, so run simple first as prerequisite
        run_step(
            ["python3", "-m", "classification.simple_classifier", repo, "--input", classification_input],
            f"Running Simple Classifier for {repo} (prerequisite for GPT)"
        )
        run_step(
            ["python3", "-m", "classification.gpt_classifier", repo, "--input", classification_input],
            f"Running GPT Classification for {repo}"
        )

def process_repo(repo, search_limit, results_limit, mining_type, classifier, timeout_seconds, reclassify):
    print(f"\n*** PROCESSING REPO: {repo} ***")
    
    if "/" not in repo:
        print(f"Skipping invalid repo format: {repo}")
        return

    owner, name = repo.split("/", 1)
    output_dir = "results"
    state_dir = ".state"
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(state_dir, exist_ok=True)
    
    # Mining
    classification_input = run_mining(repo, search_limit, results_limit, mining_type, output_dir, state_dir)
    
    # Classification
    run_classification(repo, classifier, classification_input, reclassify)

def aggregate_results():
    """
    Step 3: Aggregation - Combine all per_repo files into a single results.json
    """
    per_repo_dir = os.path.join("results", "per_repo")
    output_file = os.path.join("results", "results.json")
    
    all_results = []
    file_count = 0
    
    if os.path.exists(per_repo_dir):
        # Read all JSON files from per_repo directory
        for filename in os.listdir(per_repo_dir):
            if filename.endswith(".json"):
                filepath = os.path.join(per_repo_dir, filename)
                try:
                    with open(filepath, 'r') as f:
                        data = json.load(f)
                        if isinstance(data, list):
                            all_results.extend(data)
                            file_count += 1
                            print(f"Added {len(data)} results from {filename}")
                        else:
                            print(f"Warning: {filename} does not contain a list, skipping")
                except Exception as e:
                    print(f"Error reading {filename}: {e}")
    else:
        print(f"No per_repo directory found at {per_repo_dir}")
    
    # Always write results file, even if empty
    from mining.mine_common import ensure_directory
    ensure_directory(os.path.dirname(output_file))
    
    with open(output_file, 'w') as f:
        json.dump(all_results, f, indent=2)
    
    if all_results:
        print(f"\n✓ Aggregated {len(all_results)} total results from {file_count} repositories into {output_file}")
    else:
        print(f"\n✓ Created empty results file at {output_file}")

def validate_tokens(classifier):
    """
    Step 0: Validate that required tokens are set.
    
    Args:
        classifier: The classifier type to determine which tokens are needed
    """
    missing_tokens = []
    
    # GITHUB_TOKEN is always required
    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        missing_tokens.append("GITHUB_TOKEN")
    else:
        print("✓ GITHUB_TOKEN is set")
    
    # GEMINI_API_KEY is required if using Gemini classification
    if classifier == "gemini":
        gemini_key = os.getenv("GEMINI_API_KEY")
        if not gemini_key:
            missing_tokens.append("GEMINI_API_KEY")
        else:
            print("✓ GEMINI_API_KEY is set")
    
    # OPENAI_API_KEY is required if using GPT classification
    if classifier == "gpt":
        openai_key = os.getenv("OPENAI_API_KEY")
        if not openai_key:
            missing_tokens.append("OPENAI_API_KEY")
        else:
            print("✓ OPENAI_API_KEY is set")
    
    if missing_tokens:
        print(f"\n❌ Error: The following required environment variables are not set:")
        for token in missing_tokens:
            print(f"   - {token}")
        print("\nPlease ensure you have a .env file in the project root with these variables.")
        print("Example .env format:")
        print("GITHUB_TOKEN=your_github_token_here")
        if classifier == "gemini":
            print("GEMINI_API_KEY=your_gemini_api_key_here")
        if classifier == "gpt":
            print("OPENAI_API_KEY=your_openai_api_key_here")
        sys.exit(1)
    
    print("\n✓ All required tokens are set")

def main():
    parser = argparse.ArgumentParser(description="Run the full Task Mining Pipeline")
    parser.add_argument("repo_or_file", help="GitHub repository (owner/name) OR path to a text file with a list of repos")
    parser.add_argument("--search-limit", type=int, help="Maximum number of PRs/commits to search through (stops after searching this many items)")
    parser.add_argument("--results-limit", type=int, help="Maximum number of valid results to find (stops after finding this many valid pairs)")
    parser.add_argument("--timeout", type=int, default=120, help="Timeout in seconds for processing each repository (default: 120)")
    parser.add_argument("--clean", action="store_true", help="Clean previous results/state before running (deletes entire results/ and .state/ directories)")
    parser.add_argument("--clean-cache", action="store_true", help="Clean cache before running (deletes entire .cache/ directory)")
    parser.add_argument("--reclassify", action="store_true", help="Clear category and tags fields before re-running classification")
    parser.add_argument("--type", default="prs", choices=["prs", "commits"],
                       help="Type of mining to run (Step 1): 'prs' (PR-based bad->good) or 'commits' (commit-based pairs with successful builds). Default: prs")
    parser.add_argument("--classifier", default="simple", choices=["simple", "gemini", "gpt"],
                       help="Classification to run (Steps 2 and 2b): 'simple' (heuristic), 'gemini' (Gemini API), or 'gpt' (OpenAI GPT). AI classifiers automatically run simple as prerequisite. Runs on the mining results from Step 1. Default: simple")
    
    args = parser.parse_args()
    
    # Validate that at least one limit is specified
    if not args.search_limit and not args.results_limit:
        parser.error("At least one of --search-limit or --results-limit must be specified")
    
    print(f"\n{'='*60}")
    print("INITIALIZATION")
    print(f"{'='*60}")
    
    # Step 0: Load environment variables and validate tokens
    load_env()
    validate_tokens(args.classifier)
    
    # Clean cache if requested (done first, before anything else)
    if args.clean_cache:
        import shutil
        from mining.cache import CacheManager
        CacheManager.clear_all_caches()
        
        # Also clean commit diff cache
        commit_cache_dir = os.path.join(".cache", "commit_contents")
        if os.path.exists(commit_cache_dir):
            print(f"Cleaning {commit_cache_dir}/ directory...")
            shutil.rmtree(commit_cache_dir)
            print(f"Removed {commit_cache_dir}/")
    
    # Clean entire results and state directories if requested (done first, before processing any repos)
    if args.clean:
        import shutil
        results_dir = "results"
        state_dir = ".state"
        
        if os.path.exists(results_dir):
            print(f"Cleaning entire {results_dir}/ directory...")
            shutil.rmtree(results_dir)
            print(f"Removed {results_dir}/")
        
        if os.path.exists(state_dir):
            print(f"Cleaning entire {state_dir}/ directory...")
            shutil.rmtree(state_dir)
            print(f"Removed {state_dir}/")
        
        print("Clean complete.")
    
    repos = []
    if os.path.isfile(args.repo_or_file):
        with open(args.repo_or_file, 'r') as f:
            repos = [line.strip() for line in f if line.strip() and not line.startswith("#")]
        print(f"Loaded {len(repos)} repositories from {args.repo_or_file}")
    else:
        repos = [args.repo_or_file]
    
    repo_word = "repository" if len(repos) == 1 else "repositories"
    print(f"Processing {len(repos)} {repo_word} with {args.timeout} second timeout per repo")
    
    # Prime cache for all repos first (with timeout protection)
    for repo in repos:
        try:
            with timeout_context(args.timeout, repo):
                prime_cache_for_repo(repo, args.type)
        except TimeoutError as e:
            print(f"\n{'!'*60}")
            print(f"TIMEOUT during cache priming: {e}")
            print(f"{'!'*60}")
            print(f"Skipping cache priming for {repo}, will fetch from GitHub during mining...")
        except Exception as e:
            print(f"Failed to prime cache for {repo}: {e}")
            # Continue to next repo
    
    print(f"\n{'='*60}")
    print("PROCESSING REPOSITORIES")
    print(f"{'='*60}")
    
    for repo in repos:
        try:
            with timeout_context(args.timeout, repo):
                process_repo(repo, args.search_limit, args.results_limit, args.type, args.classifier, args.timeout, args.reclassify)
        except TimeoutError as e:
            print(f"\n{'!'*60}")
            print(f"TIMEOUT: {e}")
            print(f"{'!'*60}")
            print(f"Skipping {repo} and continuing to next repository...")
            # Continue to next repo
        except Exception as e:
            print(f"Failed to process {repo}: {e}")
            # Continue to next repo
    
    print(f"\n{'='*60}")
    print("GENERATING REPORT")
    print(f"{'='*60}\n")
    
    # Step 3: Aggregate all results into a single file
    aggregate_results()
    
    # Step 4: Build dashboard
    from reporting.build_dashboard import build_dashboard
    build_dashboard()
    
    print(f"\n{'='*60}")
    print("FINISHED!")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
