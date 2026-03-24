"""Generate the GitHub Pages dashboard (self-contained HTML with inline JS/CSS)."""

from __future__ import annotations

import html
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.state import load_json_or_default, save_json

logger = logging.getLogger(__name__)


def update_briefings_data(
    items: list[dict],
    leaderboard: list[dict],
    backlog_summary: dict,
    dropped_counts: dict,
    total_fetched: int,
    report_date: str,
    briefings_path: Path,
) -> None:
    """Append today's briefing to briefings.json.

    Args:
        items: Today's classified items.
        leaderboard: Today's leaderboard entries.
        backlog_summary: Backlog stats dict.
        dropped_counts: Dropped counts per layer.
        total_fetched: Total items fetched.
        report_date: Date string YYYY-MM-DD.
        briefings_path: Path to briefings.json.
    """
    briefings = load_json_or_default(briefings_path, [])

    entry = {
        "date": report_date,
        "items": items,
        "leaderboard": leaderboard,
        "backlog_summary": backlog_summary,
        "dropped_counts": dropped_counts,
        "total_fetched": total_fetched,
    }

    briefings.insert(0, entry)

    # Prune entries older than 90 days
    cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).strftime("%Y-%m-%d")
    briefings = [b for b in briefings if b.get("date", "9999") >= cutoff]

    save_json(briefings_path, briefings)
    logger.info("Briefings data updated: %d entries", len(briefings))


