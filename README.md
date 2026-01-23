# Task Mining: Self-Correction Pairs

This project mines GitHub repositories for "Self-Correction" pairs (Bad Commit -> Good Commit) in merged Pull Requests. It specifically looks for build failures followed by fixes.

## Scripts

### 0. `run_pipeline.py` (The All-in-One)
**Function**: Runs the entire pipeline (Mining -> Analysis -> AI).
- **Usage (Single Repo)**:
  ```bash
  python3 run_pipeline.py android/nowinandroid --limit 100
  ```
- **Usage (Multi-Repo)**:
  Create a file `repos.txt` with one repo per line, then:
  ```bash
  python3 run_pipeline.py repos.txt --limit 100
  ```
  Results will be saved in `results/{owner}_{name}/`.

### 1. `mine_fixes.py` (The Miner)
**Function**: Identifies "Self-Correction" pairs in merged PRs.
- **Logic**: Scans PRs for a sequence of `Failure -> Success` commits.
- **Input**: GitHub Repo (owner/name)
- **Output**: `mining_results.json`
- **Usage**:
  ```bash
  python3 mine_fixes.py android/nowinandroid --limit 100
  ```

### 1b. `mine_simple_dependency_updates.py` (The Simple Dependency Miner)
**Function**: Identifies simple single-line dependency version updates.
- **Logic**: Scans individual commits (not PRs) for single-line dependency version increases in `build.gradle`, `build.gradle.kts`, or `libs.versions.toml` files where both the commit and its parent have successful builds.
- **Branch Detection**: Automatically detects the default branch (tries `main` first, then `master`).
- **Input**: GitHub Repo (owner/name) OR a text file with a list of repos (one per line)
- **Output**: `results/{owner}_{name}/simple_dependency_updates.json`
- **Usage (Single Repo)**:
  ```bash
  python3 mine_simple_dependency_updates.py android/nowinandroid --limit 1000
  ```
- **Usage (Multi-Repo)**:
  Create a file `repos.txt` with one repo per line, then:
  ```bash
  python3 mine_simple_dependency_updates.py repos.txt --limit 1000
  ```
  Results will be saved in `results/{owner}_{name}/simple_dependency_updates.json`.
- **Output Format**: Similar to `mining_results.json` but with:
  - `from_commit` / `to_commit` instead of `bad_commit` / `good_commit`
  - Additional fields: `changed_file`, `changed_line_number`, `from_line_contents`, `to_line_contents`

### 2. `analyze_pairs.py` (The Heuristic Classifier)
**Function**: Classifies pairs based on changed files (Fast & Cheap).
- **Logic**: Checks if `build.gradle`, `libs.versions.toml`, or other build files were modified.
- **Categories**: `Dependency Update` vs `Other`.
- **Input**: `mining_results.json`
- **Output**: `analyzed_results.json`
- **Usage**:
  ```bash
  python3 analyze_pairs.py android/nowinandroid
  ```

### 3. `gemini_classifier.py` (The AI Classifier)
**Function**: Classifies pairs using an LLM (Gemini) for deeper understanding.
- **Logic**: Fetches the actual code diff and asks Gemini: "Is this a dependency update?".
- **Benefit**: Can distinguish between a simple version bump and a logic fix in a build file.
- **Input**: `analyzed_results.json`
- **Output**: `ai_classified_results.json`
- **Usage**:
  ```bash
  python3 gemini_classifier.py android/nowinandroid
  ```

## Resumability
Multiple scripts support resuming if interrupted.

- **mine_fixes.py**: Uses a state file (default `mining_state.json`) to save the cursor.
  - To resume: Just run the same command again.
  - To restart: Delete `mining_state.json` and `mining_results.json`.

- **mine_simple_dependency_updates.py**: Uses a state file (default `simple_dependency_state.json`) to save the cursor.
  - To resume: Just run the same command again.
  - To restart: Delete `simple_dependency_state.json` and `results/simple_dependency_updates.json`.

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
