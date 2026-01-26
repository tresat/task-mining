#!/usr/bin/env python3
"""
Dashboard Builder for Task Mining Results

Generates an interactive HTML dashboard from mining results.
"""

import json
import os
from datetime import datetime


def build_dashboard(results_file="results/results.json", output_file="results/dashboard.html"):
    """
    Build an interactive HTML dashboard from mining results.
    
    Args:
        results_file: Path to the aggregated results.json file
        output_file: Path where the dashboard HTML will be saved
    """
    # Load results data
    if not os.path.exists(results_file):
        print(f"No results file found at {results_file}")
        # Create empty results for dashboard
        raw_data = []
    else:
        try:
            with open(results_file, 'r') as f:
                raw_data = json.load(f)
            print(f"Loaded {len(raw_data)} results from {results_file}")
        except Exception as e:
            print(f"Error loading results: {e}")
            raw_data = []
    
    # Generate the HTML dashboard
    html_content = generate_dashboard_html(raw_data)
    
    # Write dashboard file
    try:
        with open(output_file, 'w') as f:
            f.write(html_content)
        # Get absolute path for IDE compatibility
        abs_path = os.path.abspath(output_file)
        print(f"✓ Dashboard created at file://{abs_path}")
    except Exception as e:
        print(f"Error writing dashboard: {e}")


