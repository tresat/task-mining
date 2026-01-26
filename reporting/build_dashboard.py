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
    <title>GitHub Update Mining</title>
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

        input[type="text"] {{
            background-color: var(--card-bg);
            color: var(--text-primary);
            border: 1px solid var(--border);
            padding: 0.5rem 1rem;
            border-radius: 0.5rem;
            font-size: 1rem;
            min-width: 300px;
        }}

        input[type="text"]:focus {{
            outline: none;
            border-color: var(--accent);
        }}

        input[type="text"]::placeholder {{
            color: var(--text-secondary);
            opacity: 0.7;
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
            padding: 0.5rem;
            border-radius: 0.5rem;
            background: rgba(255, 255, 255, 0.05);
        }}

        .stat-value {{
            font-size: 1.5rem;
            font-weight: 700;
            color: var(--accent);
        }}

        .stat-label {{
            font-size: 0.8rem;
            color: var(--text-secondary);
            margin-top: 0.1rem;
        }}

        .tags-section {{
            margin-top: 1rem;
            padding-top: 1rem;
            border-top: 1px solid var(--border);
        }}

        .tags-title {{
            font-size: 0.9rem;
            font-weight: 600;
            color: var(--text-secondary);
            margin-bottom: 0.75rem;
        }}

        .tags-list {{
            display: flex;
            flex-wrap: wrap;
            gap: 0.5rem;
        }}

        .tag-filter {{
            padding: 0.4rem 0.8rem;
            border-radius: 0.375rem;
            font-size: 0.85rem;
            font-weight: 600;
            background-color: rgba(56, 189, 248, 0.2);
            color: var(--accent);
            cursor: pointer;
            transition: all 0.2s;
            border: 1px solid transparent;
        }}

        .tag-filter:hover {{
            background-color: rgba(56, 189, 248, 0.3);
            border-color: var(--accent);
        }}

        .tag-filter.active {{
            background-color: var(--accent);
            color: var(--bg-color);
        }}

        .clear-filters {{
            margin-top: 0.75rem;
            padding: 0.4rem 0.8rem;
            border-radius: 0.375rem;
            font-size: 0.85rem;
            font-weight: 600;
            background-color: rgba(248, 113, 113, 0.2);
            color: #f87171;
            cursor: pointer;
            transition: all 0.2s;
            border: 1px solid transparent;
            display: inline-block;
        }}

        .clear-filters:hover {{
            background-color: rgba(248, 113, 113, 0.3);
            border-color: #f87171;
        }}

        .clear-filters.hidden {{
            display: none;
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

        .download-btn {{
            padding: 0.6rem 1.2rem;
            border-radius: 0.5rem;
            font-size: 0.95rem;
            font-weight: 600;
            background-color: var(--accent);
            color: var(--bg-color);
            cursor: pointer;
            transition: all 0.2s;
            border: none;
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
        }}

        .download-btn:hover {{
            background-color: var(--accent-hover);
        }}

        .download-btn:disabled {{
            opacity: 0.5;
            cursor: not-allowed;
        }}

        .result-card {{
            position: relative;
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
            gap: 1rem;
        }}

        .result-checkbox {{
            position: relative;
            top: 0.25rem;
            width: 1.2rem;
            height: 1.2rem;
            cursor: pointer;
            accent-color: var(--accent);
        }}

        .result-title-wrapper {{
            display: flex;
            align-items: start;
            gap: 0.75rem;
            flex: 1;
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
            cursor: pointer;
            transition: all 0.2s;
        }}

        .badge-tag:hover {{
            background-color: rgba(56, 189, 248, 0.3);
            transform: scale(1.05);
        }}

        .result-meta {{
            display: flex;
            gap: 1.5rem;
            color: var(--text-secondary);
            font-size: 0.9rem;
            margin-bottom: 0.75rem;
            align-items: flex-start;
        }}

        .result-meta-left {{
            display: flex;
            gap: 1.5rem;
            flex-wrap: wrap;
            flex: 1;
        }}

        .result-meta-right {{
            margin-left: auto;
            text-align: right;
            max-width: 40%;
        }}

        .result-meta-item {{
            display: flex;
            align-items: center;
            gap: 0.25rem;
        }}

        .files-list {{
            color: var(--text-secondary);
            font-size: 0.85rem;
        }}

        .files-list-title {{
            font-weight: 600;
            margin-bottom: 0.25rem;
            color: var(--text-secondary);
        }}

        .file-item {{
            margin-bottom: 0.1rem;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }}

        .more-files {{
            font-style: italic;
            opacity: 0.7;
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
            <h1>GitHub Update Mining</h1>
            <p class="subtitle">Interactive analysis of project modifications</p>
        </header>

        <div class="controls">
            <div class="control-group">
                <label for="repoFilter">Repository:</label>
                <select id="repoFilter" onchange="updateDisplay()">
                    <option value="ALL">ALL</option>
                </select>
            </div>
            <div class="control-group">
                <label for="searchInput">Search:</label>
                <input type="text" id="searchInput" placeholder="Search in titles, repos, tags..." oninput="updateDisplay()">
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
                <div class="tags-section">
                    <div class="tags-title">Filter by Tags</div>
                    <div class="tags-list" id="tagsList"></div>
                    <div class="clear-filters hidden" id="clearFilters" onclick="clearFilters()">Clear Filters</div>
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
                <div style="display: flex; align-items: center; gap: 1rem;">
                    <span class="filter-info" id="filterInfo"></span>
                    <button class="download-btn" id="downloadBtn" onclick="downloadSelected()" disabled>
                        <span>📥</span>
                        <span id="downloadBtnText">Download Selected</span>
                    </button>
                </div>
            </div>
            <div id="resultsContainer"></div>
        </div>
    </div>

    <script>
        const rawData = {raw_data_json};

        let chart = null;
        let currentRepoFilter = 'ALL';
        let selectedTags = new Set();
        let currentCategoryFilter = null;
        let selectedItems = new Set();
        let currentSearchText = '';

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
            let filtered = rawData;
            
            // Filter by repository
            if (currentRepoFilter !== 'ALL') {{
                filtered = filtered.filter(r => r.repo_url === currentRepoFilter);
            }}
            
            // Filter by tag
            if (selectedTags.size > 0) {{
                filtered = filtered.filter(r => 
                    r.tags && Array.isArray(r.tags) && r.tags.some(tag => selectedTags.has(tag))
                );
            }}
            
            // Filter by category
            if (currentCategoryFilter) {{
                filtered = filtered.filter(r => 
                    (r.category || 'Other') === currentCategoryFilter
                );
            }}
            
            // Filter by search text
            if (currentSearchText) {{
                const searchLower = currentSearchText.toLowerCase();
                filtered = filtered.filter(r => {{
                    // Search in title (to_msg)
                    const title = (r.to_msg || r.from_msg || '').toLowerCase();
                    if (title.includes(searchLower)) return true;
                    
                    // Search in repo name
                    const repoName = (r.repo_url || '').toLowerCase();
                    if (repoName.includes(searchLower)) return true;
                    
                    // Search in category
                    const category = (r.category || '').toLowerCase();
                    if (category.includes(searchLower)) return true;
                    
                    // Search in tags
                    if (r.tags && Array.isArray(r.tags)) {{
                        const tagMatch = r.tags.some(tag => tag.toLowerCase().includes(searchLower));
                        if (tagMatch) return true;
                    }}
                    
                    // Search in files
                    if (r.files_changed && Array.isArray(r.files_changed)) {{
                        const fileMatch = r.files_changed.some(f => 
                            (f.filename || '').toLowerCase().includes(searchLower)
                        );
                        if (fileMatch) return true;
                    }}
                    
                    return false;
                }});
            }}
            
            return filtered;
        }}

        function updateDisplay() {{
            currentRepoFilter = document.getElementById('repoFilter').value;
            currentSearchText = document.getElementById('searchInput').value.trim();
            // Clear selections when filters change
            selectedItems.clear();
            updateStats();
            updateTagsList();
            updateChart();
            displayResults();
            updateClearFiltersButton();
        }}

        function clearFilters() {{
            selectedTags.clear();
            currentCategoryFilter = null;
            updateDisplay();
        }}

        function updateClearFiltersButton() {{
            const clearBtn = document.getElementById('clearFilters');
            if (selectedTags.size > 0 || currentCategoryFilter) {{
                clearBtn.classList.remove('hidden');
            }} else {{
                clearBtn.classList.add('hidden');
            }}
        }}

        function filterByTag(tag) {{
            if (selectedTags.has(tag)) {{
                selectedTags.delete(tag);
            }} else {{
                selectedTags.add(tag);
                currentCategoryFilter = null; // Clear category filter when tag is selected
            }}
            updateDisplay();
        }}

        function filterByCategory(category) {{
            if (currentCategoryFilter === category) {{
                currentCategoryFilter = null;
            }} else {{
                currentCategoryFilter = category;
                selectedTags.clear(); // Clear tag filters when category is selected
            }}
            updateDisplay();
        }}

        function updateTagsList() {{
            // Get all unique tags from current repository filter
            const filteredByRepo = currentRepoFilter === 'ALL' ? rawData : 
                rawData.filter(r => r.repo_url === currentRepoFilter);
            
            const tagsSet = new Set();
            filteredByRepo.forEach(r => {{
                if (r.tags && Array.isArray(r.tags)) {{
                    r.tags.forEach(tag => tagsSet.add(tag));
                }}
            }});
            
            const tagsList = document.getElementById('tagsList');
            const sortedTags = Array.from(tagsSet).sort();
            
            if (sortedTags.length === 0) {{
                tagsList.innerHTML = '<span style="color: var(--text-secondary); font-size: 0.85rem;">No tags available</span>';
                return;
            }}
            
            tagsList.innerHTML = sortedTags.map(tag => {{
                const activeClass = selectedTags.has(tag) ? ' active' : '';
                return `<span class="tag-filter${{activeClass}}" onclick="filterByTag('${{tag}}')">${{tag}}</span>`;
            }}).join('');
        }}

        function updateStats() {{
            const filteredData = getFilteredData();
            const totalCount = filteredData.length;
            const repos = new Set(filteredData.map(r => r.repo_url)).size;
            
            const categories = new Set();
            filteredData.forEach(r => {{
                if (r.category) {{
                    categories.add(r.category);
                }}
            }});
            
            document.getElementById('totalCount').textContent = totalCount;
            document.getElementById('categoryCount').textContent = categories.size;
            document.getElementById('repoCount').textContent = repos;
        }}

        function updateChart() {{
            const ctx = document.getElementById('distributionChart').getContext('2d');
            const filteredData = getFilteredData();
            
            // Count by category
            const counts = {{}};
            filteredData.forEach(r => {{
                const cat = r.category || 'Other';
                counts[cat] = (counts[cat] || 0) + 1;
            }});
            
            const labels = Object.keys(counts);
            const data = Object.values(counts);
            
            if (chart) {{
                chart.destroy();
            }}
            
            document.getElementById('chartTitle').textContent = 'Distribution by Category';
            
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
                    onClick: (event, activeElements) => {{
                        if (activeElements.length > 0) {{
                            const index = activeElements[0].index;
                            const category = labels[index];
                            filterByCategory(category);
                        }}
                    }},
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
                        }},
                        tooltip: {{
                            callbacks: {{
                                label: function(context) {{
                                    const label = context.label || '';
                                    const value = context.parsed || 0;
                                    const total = context.dataset.data.reduce((a, b) => a + b, 0);
                                    const percentage = ((value / total) * 100).toFixed(1);
                                    return `${{label}}: ${{value}} (${{percentage}}%)`;
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
            
            container.innerHTML = filteredData.map((result, index) => {{
                const resultId = `result-${{index}}`;
                const repoName = result.repo_url ? result.repo_url.split('/').slice(-2).join('/') : 'Unknown';
                const prUrl = result.pr_id && result.repo_url ? 
                    `${{result.repo_url}}/pull/${{result.pr_id}}` : null;
                const commitUrl = result.repo_url && result.to_commit ?
                    `${{result.repo_url}}/commit/${{result.to_commit}}` : null;
                const prLink = result.pr_id ? 
                    `<a href="${{prUrl}}" target="_blank">#${{result.pr_id}}</a>` :
                    null;
                
                // Determine title: for PRs use first line of to_msg, for commits use to_msg
                let title = 'No message';
                if (result.to_msg) {{
                    if (result.pr_id) {{
                        // For PRs, extract first line before \\n\\n
                        const firstLineMatch = result.to_msg.split('\\n\\n')[0];
                        title = firstLineMatch || result.to_msg;
                    }} else {{
                        // For commits, use the full commit message
                        title = result.to_msg;
                    }}
                }} else if (result.from_msg) {{
                    title = result.from_msg;
                }}
                
                const link = prUrl || commitUrl || '#';
                let badges = '';
                if (result.category) {{
                    const badgeClass = result.category === 'Unknown' ? 'badge-unknown' : 'badge-category';
                    badges += `<span class="badge ${{badgeClass}}">${{result.category}}</span>`;
                }}
                
                if (result.tags && Array.isArray(result.tags) && result.tags.length > 0) {{
                    result.tags.forEach(tag => {{
                        badges += `<span class="badge badge-tag" onclick="event.stopPropagation(); filterByTag('${{tag}}')">${{tag}}</span>`;
                    }});
                }}
                
                // Build files changed info
                let filesInfo = '';
                let filesMetaInfo = '';
                if (result.files_changed && result.files_changed.length > 0) {{
                    const maxFilesToShow = 3;
                    const filesToDisplay = result.files_changed.slice(0, maxFilesToShow);
                    const remainingCount = result.files_changed.length - maxFilesToShow;
                    
                    filesMetaInfo = '<div class="files-list">';
                    filesMetaInfo += '<div class="files-list-title">Files changed:</div>';
                    filesToDisplay.forEach(f => {{
                        const fileName = f.filename || f;
                        filesMetaInfo += `<div class="file-item">${{fileName}}</div>`;
                    }});
                    if (remainingCount > 0) {{
                        filesMetaInfo += `<div class="more-files">+${{remainingCount}} more...</div>`;
                    }}
                    filesMetaInfo += '</div>';
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
                
                return `
                    <div class="result-card" data-index="${{index}}">
                        <div class="result-header">
                            <div class="result-title-wrapper">
                                <input type="checkbox" class="result-checkbox" id="${{resultId}}" onchange="toggleSelection(${{index}})" ${{selectedItems.has(index) ? 'checked' : ''}}>
                                <a href="${{link}}" target="_blank" class="result-title">${{title}}</a>
                            </div>
                        </div>
                        <div class="result-meta">
                            <div class="result-meta-left">
                                <span class="result-meta-item">📦 ${{repoName}}</span>
                                ${{prLink ? `<span class="result-meta-item">PR ${{prLink}}</span>` : ''}}
                                ${{result.to_date ? `<span class="result-meta-item">📅 ${{new Date(result.to_date).toLocaleDateString()}}</span>` : ''}}
                            </div>
                            ${{filesMetaInfo ? `<div class="result-meta-right">${{filesMetaInfo}}</div>` : ''}}
                        </div>
                        <div class="badges">${{badges}}</div>
                        ${{filesInfo}}
                        ${{errorInfo}}
                    </div>
                `;
            }}).join('');
            
            document.getElementById('filterInfo').textContent = `Showing ${{filteredData.length}} result(s)`;
            
            // Add filter status
            if (selectedTags.size > 0 || currentCategoryFilter) {{
                let filterText = '';
                if (selectedTags.size > 0) {{
                    const tagsList = Array.from(selectedTags).join(', ');
                    filterText = ` (filtered by tags: ${{tagsList}})`;
                }} else if (currentCategoryFilter) {{
                    filterText = ` (filtered by category: ${{currentCategoryFilter}})`;
                }}
                document.getElementById('filterInfo').textContent += filterText;
            }}
            
            // Update download button state
            updateDownloadButton();
        }}

        function toggleSelection(index) {{
            if (selectedItems.has(index)) {{
                selectedItems.delete(index);
            }} else {{
                selectedItems.add(index);
            }}
            updateDownloadButton();
        }}

        function updateDownloadButton() {{
            const downloadBtn = document.getElementById('downloadBtn');
            const btnText = document.getElementById('downloadBtnText');
            const count = selectedItems.size;
            
            if (count > 0) {{
                downloadBtn.disabled = false;
                btnText.textContent = `Download Selected (${{count}})`;
            }} else {{
                downloadBtn.disabled = true;
                btnText.textContent = 'Download Selected';
            }}
        }}

        function downloadSelected() {{
            if (selectedItems.size === 0) {{
                alert('Please select at least one item to download.');
                return;
            }}

            // Prompt for filename
            const defaultFilename = `selected_results_${{new Date().toISOString().split('T')[0]}}.json`;
            const filename = prompt('Enter filename for the download:', defaultFilename);
            
            if (!filename) {{
                return; // User cancelled
            }}

            // Get filtered data and select only checked items
            const filteredData = getFilteredData();
            const selectedData = Array.from(selectedItems)
                .map(index => filteredData[index])
                .filter(item => item !== undefined);

            // Create JSON blob
            const jsonStr = JSON.stringify(selectedData, null, 2);
            const blob = new Blob([jsonStr], {{ type: 'application/json' }});
            
            // Create download link
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = filename.endsWith('.json') ? filename : filename + '.json';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
            
            // Show success message
            alert(`Downloaded ${{selectedData.length}} item(s) to ${{a.download}}`);
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
