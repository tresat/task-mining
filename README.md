# Task Mining: Self-Correction Pairs

This project mines GitHub repositories for "Self-Correction" pairs (Bad Commit -> Good Commit) in merged Pull Requests. It specifically looks for build failures followed by fixes.

## Project Structure

- `/mining` - Mining scripts for extracting data from repositories
  - `mine_fixes.py` - Mines PR-based bad->good commit pairs
  - `mine_simple_dependency_updates.py` - Mines single-line dependency updates
  - `common.py` - Shared utilities for mining scripts
- `/classification` - Classification and analysis scripts
  - `analyze_pairs.py` - Heuristic classification of mining results
  - `gemini_classifier.py` - AI-powered classification using Gemini
- `/test` - Unit tests for mining and classification scripts
- `/state` - State files for resumable mining (gitignored)
- `/results` - Mining results (gitignored)
- `/samples` - Sample output files for reference

## Output Format

All mining scripts now use a **unified JSON format** to ensure consistency:

```json
{
  "pr_id": 123,
  "pr_url": "https://github.com/owner/repo/pull/123",
  "from_commit": "abc123",
  "from_msg": "Initial implementation",
  "to_commit": "def456",
  "to_msg": "Fix build issue",
  "files_changed": [
    {
      "filename": "build.gradle",
      "line_number": 42,
      "from_line_contents": "version = \"1.0.0\"",
      "to_line_contents": "version = \"1.1.0\""
    }
  ]
}
```

**Note:** 
- `files_changed` is always an array, even for single-file changes
- For PR-based mining, `files_changed` is initially empty and can be populated by classification scripts
- For commit-based mining, `files_changed` contains detailed line-level change information
- Fields not applicable to a specific mining type (e.g., `pr_id` for commit-based mining) are left empty or null

## Scripts

### 0. `run_pipeline.py` (The All-in-One)
**Function**: Runs the entire pipeline (Mining -> Classification).
- **Mining Types** (`--type`): Controls Step 1
  - `fixes` (default): PR-based bad->good commit pairs
  - `simple-dep-updates`: Single-line dependency updates only
  - `both`: Runs both mining types
- **Classification Options** (`--classifier`): Controls Steps 2 and 2b, runs on the results from Step 1
  - `simple`: Heuristic classification only (fast)
  - `ai`: AI classification with Gemini (requires simple as prerequisite)
  - `both` (default): Runs both simple and AI classification
- **Limit Options**:
  - `--search-limit`: Maximum number of PRs/commits to search through (stops after searching this many items)
  - `--results-limit`: Maximum number of valid results to find (stops after finding this many valid pairs/updates)
  - At least one limit must be specified
  - Both limits can be used together
- **Timeout Option** (`--timeout`):
  - Per-repository timeout in seconds (default: 120)
  - If a repository exceeds the timeout, it is skipped and processing continues with the next repository
  - Prevents individual repositories from hanging indefinitely
  - Example: `--timeout 300` for 5-minute timeout
- **Clean Option** (`--clean`):
  - Deletes entire `results/` and `state/` directories before running
  - Useful for starting fresh or after changing mining parameters
  - Executes before any mining or classification begins
- **Usage (Single Repo)**:
  ```bash
  # Search through 100 PRs
  python3 run_pipeline.py android/nowinandroid --search-limit 100 --type fixes
  
  # Find 50 valid pairs
  python3 run_pipeline.py android/nowinandroid --results-limit 50 --type fixes
  
  # Search through 200 PRs or until 50 valid pairs found (whichever comes first)
  python3 run_pipeline.py android/nowinandroid --search-limit 200 --results-limit 50 --type fixes
  
  # Run with custom timeout (5 minutes)
  python3 run_pipeline.py android/nowinandroid --search-limit 100 --type fixes --timeout 300
  
  # Run with clean (deletes all previous results first)
  python3 run_pipeline.py android/nowinandroid --search-limit 100 --type fixes --clean
  
  # Run only simple classification
  python3 run_pipeline.py android/nowinandroid --search-limit 100 --type fixes --classifier simple
  
  # Run simple-dep-updates mining with both classifiers
  python3 run_pipeline.py android/nowinandroid --results-limit 100 --type simple-dep-updates --classifier both
  
  # Run simple-dep-updates with only AI classification
  python3 run_pipeline.py android/nowinandroid --results-limit 100 --type simple-dep-updates --classifier ai
  ```
