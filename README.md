# Task Mining: Self-Correction Pairs

This project mines GitHub repositories for "Self-Correction" pairs (Bad Commit -> Good Commit) in merged Pull Requests. It specifically looks for build failures followed by fixes.

## Setup

1.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```
2.  **Environment Variables**:
    Create a `.env` file:
    ```env
    GITHUB_TOKEN=your_github_pat
    # For LLM classification, set at least one of these (LiteLLM handles them):
    GEMINI_API_KEY=your_gemini_key
    OPENAI_API_KEY=your_openai_key
    ANTHROPIC_API_KEY=your_anthropic_key
    # Or any other provider supported by LiteLLM
    ```

## Usage

Run the full pipeline with `run_pipeline.py`:

```bash
# Single repository
# Required env vars: GITHUB_TOKEN
python3 run_pipeline.py owner/repo --search-limit 100

# Multiple repositories (from a text file with one repo per line)
# Required env vars: GITHUB_TOKEN
python3 run_pipeline.py repos.txt --search-limit 100
```

### Arguments

#### Required (at least one)

- `--search-limit N` - Maximum number of PRs/commits to search through
- `--results-limit N` - Maximum number of valid results to find

#### Mining Type

- `--type prs` (default) - Mine PR-based bad→good commit pairs
- `--type commits` - Mine commit pairs with successful builds

#### Classification

- `--classifier simple` (default) - Fast heuristic classification
- `--classifier llm` - AI-powered classification via LiteLLM (requires an API key for the chosen provider)
- `--model MODEL_NAME` - The model to use with LiteLLM (default: `gemini/gemini-2.0-flash`). Supports any model LiteLLM supports (e.g., `openai/gpt-4o`, `anthropic/claude-3-5-sonnet-20240620`, and local models like `qwen/qwen3-coder-next`.

#### Other Options

- `--reclassify` - Clear and re-run classification on existing results
- `--clean` - Delete results/ and .state/ directories before running
- `--clean-cache` - Delete .cache/ directory before running
- `--timeout N` - Timeout in seconds per repository (default: 120)
- `--allow-missing-status` - Allow commits without status checks (for `--type commits` only). Useful for repositories without CI/CD configured. Without this flag, only commits with verified successful builds are included.

### Examples

```bash
# Basic usage - search 100 PRs with simple classification
# Required env vars: GITHUB_TOKEN
python3 run_pipeline.py android/nowinandroid --search-limit 100

# Find 50 pairs with AI classification (default: Gemini)
# Required env vars: GITHUB_TOKEN, GEMINI_API_KEY
python3 run_pipeline.py android/nowinandroid --results-limit 50 --classifier llm

# Find 50 pairs with GPT-4o classification
# Required env vars: GITHUB_TOKEN, OPENAI_API_KEY
python3 run_pipeline.py android/nowinandroid --results-limit 50 --classifier llm --model openai/gpt-4o

# Find 50 pairs with Claude 3.5 Sonnet
# Required env vars: GITHUB_TOKEN, ANTHROPIC_API_KEY
python3 run_pipeline.py android/nowinandroid --results-limit 50 --classifier llm --model anthropic/claude-3-5-sonnet-20240620

# Use a local model via LM Studio
# Required env vars: GITHUB_TOKEN, OPENAI_API_BASE, OPENAI_API_KEY
OPENAI_API_BASE=http://localhost:1234/v1 python3 run_pipeline.py owner/repo --results-limit 10 --classifier llm --model openai/your-model-id

# Re-classify existing results
# Required env vars: GITHUB_TOKEN
python3 run_pipeline.py android/nowinandroid --search-limit 100 --reclassify

# Start fresh with clean state
# Required env vars: GITHUB_TOKEN
python3 run_pipeline.py android/nowinandroid --search-limit 100 --clean

# Mine commits instead of PRs
# Required env vars: GITHUB_TOKEN
python3 run_pipeline.py android/nowinandroid --results-limit 100 --type commits

# Mine commits from repo WITHOUT CI/CD (allow missing status checks)
# Required env vars: GITHUB_TOKEN
python3 run_pipeline.py gradle/gradle-profiler --results-limit 100 --type commits --allow-missing-status

