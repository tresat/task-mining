import argparse
import subprocess
import sys
import os

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

def process_repo(repo, limit, clean, mining_type):
    print(f"\n{'#'*60}")
    print(f"PROCESSING REPO: {repo}")
    print(f"{'#'*60}\n")
    
    if "/" not in repo:
        print(f"Skipping invalid repo format: {repo}")
        return

    owner, name = repo.split("/", 1)
    output_dir = os.path.join("results", f"{owner}_{name}")
    state_dir = "state"
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(state_dir, exist_ok=True)
    
    # Define filenames within the repo-specific directory
    mining_output = os.path.join(output_dir, "mining_results.json")
    mining_state = os.path.join(state_dir, f"{owner}_{name}_mining_state.json")
    simple_dep_output = os.path.join(output_dir, "simple_dependency_updates.json")
    simple_dep_state = os.path.join(state_dir, f"{owner}_{name}_simple_dependency_state.json")
    analyzed_output = os.path.join(output_dir, "analyzed_results.json")
    ai_output = os.path.join(output_dir, "ai_classified_results.json")
    
    # Clean if requested
    if clean:
        print(f"Cleaning up previous results in {output_dir} and {state_dir}...")
        for f in [mining_output, mining_state, simple_dep_output, simple_dep_state, analyzed_output, ai_output]:
            if os.path.exists(f):
                os.remove(f)
                print(f"Removed {f}")
    
    # Step 1: Mine based on type
    if mining_type == "fixes":
        run_step(
            ["python3", "-m", "mining.mine_fixes", repo, "--limit", str(limit), "--output", "results", "--state", state_dir],
            f"Mining 'Bad -> Good' Pairs for {repo}"
        )
        
        # Step 2: Heuristic Analysis
        run_step(
            ["python3", "analyze_pairs.py", repo, "--input", mining_output, "--output", analyzed_output],
            f"Running Heuristic Analysis for {repo}"
        )
        
        # Step 3: AI Classification
        run_step(
            ["python3", "gemini_classifier.py", repo, "--input", analyzed_output, "--output", ai_output],
            f"Running AI Classification (Gemini) for {repo}"
        )
    elif mining_type == "simple":
        run_step(
            ["python3", "-m", "mining.mine_simple_dependency_updates", repo, "--limit", str(limit), "--output", "results", "--state", state_dir],
            f"Mining Simple Dependency Updates for {repo}"
        )
    elif mining_type == "both":
        # Run both mining types
        run_step(
            ["python3", "-m", "mining.mine_fixes", repo, "--limit", str(limit), "--output", "results", "--state", state_dir],
            f"Mining 'Bad -> Good' Pairs for {repo}"
        )
        run_step(
            ["python3", "-m", "mining.mine_simple_dependency_updates", repo, "--limit", str(limit), "--output", "results", "--state", state_dir],
            f"Mining Simple Dependency Updates for {repo}"
        )
        
        # Run analysis on fixes mining results
        run_step(
            ["python3", "analyze_pairs.py", repo, "--input", mining_output, "--output", analyzed_output],
            f"Running Heuristic Analysis for {repo}"
        )
        run_step(
            ["python3", "gemini_classifier.py", repo, "--input", analyzed_output, "--output", ai_output],
            f"Running AI Classification (Gemini) for {repo}"
        )

def main():
    parser = argparse.ArgumentParser(description="Run the full Task Mining Pipeline")
    parser.add_argument("repo_or_file", help="GitHub repository (owner/name) OR path to a text file with a list of repos")
    parser.add_argument("--limit", type=int, default=100, help="Limit for mining PRs per repo")
    parser.add_argument("--clean", action="store_true", help="Clean previous results/state before running")
    parser.add_argument("--type", default="fixes", choices=["fixes", "simple", "both"],
                       help="Type of mining to run: 'fixes' (PR-based bad->good), 'simple' (single-line dependency updates), or 'both' (default: fixes)")
    
    args = parser.parse_args()
    
    repos = []
    if os.path.isfile(args.repo_or_file):
        with open(args.repo_or_file, 'r') as f:
            repos = [line.strip() for line in f if line.strip() and not line.startswith("#")]
        print(f"Loaded {len(repos)} repositories from {args.repo_or_file}")
    else:
        repos = [args.repo_or_file]
        
    for repo in repos:
        try:
            process_repo(repo, args.limit, args.clean, args.type)
        except Exception as e:
            print(f"Failed to process {repo}: {e}")
            # Continue to next repo
            
    print("\nPipeline Complete!")


if __name__ == "__main__":
    main()