- **Usage (Multi-Repo)**:
  Create a file `repos.txt` with one repo per line, then:
  ```bash
  # Process multiple repos with 2-minute timeout per repo (default)
  python3 run_pipeline.py repos.txt --search-limit 100 --type both --clean
  
  # Process with longer timeout for slow repos
  python3 run_pipeline.py repos.txt --search-limit 100 --type both --timeout 600
  ```
  Results will be saved in `results/{owner}_{name}/`, state files in `state/`.

### 1. `mining/mine_fixes.py` (The Fixes Miner)
**Function**: Identifies "Self-Correction" pairs in merged PRs.
- **Logic**: Scans PRs for a sequence of `Failure -> Success` commits.
- **Input**: GitHub Repo (owner/name) OR a text file with a list of repos (one per line)
- **Output**: `results/{owner}_{name}/mining_results.json`
- **State Files**: Stored in `state/{owner}_{name}_mining_state.json`
- **Usage (Single Repo)**:
  ```bash
  python3 -m mining.mine_fixes android/nowinandroid --limit 100
  ```
- **Usage (Multi-Repo)**:
  ```bash
  python3 -m mining.mine_fixes repos.txt --limit 100
  ```

### 1b. `mining/mine_simple_dependency_updates.py` (The Simple Dependency Miner)
**Function**: Identifies simple single-line dependency version updates.
- **Logic**: Scans individual commits (not PRs) for single-line dependency version increases in `build.gradle`, `build.gradle.kts`, or `libs.versions.toml` files where both the commit and its parent have successful builds.
- **Branch Detection**: Automatically detects the default branch (tries `main` first, then `master`).
- **Input**: GitHub Repo (owner/name) OR a text file with a list of repos (one per line)
- **Output**: `results/{owner}_{name}/simple_dependency_updates.json`
- **State Files**: Stored in `state/{owner}_{name}_simple_dependency_state.json`
- **Usage (Single Repo)**:
  ```bash
  python3 -m mining.mine_simple_dependency_updates android/nowinandroid --limit 1000
  ```
- **Usage (Multi-Repo)**:
  Create a file `repos.txt` with one repo per line, then:
  ```bash
  python3 -m mining.mine_simple_dependency_updates repos.txt --limit 1000
  ```
  Results will be saved in `results/{owner}_{name}/simple_dependency_updates.json`.

### 2. `classification/analyze_pairs.py` (The Simple/Heuristic Classifier)
**Function**: Classifies pairs based on changed files (Fast & Cheap).
- **Logic**: Checks if `build.gradle`, `libs.versions.toml`, or other build files were modified.
- **Categories**: `Dependency Update` vs `Other`.
- **Input**: Mining results in unified format
- **Output**: `analyzed_results.json`
- **Usage**:
  ```bash
  python3 -m classification.analyze_pairs android/nowinandroid
  ```

### 2b. `classification/gemini_classifier.py` (The AI Classifier)
**Function**: Classifies pairs using an LLM (Gemini) for deeper understanding.
- **Logic**: Fetches the actual code diff and asks Gemini: "Is this a dependency update?".
- **Benefit**: Can distinguish between a simple version bump and a logic fix in a build file.
- **Input**: `analyzed_results.json`
- **Output**: `ai_classified_results.json`
- **Usage**:
  ```bash
  python3 -m classification.gemini_classifier android/nowinandroid
  ```

## Resumability
All mining scripts support resuming if interrupted.

- **mining/mine_fixes.py**: Uses state files in the `state/` directory (e.g., `state/{owner}_{name}_mining_state.json`).
  - To resume: Just run the same command again.
  - To restart: Delete the corresponding state file in `state/` and the results in `results/{owner}_{name}/mining_results.json`.

- **mining/mine_simple_dependency_updates.py**: Uses state files in the `state/` directory (e.g., `state/{owner}_{name}_simple_dependency_state.json`).
  - To resume: Just run the same command again.
  - To restart: Delete the corresponding state file in `state/` and the results in `results/{owner}_{name}/simple_dependency_updates.json`.

- **gemini_classifier.py**: Checks `ai_classified_results.json` for existing entries.
  - To resume: Run the command again; it skips already classified pairs.
  - To restart: Delete `ai_classified_results.json`.

## Setup

1.  **Install Dependencies**:
    ```bash
    pip install requests
    ```
2.  **Environment Variables**:
    Create a `.env` file:
    ```env
    GITHUB_TOKEN=your_github_pat
    GEMINI_API_KEY=your_gemini_key
    ```
