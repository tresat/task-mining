# Task Mining: Self-Correction Pairs

This project mines GitHub repositories for "Self-Correction" pairs (Bad Commit -> Good Commit) in merged Pull Requests. It specifically looks for build failures followed by fixes.

## Project Structure

- `/mining` - Mining scripts for extracting data from repositories
  - `mine_prs.py` - Mines PR-based commit pairs (bad->good)
  - `mine_commits.py` - Mines commit pairs with successful builds
  - `cache.py` - GitHub API caching system
  - `mine_common.py` - Shared utilities for mining scripts
- `/classification` - Classification and analysis scripts
  - `simple_classifier.py` - Heuristic classification of mining results (formerly analyze_pairs.py)
  - `gemini_classifier.py` - AI-powered classification using Gemini
- `/reporting` - Reporting and dashboard generation scripts
  - `build_dashboard.py` - Generates interactive HTML dashboard from results
- `/test` - Unit tests for mining and classification scripts
- `/.state` - State files for resumable mining (gitignored)
- `/.cache` - GitHub API response cache (gitignored)
- `/results` - Mining results (gitignored)
  - `/per_repo/` - Individual JSON files per repository
  - `results.json` - Aggregated results from all repositories
  - `dashboard.html` - Interactive visualization dashboard
- `/samples` - Sample output files for reference

## GitHub API Caching

The mining scripts use a comprehensive caching system to improve performance and reduce API calls:

### How It Works
1. **Cache Location**: `.cache/{owner}_{name}/` directory (hidden, gitignored)
2. **Cache Structure**: 
   - PRs: `prs_cache.json` (for `mine_prs.py`, max 100 items)
   - Commits: `commits_cache.json` (for `mine_commits.py`, max 1000 items)
3. **Cache Priming** (automatic first step):
   - Fetches list of recent PR/commit IDs from GitHub
   - For each ID (most to least recent): checks if full details are in cache
   - If not cached: fetches full details and adds to cache
   - Stops when: (a) finding an ID already in cache, OR (b) reaching max items (100 for PRs, 1000 for commits)
4. **Mining with Cache**:
   - First reads data from cache (fast, no API calls)
   - When cache is exhausted: fetches next batch from GitHub and caches it
   - Automatically displays cache stats when starting

### Cache Management
- **Always Enabled**: Caching is automatic and always active
- **Cache Stats**: Shown when mining starts (e.g., "Cache contains 150 PRs for owner/repo")
- **Logging**: Clear indication when querying GitHub vs. reading from cache
- **Clean Options**:
  - `--clean` clears results/ and .state/ but NOT .cache/
  - `--clean-cache` clears the entire .cache/ directory
  
Example:
```bash
# Clean cache before running
python3 run_pipeline.py owner/repo --search-limit 100 --clean-cache

# Normal run uses existing cache
python3 run_pipeline.py owner/repo --search-limit 100
```

## Output Format

All mining scripts now use a **unified JSON format** with date fields and category placeholders:

```json
{
  "pr_id": 123,
  "repo_url": "https://github.com/owner/repo",
  "from_commit": "abc123",
  "from_msg": "Initial implementation",
  "from_date": "2024-01-01T12:00:00Z",
  "to_commit": "def456",
  "to_msg": "Fix build issue",
  "to_date": "2024-01-02T12:00:00Z",
  "files_changed": [
    {
      "filename": "build.gradle",
      "line_number": 42,
      "from_line_contents": "version = \"1.0.0\"",
      "to_line_contents": "version = \"1.1.0\""
    }
  ],
  "category": null,
  "tags": [],
  "error": null
}
```

**Note:** 
- `pr_id` is `null` for commit-based mining (only available for PR-based mining)
- `repo_url` contains the GitHub repository URL (e.g., `https://github.com/owner/repo`)
- `from_date` and `to_date` are ISO 8601 timestamps from GitHub's `committedDate` field
  - For PR-based mining: `from_date` is the bad commit's date, `to_date` is the good commit's date
  - For commit-based mining: `from_date` is the parent commit's date, `to_date` is the current commit's date
- `files_changed` is always an array, even for single-file changes
- For PR-based mining, `files_changed` is initially empty and populated by classification scripts
- For commit-based mining, `files_changed` contains detailed line-level change information
- `category` is initialized to `null` and set by the simple classifier (only set to "Dependency Update" for pure libs.versions.toml changes)
- `tags` is an empty array `[]` initially, populated by classification steps as a list of tags
- `error` is `null` when successful. If classification or other operations fail, contains descriptive error message (e.g., "429: Quota exceeded...")

## Output Structure

Results are now organized as follows:
- `results/per_repo/{owner}_{name}.json` - Individual repository results (one file per repo, regardless of mining type)
- `results/results.json` - Aggregated results from all repositories (created at the end of the pipeline, even if empty)
- `results/dashboard.html` - Interactive HTML dashboard for visualizing results

## Interactive Dashboard

The pipeline automatically generates an interactive HTML dashboard at `results/dashboard.html` that provides:

