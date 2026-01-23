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

def process_repo(repo, search_limit, results_limit, mining_type, classifier):
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
    
    # Build limit arguments
    limit_args = []
    if search_limit:
        limit_args.extend(["--search-limit", str(search_limit)])
    if results_limit:
        limit_args.extend(["--results-limit", str(results_limit)])
    
    # Step 1: Mine based on type
    if mining_type == "fixes":
        run_step(
            ["python3", "-m", "mining.mine_fixes", repo] + limit_args + ["--output", "results", "--state", state_dir],
            f"Mining 'Bad -> Good' Pairs for {repo}"
        )
        
        # Step 2: Classification based on classifier option
        if classifier in ["simple", "both"]:
            run_step(
                ["python3", "-m", "classification.analyze_pairs", repo, "--input", mining_output, "--output", analyzed_output],
                f"Running Simple/Heuristic Analysis for {repo}"
            )
        
        # Step 3: AI Classification
        if classifier in ["ai", "both"]:
            # AI classifier needs analyzed results, so run simple first if not already run
            if classifier == "ai":
                run_step(
                    ["python3", "-m", "classification.analyze_pairs", repo, "--input", mining_output, "--output", analyzed_output],
                    f"Running Simple/Heuristic Analysis for {repo} (prerequisite for AI)"
                )
            run_step(
                ["python3", "-m", "classification.gemini_classifier", repo, "--input", analyzed_output, "--output", ai_output],
                f"Running AI Classification (Gemini) for {repo}"
            )
    elif mining_type == "simple-dep-updates":
        run_step(
            ["python3", "-m", "mining.mine_simple_dependency_updates", repo] + limit_args + ["--output", "results", "--state", state_dir],
            f"Mining Simple Dependency Updates for {repo}"
        )
    elif mining_type == "both":
        # Run both mining types
        run_step(
            ["python3", "-m", "mining.mine_fixes", repo] + limit_args + ["--output", "results", "--state", state_dir],
            f"Mining 'Bad -> Good' Pairs for {repo}"
        )
        run_step(
            ["python3", "-m", "mining.mine_simple_dependency_updates", repo] + limit_args + ["--output", "results", "--state", state_dir],
            f"Mining Simple Dependency Updates for {repo}"
        )
        
        # Run classification on fixes mining results based on classifier option
        if classifier in ["simple", "both"]:
            run_step(
                ["python3", "-m", "classification.analyze_pairs", repo, "--input", mining_output, "--output", analyzed_output],
                f"Running Simple/Heuristic Analysis for {repo}"
            )
        
        if classifier in ["ai", "both"]:
            # AI classifier needs analyzed results, so run simple first if not already run
            if classifier == "ai":
                run_step(
                    ["python3", "-m", "classification.analyze_pairs", repo, "--input", mining_output, "--output", analyzed_output],
                    f"Running Simple/Heuristic Analysis for {repo} (prerequisite for AI)"
                )
            run_step(
                ["python3", "-m", "classification.gemini_classifier", repo, "--input", analyzed_output, "--output", ai_output],
                f"Running AI Classification (Gemini) for {repo}"
            )

def main():
    parser = argparse.ArgumentParser(description="Run the full Task Mining Pipeline")
    parser.add_argument("repo_or_file", help="GitHub repository (owner/name) OR path to a text file with a list of repos")
    parser.add_argument("--search-limit", type=int, help="Maximum number of PRs/commits to search through (stops after searching this many items)")
    parser.add_argument("--results-limit", type=int, help="Maximum number of valid results to find (stops after finding this many valid pairs)")
    parser.add_argument("--clean", action="store_true", help="Clean previous results/state before running (deletes entire results/ and state/ directories)")
    parser.add_argument("--type", default="fixes", choices=["fixes", "simple-dep-updates", "both"],
                       help="Type of mining to run: 'fixes' (PR-based bad->good), 'simple-dep-updates' (single-line dependency updates), or 'both' (default: fixes)")
    parser.add_argument("--classifier", default="both", choices=["simple", "ai", "both"],
                       help="Classification to run: 'simple' (heuristic), 'ai' (Gemini), or 'both' (default: both). Only applies to 'fixes' mining type.")
    
    args = parser.parse_args()
    
    # Validate that at least one limit is specified
    if not args.search_limit and not args.results_limit:
        parser.error("At least one of --search-limit or --results-limit must be specified")
    
    # Clean entire results and state directories if requested (done first, before processing any repos)
    if args.clean:
        import shutil
        results_dir = "results"
        state_dir = "state"
        
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
        
    for repo in repos:
        try:
            process_repo(repo, args.search_limit, args.results_limit, args.type, args.classifier)
        except Exception as e:
            print(f"Failed to process {repo}: {e}")
            # Continue to next repo
            
    print("\nPipeline Complete!")


if __name__ == "__main__":
    main()
