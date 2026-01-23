import argparse
import subprocess
import sys
import os
import signal
from contextlib import contextmanager
from mining.common import load_env

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
    print(f"\n{'='*60}")
    print(f"STEP: {description}")
    print(f"CMD: {' '.join(command)}")
    print(f"{'='*60}\n")
    
    try:
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error during '{description}': {e}")
        sys.exit(1)

def run_mining(repo, search_limit, results_limit, mining_type, output_dir, state_dir):
    """
    Run Step 1: Mining based on the specified type.
    
    Returns:
        Path to the mining output file to use for classification, or None
    """
    # Define filenames within the repo-specific directory
    mining_output = os.path.join(output_dir, "mining_results.json")
    simple_dep_output = os.path.join(output_dir, "simple_dependency_updates.json")
    
    # Build limit arguments
    limit_args = []
    if search_limit:
        limit_args.extend(["--search-limit", str(search_limit)])
    if results_limit:
        limit_args.extend(["--results-limit", str(results_limit)])
    
    # Step 1: Mine based on type
    # Determine which mining output to use for classification
    classification_input = None
    
    if mining_type == "fixes":
        run_step(
            ["python3", "-m", "mining.mine_fixes", repo] + limit_args + ["--output", "results", "--state", state_dir],
            f"Step 1: Mining 'Bad -> Good' Pairs for {repo}"
        )
        classification_input = mining_output
    elif mining_type == "simple-dep-updates":
        run_step(
            ["python3", "-m", "mining.mine_simple_dependency_updates", repo] + limit_args + ["--output", "results", "--state", state_dir],
            f"Step 1: Mining Simple Dependency Updates for {repo}"
        )
        classification_input = simple_dep_output
    
    return classification_input

def run_classification(repo, classifier, classification_input, output_dir):
    """
    Run Steps 2 and 2b: Classification based on the specified classifier.
    """
    if not classification_input:
        return
    
    analyzed_output = os.path.join(output_dir, "analyzed_results.json")
    ai_output = os.path.join(output_dir, "ai_classified_results.json")
    
    # Step 2: Simple/Heuristic Classification (runs on any mining type)
    if classifier == "simple":
        run_step(
            ["python3", "-m", "classification.analyze_pairs", repo, "--input", classification_input, "--output", analyzed_output],
            f"Step 2: Running Simple/Heuristic Classification for {repo}"
        )
    
    # Step 2b: AI Classification (runs on any mining type)
    elif classifier == "ai":
        # AI classifier needs analyzed results, so run simple first as prerequisite
        run_step(
            ["python3", "-m", "classification.analyze_pairs", repo, "--input", classification_input, "--output", analyzed_output],
            f"Step 2: Running Simple/Heuristic Classification for {repo} (prerequisite for AI)"
        )
        run_step(
            ["python3", "-m", "classification.gemini_classifier", repo, "--input", analyzed_output, "--output", ai_output],
            f"Step 2b: Running AI Classification (Gemini) for {repo}"
        )

def process_repo(repo, search_limit, results_limit, mining_type, classifier, timeout_seconds):
    print(f"\n{'#'*60}")
    print(f"PROCESSING REPO: {repo}")
    print(f"{'#'*60}\n")
    
    if "/" not in repo:
        print(f"Skipping invalid repo format: {repo}")
        return

    owner, name = repo.split("/", 1)
    output_dir = os.path.join("results", f"{owner}_{name}")
    state_dir = ".state"
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(state_dir, exist_ok=True)
    
    # Step 1: Mining
    classification_input = run_mining(repo, search_limit, results_limit, mining_type, output_dir, state_dir)
    
    # Steps 2 and 2b: Classification
    run_classification(repo, classifier, classification_input, output_dir)

def validate_tokens(classifier):
    """
    Step 0: Validate that required tokens are set.
    
    Args:
        classifier: The classifier type to determine which tokens are needed
    """
    print(f"\n{'='*60}")
    print("Step 0: Validating Environment Tokens")
    print(f"{'='*60}\n")
    
    missing_tokens = []
    
    # GITHUB_TOKEN is always required
    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        missing_tokens.append("GITHUB_TOKEN")
    else:
        print("✓ GITHUB_TOKEN is set")
    
    # GEMINI_API_KEY is required if using AI classification
    if classifier == "ai":
        gemini_key = os.getenv("GEMINI_API_KEY")
        if not gemini_key:
            missing_tokens.append("GEMINI_API_KEY")
        else:
            print("✓ GEMINI_API_KEY is set")
    
    if missing_tokens:
        print(f"\n❌ Error: The following required environment variables are not set:")
        for token in missing_tokens:
            print(f"   - {token}")
        print("\nPlease ensure you have a .env file in the project root with these variables.")
        print("Example .env format:")
        print("GITHUB_TOKEN=your_github_token_here")
        if classifier == "ai":
            print("GEMINI_API_KEY=your_gemini_api_key_here")
        sys.exit(1)
    
    print("\n✓ All required tokens are set\n")

def main():
    parser = argparse.ArgumentParser(description="Run the full Task Mining Pipeline")
    parser.add_argument("repo_or_file", help="GitHub repository (owner/name) OR path to a text file with a list of repos")
    parser.add_argument("--search-limit", type=int, help="Maximum number of PRs/commits to search through (stops after searching this many items)")
    parser.add_argument("--results-limit", type=int, help="Maximum number of valid results to find (stops after finding this many valid pairs)")
    parser.add_argument("--timeout", type=int, default=120, help="Timeout in seconds for processing each repository (default: 120)")
    parser.add_argument("--clean", action="store_true", help="Clean previous results/state before running (deletes entire results/ and .state/ directories)")
    parser.add_argument("--type", default="fixes", choices=["fixes", "simple-dep-updates"],
                       help="Type of mining to run (Step 1): 'fixes' (PR-based bad->good) or 'simple-dep-updates' (single-line dependency updates). Default: fixes")
    parser.add_argument("--classifier", default="simple", choices=["simple", "ai"],
                       help="Classification to run (Steps 2 and 2b): 'simple' (heuristic) or 'ai' (Gemini, automatically runs simple as prerequisite). Runs on the mining results from Step 1. Default: simple")
    
    args = parser.parse_args()
    
    # Validate that at least one limit is specified
    if not args.search_limit and not args.results_limit:
        parser.error("At least one of --search-limit or --results-limit must be specified")
    
    # Step 0: Load environment variables and validate tokens
    load_env()
    validate_tokens(args.classifier)
    
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
        
        print("Clean complete.\n")
    
    repos = []
    if os.path.isfile(args.repo_or_file):
        with open(args.repo_or_file, 'r') as f:
            repos = [line.strip() for line in f if line.strip() and not line.startswith("#")]
        print(f"Loaded {len(repos)} repositories from {args.repo_or_file}")
    else:
        repos = [args.repo_or_file]
    
    print(f"Processing {len(repos)} repository/repositories with {args.timeout} second timeout per repo\n")
        
    for repo in repos:
        try:
            with timeout_context(args.timeout, repo):
                process_repo(repo, args.search_limit, args.results_limit, args.type, args.classifier, args.timeout)
        except TimeoutError as e:
            print(f"\n{'!'*60}")
            print(f"TIMEOUT: {e}")
            print(f"{'!'*60}\n")
            print(f"Skipping {repo} and continuing to next repository...")
            # Continue to next repo
        except Exception as e:
            print(f"Failed to process {repo}: {e}")
            # Continue to next repo
            
    print("\nPipeline Complete!")


if __name__ == "__main__":
    main()