def generate_dashboard_html(raw_data):
    """
    Generate the complete HTML dashboard content.
    
    Args:
        raw_data: List of mining result objects
        
    Returns:
        Complete HTML string
    """
    # Convert raw_data to JSON string for embedding
    raw_data_json = json.dumps(raw_data, indent=2)
    
    html = f'''<!DOCTYPE html>
<html lang="en">

<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Task Mining Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg-color: #0f172a;
            --card-bg: #1e293b;
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --accent: #38bdf8;
            --accent-hover: #0ea5e9;
            --border: #334155;
            --dep-bg: #064e3b;
            --dep-text: #34d399;
            --unknown-bg: #78350f;
            --unknown-text: #fbbf24;
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}

        body {{
            font-family: 'Inter', sans-serif;
            background-color: var(--bg-color);
            color: var(--text-primary);
            line-height: 1.6;
            padding: 2rem;
        }}

        .container {{
            max-width: 1400px;
            margin: 0 auto;
        }}

        header {{
            margin-bottom: 3rem;
            text-align: center;
        }}

        h1 {{
            font-size: 2.5rem;
            font-weight: 700;
            margin-bottom: 0.5rem;
            background: linear-gradient(to right, #38bdf8, #818cf8);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}

        .subtitle {{
            color: var(--text-secondary);
            font-size: 1.1rem;
        }}

        .controls {{
            display: flex;
            gap: 1rem;
            margin-bottom: 2rem;
            flex-wrap: wrap;
            align-items: center;
        }}

        .control-group {{
            display: flex;
            gap: 0.5rem;
            align-items: center;
        }}

        label {{
            color: var(--text-secondary);
            font-weight: 600;
        }}

        select {{
            background-color: var(--card-bg);
            color: var(--text-primary);
            border: 1px solid var(--border);
            padding: 0.5rem 1rem;
            border-radius: 0.5rem;
            font-size: 1rem;
            cursor: pointer;
        }}

        select:hover {{
            border-color: var(--accent);
        }}

        .dashboard-grid {{
            display: grid;
            grid-template-columns: 1fr 2fr;
            gap: 2rem;
            margin-bottom: 3rem;
        }}

        @media (max-width: 900px) {{
            .dashboard-grid {{
                grid-template-columns: 1fr;
            }}
        }}

        .card {{
            background-color: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 1rem;
            padding: 1.5rem;
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
        }}

        .card-title {{
            font-size: 1.25rem;
            font-weight: 600;
            margin-bottom: 1rem;
            color: var(--text-primary);
        }}

        .chart-container {{
            position: relative;
            height: 400px;
        }}

        .stats-summary {{
            display: flex;
            flex-direction: column;
            gap: 1rem;
            justify-content: center;
        }}

        .stat-item {{
            text-align: center;
            padding: 1rem;
            border-radius: 0.75rem;
            background: rgba(255, 255, 255, 0.05);
        }}

        .stat-value {{
            font-size: 2.5rem;
            font-weight: 700;
            color: var(--accent);
        }}

        .stat-label {{
            font-size: 0.9rem;
            color: var(--text-secondary);
            margin-top: 0.25rem;
        }}

        .results-section {{
            margin-top: 3rem;
        }}

        .section-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1.5rem;
        }}

        .section-title {{
            font-size: 1.75rem;
            font-weight: 700;
        }}

        .filter-info {{
            color: var(--text-secondary);
        }}

        .result-card {{
            background-color: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 0.75rem;
            padding: 1.5rem;
            margin-bottom: 1rem;
            transition: transform 0.2s, border-color 0.2s;
        }}

        .result-card:hover {{
            transform: translateY(-2px);
            border-color: var(--accent);
        }}

        .result-header {{
            display: flex;
            justify-content: space-between;
            align-items: start;
            margin-bottom: 1rem;
        }}

        .result-title {{
            font-size: 1.1rem;
            font-weight: 600;
            color: var(--accent);
            text-decoration: none;
            flex: 1;
        }}

        .result-title:hover {{
            color: var(--accent-hover);
        }}

        .badges {{
            display: flex;
            gap: 0.5rem;
            flex-wrap: wrap;
        }}

        .badge {{
            padding: 0.25rem 0.75rem;
            border-radius: 0.375rem;
            font-size: 0.875rem;
            font-weight: 600;
        }}

        .badge-category {{
            background-color: var(--dep-bg);
            color: var(--dep-text);
        }}

        .badge-unknown {{
            background-color: var(--unknown-bg);
            color: var(--unknown-text);
        }}

        .badge-tag {{
            background-color: rgba(56, 189, 248, 0.2);
            color: var(--accent);
        }}

        .result-meta {{
            display: flex;
            gap: 1.5rem;
            color: var(--text-secondary);
            font-size: 0.9rem;
            margin-bottom: 0.75rem;
        }}

        .result-meta-item {{
            display: flex;
            align-items: center;
            gap: 0.25rem;
        }}

        .result-message {{
            color: var(--text-primary);
            margin-bottom: 0.5rem;
        }}

        .files-changed {{
            color: var(--text-secondary);
            font-size: 0.9rem;
            margin-top: 0.5rem;
        }}

        .error-message {{
            color: #f87171;
            font-size: 0.9rem;
            margin-top: 0.5rem;
            padding: 0.5rem;
            background-color: rgba(248, 113, 113, 0.1);
            border-radius: 0.375rem;
        }}

        .error-toggle {{
            cursor: pointer;
            color: #f87171;
            text-decoration: underline;
            margin-top: 0.5rem;
        }}

        .error-toggle:hover {{
            color: #fca5a5;
        }}

        .error-details {{
            display: none;
            margin-top: 0.5rem;
            padding: 0.75rem;
            background-color: rgba(248, 113, 113, 0.1);
            border-radius: 0.375rem;
            border-left: 3px solid #f87171;
            font-family: 'Courier New', monospace;
            font-size: 0.85rem;
            color: #f87171;
            white-space: pre-wrap;
            word-wrap: break-word;
            overflow-x: auto;
        }}

        .error-details.show {{
            display: block;
        }}

        .empty-state {{
            text-align: center;
            padding: 4rem 2rem;
            color: var(--text-secondary);
        }}

        .empty-state h3 {{
            font-size: 1.5rem;
            margin-bottom: 0.5rem;
        }}
    </style>
</head>

<body>
    <div class="container">
        <header>
            <h1>Task Mining Dashboard</h1>
            <p class="subtitle">Analyzed commit pairs and dependency updates from GitHub repositories</p>
        </header>

        <div class="controls">
            <div class="control-group">
                <label for="repoFilter">Repository:</label>
                <select id="repoFilter" onchange="updateDisplay()">
                    <option value="ALL">ALL</option>
                </select>
            </div>
            <div class="control-group">
                <label for="groupBy">Group By:</label>
                <select id="groupBy" onchange="updateDisplay()">
                    <option value="category">Category</option>
                    <option value="tags">Tags</option>
                </select>
            </div>
        </div>

        <div class="dashboard-grid">
            <div class="card">
                <h2 class="card-title">Statistics</h2>
                <div class="stats-summary">
                    <div class="stat-item">
                        <div class="stat-value" id="totalCount">0</div>
                        <div class="stat-label">Total Results</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value" id="categoryCount">0</div>
                        <div class="stat-label">Categories</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value" id="repoCount">0</div>
                        <div class="stat-label">Repositories</div>
                    </div>
                </div>
            </div>

            <div class="card">
                <h2 class="card-title" id="chartTitle">Distribution by Category</h2>
                <div class="chart-container">
                    <canvas id="distributionChart"></canvas>
                </div>
            </div>
        </div>

        <div class="results-section">
            <div class="section-header">
                <h2 class="section-title">Results</h2>
                <span class="filter-info" id="filterInfo"></span>
            </div>
            <div id="resultsContainer"></div>
        </div>
    </div>

    <script>
        const rawData = {raw_data_json};

        let chart = null;
        let currentGroupBy = 'category';
        let currentRepoFilter = 'ALL';

        function initializeRepoFilter() {{
            const repos = new Set(rawData.map(r => r.repo_url));
            const repoFilter = document.getElementById('repoFilter');
            
            // Add ALL option (already in HTML)
            // Add each repository
            repos.forEach(repo => {{
                const option = document.createElement('option');
                option.value = repo;
                // Extract repo name from URL for display
                const repoName = repo.replace('https://github.com/', '');
                option.textContent = repoName;
                repoFilter.appendChild(option);
            }});
        }}

        function getFilteredData() {{
            if (currentRepoFilter === 'ALL') {{
                return rawData;
            }}
            return rawData.filter(r => r.repo_url === currentRepoFilter);
        }}

        function updateDisplay() {{
            currentGroupBy = document.getElementById('groupBy').value;
            currentRepoFilter = document.getElementById('repoFilter').value;
            updateStats();
            updateChart();
            displayResults();
        }}

        function updateStats() {{
            const filteredData = getFilteredData();
            const totalCount = filteredData.length;
            const repos = new Set(filteredData.map(r => r.repo_url)).size;
            
            let groups = new Set();
            if (currentGroupBy === 'category') {{
                filteredData.forEach(r => {{
                    if (r.category) {{
                        groups.add(r.category);
                    }}
                }});
            }} else {{
                filteredData.forEach(r => {{
                    if (r.tags && Array.isArray(r.tags)) {{
                        r.tags.forEach(tag => groups.add(tag));
                    }}
                }});
            }}
            
            document.getElementById('totalCount').textContent = totalCount;
            document.getElementById('categoryCount').textContent = groups.size;
            document.getElementById('repoCount').textContent = repos;
        }}

        function updateChart() {{
            const ctx = document.getElementById('distributionChart').getContext('2d');
            const filteredData = getFilteredData();
            
            // Count by group
            const counts = {{}};
            
            if (currentGroupBy === 'category') {{
                filteredData.forEach(r => {{
                    const cat = r.category || 'Uncategorized';
                    counts[cat] = (counts[cat] || 0) + 1;
                }});
            }} else {{
                filteredData.forEach(r => {{
                    if (r.tags && Array.isArray(r.tags) && r.tags.length > 0) {{
                        r.tags.forEach(tag => {{
                            counts[tag] = (counts[tag] || 0) + 1;
                        }});
                    }} else {{
                        counts['No Tags'] = (counts['No Tags'] || 0) + 1;
                    }}
                }});
            }}
            
            const labels = Object.keys(counts);
            const data = Object.values(counts);
            
            if (chart) {{
                chart.destroy();
            }}
            
            document.getElementById('chartTitle').textContent = 
                currentGroupBy === 'category' ? 'Distribution by Category' : 'Distribution by Tags';
            
            chart = new Chart(ctx, {{
                type: 'doughnut',
                data: {{
                    labels: labels,
                    datasets: [{{
                        data: data,
                        backgroundColor: [
                            '#38bdf8', '#818cf8', '#34d399', '#fbbf24', 
                            '#f87171', '#c084fc', '#fb923c', '#a78bfa'
                        ],
                        borderWidth: 0
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {{
                        legend: {{
                            position: 'bottom',
                            labels: {{
                                color: '#f8fafc',
                                padding: 15,
                                font: {{
                                    size: 12
                                }}
                            }}
                        }}
                    }}
                }}
            }});
        }}

        function displayResults() {{
            const container = document.getElementById('resultsContainer');
            const filteredData = getFilteredData();
            
            if (filteredData.length === 0) {{
                container.innerHTML = `
                    <div class="empty-state">
                        <h3>No Results</h3>
                        <p>No mining results to display for the selected filter.</p>
                    </div>
                `;
                return;
            }}
            
            container.innerHTML = filteredData.map(result => {{
                const repoName = result.repo_url ? result.repo_url.split('/').slice(-2).join('/') : 'Unknown';
                const prUrl = result.pr_id && result.repo_url ? 
                    `${{result.repo_url}}/pull/${{result.pr_id}}` : null;
                const commitUrl = result.repo_url && result.to_commit ?
                    `${{result.repo_url}}/commit/${{result.to_commit}}` : null;
                const prLink = result.pr_id ? 
                    `<a href="${{prUrl}}" target="_blank">#${{result.pr_id}}</a>` :
                    null;
                
                // Build badges
                let badges = '';
                if (result.category) {{
                    const badgeClass = result.category === 'Unknown' ? 'badge-unknown' : 'badge-category';
                    badges += `<span class="badge ${{badgeClass}}">${{result.category}}</span>`;
                }}
                
                if (result.tags && Array.isArray(result.tags) && result.tags.length > 0) {{
                    result.tags.forEach(tag => {{
                        badges += `<span class="badge badge-tag">${{tag}}</span>`;
                    }});
                }}
                
                // Build files changed info
                let filesInfo = '';
                if (result.files_changed && result.files_changed.length > 0) {{
                    filesInfo = `<div class="files-changed">Files changed: ${{result.files_changed.map(f => f.filename).join(', ')}}</div>`;
                }}
                
                // Build error message if present (collapsible for long errors)
                let errorInfo = '';
                if (result.error) {{
                    const errorId = `error-${{Math.random().toString(36).substr(2, 9)}}`;
                    errorInfo = `
                        <div class="error-message">
                            ⚠️ Error occurred 
                            <a class="error-toggle" onclick="document.getElementById('${{errorId}}').classList.toggle('show'); return false;" href="#">
                                (click to expand/collapse)
                            </a>
                            <div id="${{errorId}}" class="error-details">${{result.error}}</div>
                        </div>
                    `;
                }}
                
                const title = result.to_msg || result.from_msg || 'No message';
                const link = prUrl || commitUrl || '#';
                
                return `
                    <div class="result-card">
                        <div class="result-header">
                            <a href="${{link}}" target="_blank" class="result-title">${{title}}</a>
                        </div>
                        <div class="result-meta">
                            <span class="result-meta-item">📦 ${{repoName}}</span>
                            ${{prLink ? `<span class="result-meta-item">PR ${{prLink}}</span>` : ''}}
                            ${{result.to_date ? `<span class="result-meta-item">📅 ${{new Date(result.to_date).toLocaleDateString()}}</span>` : ''}}
                        </div>
                        <div class="badges">${{badges}}</div>
                        ${{filesInfo}}
                        ${{errorInfo}}
                    </div>
                `;
            }}).join('');
            
            document.getElementById('filterInfo').textContent = `Showing ${{rawData.length}} result(s)`;
        }}

        // Initialize on load
        initializeRepoFilter();
        updateDisplay();
    </script>
</body>
</html>'''
    
    return html


if __name__ == "__main__":
    # Allow running directly
    import sys
    
    results_file = sys.argv[1] if len(sys.argv) > 1 else "results/results.json"
    output_file = sys.argv[2] if len(sys.argv) > 2 else "results/dashboard.html"
    
    build_dashboard(results_file, output_file)