# Multiple repositories with longer timeout
# Required env vars: GITHUB_TOKEN
python3 run_pipeline.py repos.txt --search-limit 100 --timeout 300
```

## Output

### File Structure

- `results/per_repo/{owner}_{name}.json` - Individual repository results
- `results/results.json` - Aggregated results from all repositories
- `results/dashboard.html` - Interactive HTML dashboard

### JSON Format

```json
{
  "repo_url": "https://github.com/owner/repo",
  "pr_id": 123,
  "from_commit": "abc123",
  "from_date": "2024-01-01T12:00:00Z",
  "from_verified": true,
  "to_commit": "def456",
  "to_msg": "Fix build issue\n\nDetailed description...",
  "to_date": "2024-01-02T12:00:00Z",
  "to_verified": true,
  "files_changed": ["file1.txt", "file2.txt", "file3.txt"],
  "summary": "Fix build issue by updating dependencies and configuration",
  "category": "Dependency Update",
  "tags": ["dependencies", "version-update"],
  "error": null
}
```

**Field Descriptions:**

- `from_verified` / `to_verified`: Boolean indicating whether build status was actually verified (true) or assumed due to `--allow-missing-status` (false)

### Dashboard

Open `results/dashboard.html` in your browser for an interactive visualization with:

- Statistics overview
- Distribution charts (by category or tags)
- Searchable results with links to GitHub
- Filter by repository

```bash
# Open the dashboard
open results/dashboard.html      # macOS
xdg-open results/dashboard.html  # Linux
start results/dashboard.html     # Windows
```

## Classification Categories

Categories are defined in `classification/categories/*.txt` files:

- **Bug Fix** - Fixing errors or issues
- **Feature** - Adding new functionality
- **Refactor** - Code restructuring without changing functionality
- **Dependency Update** - Version updates, library changes
- **Gradle Update** - Gradle wrapper version updates (may include minor other changes)
- **Documentation** - Changes to documentation files
- **Other** - Doesn't fit other categories

Add custom categories by creating new `.txt` files in the `classification/categories/` directory.

## Classification Tags

Tags are defined in `classification/tags/*.txt` files and can be combined:

- **dependencies** - Dependency-related changes
- **version-update** - Version number increases
- **wrapper-update** - Gradle wrapper version changes
- **plugin-update** - Gradle plugin version updates
- **configuration-cache-update** - Configuration cache enablement
- **warning-suppression** - Warning suppression annotations
- **tests** - Changes to test files
- **documentation** - Documentation changes

Add custom tags by creating new `.txt` files in the `classification/tags/` directory.

## Caching

The pipeline automatically caches GitHub API responses in `.cache/` to improve performance:

- **PRs**: Up to 100 most recent PRs cached
- **Commits**: Up to 1000 most recent commits cached
- Use `--clean-cache` to clear the cache

## Resumability

Mining operations save state in `.state/` directory and can be resumed if interrupted. Just run the same command again to continue.

## Repositories Without CI/CD

If you're mining commits from a repository that doesn't have CI/CD configured or doesn't use GitHub status checks, the tool will return 0 results by default. This is because the commit miner requires verified successful builds to ensure data quality.

**Solution**: Use the `--allow-missing-status` flag with `--type commits`:

```bash
# Required env vars: GITHUB_TOKEN
python3 run_pipeline.py gradle/gradle-profiler --results-limit 100 --type commits --allow-missing-status
```

**Trade-off**: When this flag is enabled, commits without status checks are treated as potentially valid. This allows mining from repositories without CI/CD, but the resulting pairs may not represent actual build failures and fixes. Use this option when:

- The repository doesn't have CI/CD configured
- You want to mine commit pairs based on structure rather than verified build status
- You're willing to accept lower confidence in the "bad→good" relationship

## Project Structure

- `/mining` - Mining scripts for extracting data
- `/classification` - Classification scripts
  - `/categories` - Category definitions
- `/reporting` - Dashboard generation
- `/results` - Output files (gitignored)
- `/.state` - State files for resumability (gitignored)
- `/.cache` - API response cache (gitignored)