**Features:**
- **Group By Toggle**: Switch between grouping results by Category or Tags
- **Statistics Overview**: Total results, number of categories/tags, repositories analyzed
- **Distribution Chart**: Visual breakdown using doughnut chart
- **Detailed Results View**: Searchable list of all mining results with:
  - Repository names and links
  - PR numbers (if applicable)
  - Commit dates
  - Category and tag badges
  - Files changed
  - Error messages (if any)

**Usage:**
```bash
# Dashboard is automatically generated after running the pipeline
python3 run_pipeline.py android/nowinandroid --search-limit 100

# Open the dashboard
open results/dashboard.html  # macOS
xdg-open results/dashboard.html  # Linux
start results/dashboard.html  # Windows
```

**Manual Generation:**
```bash
# Generate dashboard from existing results.json
python3 -m reporting.build_dashboard
```

## Scripts

### 0. `run_pipeline.py` (The All-in-One)
**Function**: Runs the entire pipeline: Token Validation -> Mining -> Classification.

**Pipeline Steps:**
- **Step 0a**: Cache Priming - Automatically primes cache with recent PRs/commits (always enabled)
- **Step 0b**: Token Validation - Validates that required environment tokens (GITHUB_TOKEN, GEMINI_API_KEY) are set
- **Step 1**: Mining - Extracts data based on `--type` parameter (uses cache when available), outputs to `results/per_repo/{owner}_{name}.json`
- **Step 2**: Simple Classifier - Analyzes mining results in-place, categorizes dependency changes, updates `category` field and adds `tags`
- **Step 2b**: AI Classification - Deepens analysis using Gemini (requires GEMINI_API_KEY), adds AI-generated tags to `tags` array
- **Step 3**: Aggregation - Combines all per_repo files into `results/results.json`
- **Step 4**: Dashboard Generation - Creates interactive HTML dashboard at `results/dashboard.html`

**Parameters:**
- **Mining Types** (`--type`): Controls Step 1
  - `prs` (default): PR-based bad->good commit pairs
  - `commits`: Commit pairs with successful builds (mines ALL pairs where both parent and child have successful builds)
- **Classification Options** (`--classifier`): Controls Steps 2 and 2b, runs on the results from Step 1
  - `simple` (default): Heuristic classification only (fast)
  - `ai`: AI classification with Gemini (automatically runs simple as prerequisite)
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
- **Clean Options**:
  - `--clean`: Deletes entire `results/` and `.state/` directories before running (does NOT clear cache)
  - `--clean-cache`: Deletes entire `.cache/` directory before running
  - Both can be used together for a complete clean
  - Useful for starting fresh or after changing mining parameters
  - Executes before any mining or classification begins
- **Usage (Single Repo)**:
  ```bash
  # Search through 100 PRs
  python3 run_pipeline.py android/nowinandroid --search-limit 100 --type prs
  
  # Find 50 valid pairs
  python3 run_pipeline.py android/nowinandroid --results-limit 50 --type prs
  
  # Search through 200 PRs or until 50 valid pairs found (whichever comes first)
  python3 run_pipeline.py android/nowinandroid --search-limit 200 --results-limit 50 --type prs
  
  # Run with custom timeout (5 minutes)
  python3 run_pipeline.py android/nowinandroid --search-limit 100 --type prs --timeout 300
  
  # Run with clean (deletes all previous results first, but keeps cache)
  python3 run_pipeline.py android/nowinandroid --search-limit 100 --type prs --clean
  
  # Run with cache clean (clears cache before running)
  python3 run_pipeline.py android/nowinandroid --search-limit 100 --type prs --clean-cache
  
  # Complete clean (results, state, and cache)
  python3 run_pipeline.py android/nowinandroid --search-limit 100 --type prs --clean --clean-cache
  
  # Run only simple classification (default)
  python3 run_pipeline.py android/nowinandroid --search-limit 100 --type prs
  
  # Run with AI classification (simple runs automatically as prerequisite)
  python3 run_pipeline.py android/nowinandroid --search-limit 100 --type prs --classifier ai
  
  # Run commits mining with simple classification
  python3 run_pipeline.py android/nowinandroid --results-limit 100 --type commits
  
  # Run commits with AI classification
  python3 run_pipeline.py android/nowinandroid --results-limit 100 --type commits --classifier ai
  ```
- **Usage (Multi-Repo)**:
  Create a file `repos.txt` with one repo per line, then:
  ```bash
  # Process multiple repos with 2-minute timeout per repo (default)
  python3 run_pipeline.py repos.txt --search-limit 100 --type prs --clean
  
  # Process commits with longer timeout for slow repos
  python3 run_pipeline.py repos.txt --search-limit 100 --type commits --timeout 600
  
  # Clean cache before processing multiple repos
  python3 run_pipeline.py repos.txt --search-limit 100 --type prs --clean-cache
  ```
  Results will be saved in `results/per_repo/{owner}_{name}.json`, and aggregated into `results/results.json` at the end.