def build_dashboard(
    briefings_path: Path,
    backlog_path: Path,
    leaderboard_path: Path,
) -> str:
    """Build a complete self-contained HTML dashboard.

    Args:
        briefings_path: Path to briefings.json.
        backlog_path: Path to backlog.json.
        leaderboard_path: Path to leaderboard.json.

    Returns:
        Complete HTML string for docs/index.html.
    """
    briefings = load_json_or_default(briefings_path, [])
    backlog = load_json_or_default(backlog_path, {"items": []})
    leaderboard = load_json_or_default(leaderboard_path, {"leaderboard": []})

    briefings_json = json.dumps(briefings)
    backlog_json = json.dumps(backlog.get("items", []))
    leaderboard_json = json.dumps(leaderboard.get("leaderboard", []))

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI Intelligence Briefing — Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         background:#f1f5f9; color:#1e293b; }}
  .container {{ max-width:900px; margin:0 auto; padding:24px 16px; }}
  h1 {{ font-size:24px; font-weight:700; color:#0f172a; }}
  .subtitle {{ font-size:13px; color:#94a3b8; margin-top:4px; }}

  /* Tabs */
  .tabs {{ display:flex; gap:0; margin:24px 0 16px; border-bottom:2px solid #e2e8f0; }}
  .tab {{ padding:10px 20px; cursor:pointer; font-size:14px; font-weight:600;
          color:#64748b; border-bottom:2px solid transparent; margin-bottom:-2px;
          transition: all 0.2s; }}
  .tab:hover {{ color:#0f172a; }}
  .tab.active {{ color:#0f172a; border-bottom-color:#0f172a; }}
  .tab-content {{ display:none; }}
  .tab-content.active {{ display:block; }}

  /* Filters */
  .filters {{ display:flex; gap:8px; flex-wrap:wrap; margin-bottom:16px; }}
  .filter-btn {{ padding:6px 14px; border-radius:6px; border:1px solid #e2e8f0;
                 background:#fff; font-size:12px; cursor:pointer; font-weight:500; }}
  .filter-btn.active {{ background:#0f172a; color:#fff; border-color:#0f172a; }}
  .search-box {{ padding:8px 14px; border:1px solid #e2e8f0; border-radius:6px;
                 font-size:13px; width:100%; max-width:300px; }}

  /* Cards */
  .card {{ background:#fff; border-radius:8px; padding:16px 20px; margin-bottom:12px;
           box-shadow:0 1px 3px rgba(0,0,0,.06); border:1px solid #e2e8f0; }}
  .card-date {{ font-size:12px; color:#94a3b8; }}

  /* Tier badges */
  .badge {{ display:inline-block; font-size:10px; padding:3px 8px; border-radius:3px;
            font-weight:700; text-transform:uppercase; letter-spacing:.05em; color:#fff; }}
  .badge-gc {{ background:#ea580c; }}
  .badge-wyt {{ background:#2563eb; }}
  .badge-noted {{ background:#6b7280; }}

  /* Category badges */
  .cat-badge {{ display:inline-block; font-size:10px; padding:2px 6px; border-radius:3px;
                font-weight:600; text-transform:uppercase; letter-spacing:.05em; color:#fff; }}

  /* Leaderboard */
  .lb-entry {{ display:flex; gap:12px; padding:12px 0; border-bottom:1px solid #f1f5f9; }}
  .lb-rank {{ font-size:22px; font-weight:700; color:#0f172a; min-width:32px; }}
  .lb-title {{ font-size:15px; font-weight:600; color:#0f172a; }}
  .lb-rationale {{ font-size:13px; color:#475569; margin-top:4px; line-height:1.5; }}
  .lb-meta {{ font-size:12px; color:#94a3b8; margin-top:4px; }}

  /* Expandable */
  details {{ margin-top:8px; }}
  details summary {{ cursor:pointer; font-size:13px; font-weight:600; color:#2563eb; }}
  details .expand-content {{ margin-top:8px; padding:10px 14px; background:#f8fafc;
                             border-radius:4px; border-left:3px solid #e2e8f0; }}
  pre {{ white-space:pre-wrap; font-size:13px; font-family:monospace; }}

  /* Backlog */
  .backlog-item {{ padding:10px 0; border-bottom:1px solid #f1f5f9; }}
  .backlog-age {{ font-size:12px; color:#94a3b8; }}

  /* Chart */
  .chart-container {{ background:#fff; border-radius:8px; padding:16px;
                      box-shadow:0 1px 3px rgba(0,0,0,.06); border:1px solid #e2e8f0;
                      margin-bottom:16px; }}

  .backlog-item label {{ display:flex; align-items:center; gap:10px; cursor:pointer; }}
  .backlog-item input[type="checkbox"] {{ width:18px; height:18px; cursor:pointer;
    accent-color:#0f172a; flex-shrink:0; }}
  .backlog-item.completed {{ opacity:0.5; }}
  .backlog-item.completed strong {{ text-decoration:line-through; }}

  .empty {{ text-align:center; padding:40px; color:#94a3b8; }}
</style>
</head>
<body>
<div class="container">
  <h1>AI Intelligence Briefing</h1>
  <p class="subtitle">Last updated: {html.escape(now)}</p>

  <div class="tabs">
    <div class="tab active" onclick="switchTab('leaderboard')">Leaderboard</div>
    <div class="tab" onclick="switchTab('briefings')">Briefings</div>
    <div class="tab" onclick="switchTab('backlog')">Backlog</div>
    <div class="tab" onclick="switchTab('trend')">Trend</div>
  </div>

  <!-- Leaderboard Tab -->
  <div id="tab-leaderboard" class="tab-content active">
    <div id="leaderboard-list"></div>
  </div>

  <!-- Briefings Tab -->
  <div id="tab-briefings" class="tab-content">
    <div class="filters">
      <button class="filter-btn active" onclick="filterLayer(0, this)">All</button>
      <button class="filter-btn" onclick="filterLayer(1, this)">Anthropic</button>
      <button class="filter-btn" onclick="filterLayer(2, this)">Practitioner</button>
      <button class="filter-btn" onclick="filterLayer(3, this)">Industry</button>
      <span style="width:8px"></span>
      <button class="filter-btn active" onclick="filterTier('all', this)">All Tiers</button>
      <button class="filter-btn" onclick="filterTier('GAME_CHANGER', this)">Game Changer</button>
      <button class="filter-btn" onclick="filterTier('WORTH_YOUR_TIME', this)">Worth Your Time</button>
      <button class="filter-btn" onclick="filterTier('NOTED', this)">Noted</button>
    </div>
    <input type="text" class="search-box" placeholder="Search titles and content..."
           oninput="searchItems(this.value)">
    <div id="briefings-list" style="margin-top:12px;"></div>
  </div>

  <!-- Backlog Tab -->
  <div id="tab-backlog" class="tab-content">
    <div id="backlog-counter" style="margin-bottom:12px;font-size:13px;color:#475569;"></div>
    <div id="backlog-list"></div>
    <div id="backlog-completed-section"></div>
    <div style="margin-top:12px;display:flex;align-items:center;gap:12px;">
      <button id="clear-completed-btn" onclick="clearCompleted()"
              style="display:none;padding:6px 14px;border-radius:6px;border:1px solid #e2e8f0;
                     background:#fff;font-size:12px;cursor:pointer;font-weight:500;">
        Clear completed</button>
      <p style="margin:0;font-size:12px;color:#94a3b8;">
        These toggles save in your browser. To sync back to the repo:
        <code>python src/backlog.py --adopt &lt;id&gt;</code>
      </p>
    </div>
  </div>

  <!-- Trend Tab -->
  <div id="tab-trend" class="tab-content">
    <div class="chart-container">
      <canvas id="trendChart" height="200"></canvas>
    </div>
  </div>
</div>

<script>
const briefings = {briefings_json};
const backlogItems = {backlog_json};
const leaderboardEntries = {leaderboard_json};

let activeLayer = 0;
let activeTier = 'all';
let searchQuery = '';

// Tab switching
function switchTab(name) {{
  document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(el => el.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  event.target.classList.add('active');
}}

// Render leaderboard
function renderLeaderboard() {{
  const el = document.getElementById('leaderboard-list');
  if (!leaderboardEntries.length) {{
    el.innerHTML = '<div class="empty">No leaderboard yet.</div>';
    return;
  }}
  const catColors = {{
    NEW_CAPABILITY:'#2563eb', SKILL_GAP:'#7c3aed', BLOCKED_PROJECT:'#dc2626',
    STRATEGIC_MOVE:'#0d9488', PARADIGM_SHIFT:'#ea580c', APPLIED_PATTERN:'#ca8a04'
  }};
  el.innerHTML = leaderboardEntries.map(e => `
    <div class="lb-entry">
      <div class="lb-rank">${{e.rank}}</div>
      <div>
        <div class="lb-title">${{esc(e.title)}}
          <span class="cat-badge" style="background:${{catColors[e.category]||'#6b7280'}};margin-left:6px;">
            ${{e.category}}</span>
        </div>
        <div class="lb-rationale">${{esc(e.rationale||'')}}</div>
        <div class="lb-meta">
          First step: ${{esc(e.first_step||'')}} · Time: ${{esc(e.time_investment||'')}}
          · On board: ${{e.days_on_leaderboard||0}}d
        </div>
      </div>
    </div>
  `).join('');
}}

// Render briefings
function renderBriefings() {{
  const el = document.getElementById('briefings-list');
  let allItems = [];
  briefings.forEach(b => {{
    (b.items||[]).forEach(item => {{
      allItems.push({{...item, date: b.date}});
    }});
  }});

  // Apply filters
  if (activeLayer > 0) allItems = allItems.filter(i => i.layer === activeLayer);
  if (activeTier !== 'all') allItems = allItems.filter(i => i.tier === activeTier);
  if (searchQuery) {{
    const q = searchQuery.toLowerCase();
    allItems = allItems.filter(i =>
      (i.title||'').toLowerCase().includes(q) ||
      (i.what_it_is||'').toLowerCase().includes(q) ||
      (i.why_it_matters||'').toLowerCase().includes(q) ||
      (i.summary||'').toLowerCase().includes(q)
    );
  }}

  if (!allItems.length) {{
    el.innerHTML = '<div class="empty">No items match your filters.</div>';
    return;
  }}

  el.innerHTML = allItems.map(item => {{
    const badgeClass = item.tier==='GAME_CHANGER'?'badge-gc':item.tier==='WORTH_YOUR_TIME'?'badge-wyt':'badge-noted';
    const layerName = {{1:'Anthropic',2:'Practitioner',3:'Industry'}}[item.layer]||'';
    let expandable = '';
    if (item.expandable_implement) {{
      expandable += `<details><summary>Let me walk you through this</summary>
        <div class="expand-content"><pre>${{esc(item.expandable_implement)}}</pre></div></details>`;
    }}
    if (item.expandable_learn) {{
      expandable += `<details><summary>Here's what you need to know</summary>
        <div class="expand-content"><p>${{esc(item.expandable_learn)}}</p></div></details>`;
    }}
    return `<div class="card">
      <div class="card-date">${{item.date}} · ${{esc(item.source_name||'')}} · ${{layerName}}</div>
      <span class="badge ${{badgeClass}}">${{item.tier}}</span>
      <h3 style="margin:6px 0 4px;font-size:15px;">
        <a href="${{esc(item.url||'')}}" style="color:#0f172a;text-decoration:none;" target="_blank">
          ${{esc(item.title||'')}}</a></h3>
      <p style="font-size:13px;color:#475569;margin-bottom:4px;">${{esc(item.what_it_is||item.summary||'')}}</p>
      <p style="font-size:14px;color:#334155;line-height:1.6;">${{esc(item.why_it_matters||'')}}</p>
      ${{expandable}}
    </div>`;
  }}).join('');
}}

// Backlog localStorage helpers
const BACKLOG_PREFIX = 'backlog_completed_';
function isBacklogCompleted(id) {{ return localStorage.getItem(BACKLOG_PREFIX + id) === '1'; }}
function setBacklogCompleted(id, done) {{
  if (done) localStorage.setItem(BACKLOG_PREFIX + id, '1');
  else localStorage.removeItem(BACKLOG_PREFIX + id);
}}
function pruneBacklogStorage(validIds) {{
  const idSet = new Set(validIds);
  for (let i = localStorage.length - 1; i >= 0; i--) {{
    const key = localStorage.key(i);
    if (key && key.startsWith(BACKLOG_PREFIX)) {{
      const id = key.slice(BACKLOG_PREFIX.length);
      if (!idSet.has(id)) localStorage.removeItem(key);
    }}
  }}
}}
function toggleBacklogItem(id) {{
  setBacklogCompleted(id, !isBacklogCompleted(id));
  renderBacklog();
}}
function clearCompleted() {{
  const pending = backlogItems.filter(i => i.status === 'pending');
  pending.forEach(item => {{ if (isBacklogCompleted(item.id)) setBacklogCompleted(item.id, false); }});
  renderBacklog();
}}

// Render backlog
function renderBacklog() {{
  const el = document.getElementById('backlog-list');
  const completedEl = document.getElementById('backlog-completed-section');
  const counterEl = document.getElementById('backlog-counter');
  const clearBtn = document.getElementById('clear-completed-btn');
  const pending = backlogItems.filter(i => i.status === 'pending')
    .sort((a,b) => (a.date_added||'').localeCompare(b.date_added||''));

  // Prune orphaned localStorage keys for items no longer in the backlog
  pruneBacklogStorage(pending.map(i => i.id));

  if (!pending.length) {{
    el.innerHTML = '<div class="empty">No pending items. You\\'re caught up!</div>';
    completedEl.innerHTML = '';
    counterEl.textContent = '';
    clearBtn.style.display = 'none';
    return;
  }}

  const uncompleted = pending.filter(i => !isBacklogCompleted(i.id));
  const completed = pending.filter(i => isBacklogCompleted(i.id));

  // Update counter
  counterEl.textContent = completed.length > 0
    ? `${{completed.length}} of ${{pending.length}} items completed`
    : `${{pending.length}} pending items`;
  clearBtn.style.display = completed.length > 0 ? 'inline-block' : 'none';

  function renderItem(item) {{
    const badgeClass = item.tier==='GAME_CHANGER'?'badge-gc':'badge-wyt';
    const done = isBacklogCompleted(item.id);
    const cls = done ? 'backlog-item completed' : 'backlog-item';
    return `<div class="${{cls}}">
      <label>
        <input type="checkbox" ${{done?'checked':''}}
               onchange="toggleBacklogItem('${{item.id}}')" />
        <span class="badge ${{badgeClass}}">${{item.tier}}</span>
        <strong>${{esc(item.title||'')}}</strong>
        <span class="backlog-age">${{item.days_pending||0}}d pending · ${{item.id}}</span>
      </label>
    </div>`;
  }}

  el.innerHTML = uncompleted.map(renderItem).join('');

  if (completed.length) {{
    completedEl.innerHTML = '<p style="margin:16px 0 8px;font-size:12px;font-weight:600;'
      + 'color:#94a3b8;text-transform:uppercase;letter-spacing:.05em;">Completed</p>'
      + completed.map(renderItem).join('');
  }} else {{
    completedEl.innerHTML = '';
  }}
}}

// Render trend chart
function renderTrend() {{
  const last30 = briefings.slice(0, 30).reverse();
  const labels = last30.map(b => b.date);
  const gcData = last30.map(b => (b.items||[]).filter(i => i.tier==='GAME_CHANGER').length);
  const wytData = last30.map(b => (b.items||[]).filter(i => i.tier==='WORTH_YOUR_TIME').length);
  const notedData = last30.map(b => (b.items||[]).filter(i => i.tier==='NOTED').length);

  new Chart(document.getElementById('trendChart'), {{
    type: 'bar',
    data: {{
      labels,
      datasets: [
        {{ label:'Game Changer', data:gcData, backgroundColor:'#ea580c' }},
        {{ label:'Worth Your Time', data:wytData, backgroundColor:'#2563eb' }},
        {{ label:'Noted', data:notedData, backgroundColor:'#cbd5e1' }},
      ]
    }},
    options: {{
      responsive: true,
      plugins: {{ legend: {{ position:'top' }} }},
      scales: {{
        x: {{ stacked:true }},
        y: {{ stacked:true, beginAtZero:true, ticks:{{ stepSize:1 }} }}
      }}
    }}
  }});
}}

// Filters
function filterLayer(layer, btn) {{
  activeLayer = layer;
  btn.parentElement.querySelectorAll('.filter-btn').forEach((b,i) => {{
    if (i < 4) b.classList.toggle('active', b === btn);
  }});
  renderBriefings();
}}
function filterTier(tier, btn) {{
  activeTier = tier;
  btn.parentElement.querySelectorAll('.filter-btn').forEach((b,i) => {{
    if (i >= 5) b.classList.toggle('active', b === btn);
  }});
  renderBriefings();
}}
function searchItems(q) {{ searchQuery = q; renderBriefings(); }}

// Escape HTML
function esc(s) {{ const d=document.createElement('div'); d.textContent=s; return d.innerHTML; }}

// Init
renderLeaderboard();
renderBriefings();
renderBacklog();
renderTrend();
</script>
</body>
</html>"""
