# Task Mining: Self-Correction Pairs

This project mines GitHub repositories for "Self-Correction" pairs (Bad Commit -> Good Commit) in merged Pull Requests. It specifically looks for build failures followed by fixes.

## Setup

1.  **Install Dependencies**:
    ```bash
    pip install requests
    pip install google-generativeai  # Only needed for --classifier gemini
    pip install openai               # Only needed for --classifier gpt
    pip install anthropic            # Only needed for --classifier claude
    ```
2.  **Environment Variables**:
    Create a `.env` file:
    ```env
    GITHUB_TOKEN=your_github_pat
    GEMINI_API_KEY=your_gemini_key        # Only needed for --classifier gemini
    OPENAI_API_KEY=your_openai_key        # Only needed for --classifier gpt
    ANTHROPIC_API_KEY=your_anthropic_key  # Only needed for --classifier claude
    ```

## Usage

Run the full pipeline with `run_pipeline.py`:

```bash
# Single repository
python3 run_pipeline.py owner/repo --search-limit 100

# Multiple repositories (from a text file with one repo per line)
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
- `--classifier gemini` - AI-powered classification using Google Gemini (requires GEMINI_API_KEY)
- `--classifier gpt` - AI-powered classification using OpenAI GPT (requires OPENAI_API_KEY)
- `--classifier claude` - AI-powered classification using Anthropic Claude (requires ANTHROPIC_API_KEY)

#### Other Options
- `--reclassify` - Clear and re-run classification on existing results
- `--clean` - Delete results/ and .state/ directories before running
- `--clean-cache` - Delete .cache/ directory before running
- `--timeout N` - Timeout in seconds per repository (default: 120)

### Examples

```bash
# Basic usage - search 100 PRs with simple classification
python3 run_pipeline.py android/nowinandroid --search-limit 100

# Find 50 pairs with Gemini AI classification
python3 run_pipeline.py android/nowinandroid --results-limit 50 --classifier gemini

# Find 50 pairs with GPT AI classification
python3 run_pipeline.py android/nowinandroid --results-limit 50 --classifier gpt

# Find 50 pairs with Claude AI classification
python3 run_pipeline.py android/nowinandroid --results-limit 50 --classifier claude

# Re-classify existing results
python3 run_pipeline.py android/nowinandroid --search-limit 100 --reclassify

# Start fresh with clean state
python3 run_pipeline.py android/nowinandroid --search-limit 100 --clean

# Mine commits instead of PRs
python3 run_pipeline.py android/nowinandroid --results-limit 100 --type commits

# Multiple repositories with longer timeout
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
  "pr_id": 123,
  "repo_url": "https://github.com/owner/repo",
  "from_commit": "abc123",
  "from_msg": "Initial implementation",
  "from_date": "2024-01-01T12:00:00Z",
  "to_commit": "def456",
  "to_msg": "Fix build issue\n\nDetailed description...",
  "to_date": "2024-01-02T12:00:00Z",
  "files_changed": [...],
  "category": "Dependency Update",
  "tags": ["dependencies", "version-update"],
  "error": null
}
```

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
- **Other** - Doesn't fit other categories

Add custom categories by creating new `.txt` files in the `classification/categories/` directory.

## Caching

The pipeline automatically caches GitHub API responses in `.cache/` to improve performance:
- **PRs**: Up to 100 most recent PRs cached
- **Commits**: Up to 1000 most recent commits cached
- Use `--clean-cache` to clear the cache

## Resumability

Mining operations save state in `.state/` directory and can be resumed if interrupted. Just run the same command again to continue.

## Project Structure

- `/mining` - Mining scripts for extracting data
- `/classification` - Classification scripts
  - `/categories` - Category definitions
- `/reporting` - Dashboard generation
- `/results` - Output files (gitignored)
- `/.state` - State files for resumability (gitignored)
- `/.cache` - API response cache (gitignored)