### 1. `mining/mine_prs.py` (The PR Miner)
**Function**: Identifies "Self-Correction" pairs in merged PRs.
- **Logic**: Scans PRs for a sequence of `Failure -> Success` commits.
- **Input**: GitHub Repo (owner/name) OR a text file with a list of repos (one per line)
- **Output**: `results/per_repo/{owner}_{name}.json` with date fields and null category fields
- **State Files**: Stored in `.state/{owner}_{name}_mining_state.json`
- **Usage (Single Repo)**:
  ```bash
  python3 -m mining.mine_prs android/nowinandroid --search-limit 100 --results-limit 50
  ```
- **Usage (Multi-Repo)**:
  ```bash
  python3 -m mining.mine_prs repos.txt --search-limit 100 --results-limit 50
  ```

### 1b. `mining/mine_commits.py` (The Commit Miner)
**Function**: Mines commit pairs where both parent and child have successful builds.
- **Logic**: Scans individual commits (not PRs) for pairs where both the commit and its parent have successful builds. Does NOT filter by file type or change type - mines ALL successful build pairs.
- **Classification**: The simple_classifier adds tags for specific patterns:
  - `one-line`: Single-line changes in dependency files
  - `version-update`: Version increases detected
  - Files_changed is populated by the classifier
- **Branch Detection**: Automatically detects the default branch (tries `main` first, then `master`).
- **Input**: GitHub Repo (owner/name) OR a text file with a list of repos (one per line)
- **Output**: `results/per_repo/{owner}_{name}.json` with date fields and null category fields
- **State Files**: Stored in `.state/{owner}_{name}_commit_pairs_state.json`
- **Usage (Single Repo)**:
  ```bash
  python3 -m mining.mine_commits android/nowinandroid --search-limit 1000 --results-limit 100
  ```
- **Usage (Multi-Repo)**:
  Create a file `repos.txt` with one repo per line, then:
  ```bash
  python3 -m mining.mine_commits repos.txt --search-limit 1000 --results-limit 100
  ```
  Results will be saved in `results/per_repo/{owner}_{name}.json`.

### 2. `classification/simple_classifier.py` (The Simple Classifier)
**Function**: Classifies changes based on dependency file modifications (Fast & Cheap).
- **Logic**: 
  - Checks if `libs.versions.toml` was modified
  - Checks if changes occurred within `dependencies {}` blocks in `build.gradle` or `build.gradle.kts` files
  - Checks if exactly one line changed in a dependency file
  - Checks if version increased
  - Only sets Category = "Dependency Update" if ONLY `libs.versions.toml` was changed
  - Adds tags:
    - "dependencies" tag if any dependency-related changes were found
    - "one-line" tag if exactly one line changed in a dependency file
    - "version-update" tag if version increased
  - Populates files_changed with line-level details when version-update detected
- **Categories**: Only tags things as `Dependency Update` vs others (leaves category null for non-pure dependency changes)
- **Tags**: Adds "dependencies", "one-line", "version-update" tags when applicable
- **Input**: `results/per_repo/{owner}_{name}.json` (auto-detected from repo name)
- **Output**: Updates the same file in-place, setting the `category` field and adding to `tags` array
- **Usage**:
  ```bash
  python3 -m classification.simple_classifier android/nowinandroid
  # Or with custom input:
  python3 -m classification.simple_classifier android/nowinandroid --input custom_file.json
  ```

### 2b. `classification/gemini_classifier.py` (The AI Classifier)
**Function**: Classifies pairs using an LLM (Gemini) for deeper understanding.
- **Logic**: Fetches the actual code diff and asks Gemini for categorization.
- **Tag Types**: `Dependency Update`, `Bug Fix`, `Feature`, `Refactor`, `Other`.
- **Benefit**: Can distinguish between different types of changes beyond simple file-based heuristics.
- **Input**: `results/per_repo/{owner}_{name}.json` (auto-detected from repo name)
- **Output**: Updates the same file in-place, adding AI-generated tag to `tags` array
- **Usage**:
  ```bash
  python3 -m classification.gemini_classifier android/nowinandroid
  # Or with custom input:
  python3 -m classification.gemini_classifier android/nowinandroid --input custom_file.json
  ```

## Resumability
All mining scripts support resuming if interrupted.

- **mining/mine_prs.py**: Uses state files in the `.state/` directory (e.g., `.state/{owner}_{name}_mining_state.json`).
  - To resume: Just run the same command again.
  - To restart: Delete the corresponding state file in `.state/` and the results in `results/per_repo/{owner}_{name}.json`.

- **mining/mine_commits.py**: Uses state files in the `.state/` directory (e.g., `.state/{owner}_{name}_commit_pairs_state.json`).
  - To resume: Just run the same command again.
  - To restart: Delete the corresponding state file in `.state/` and the results in `results/per_repo/{owner}_{name}.json`.

- **gemini_classifier.py**: Checks for existing tag values in the input file.
  - To resume: Run the command again; it skips already classified pairs.
  - To restart: Delete or reset the `tags` field in the per_repo JSON file.

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
