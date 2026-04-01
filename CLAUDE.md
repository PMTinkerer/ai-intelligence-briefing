# AI Intelligence Briefing

## What this project does
Three-layer daily intelligence briefing with aggressive curation. Monitors Anthropic releases, practitioner insights, and industry news. Surfaces only what genuinely matters (3-7 items/day), provides expandable implementation/learning paths, tracks adoption via backlog, maintains a Top 5 Impact Leaderboard, and detects blocked-project unblockers.

## Verification commands
- `python3 -m pytest tests/ -v` — run all tests
- `python3 -m src.main --dry-run` — daily run without sending email or updating state
- `python3 -m src.main --layer 1 --dry-run` — run only Layer 1
- `python3 -m src.main` — full daily run
- `python3 -m src.weekly --dry-run` — weekly rollup without sending
- `python3 -m src.weekly` — full weekly rollup

## Key files
- `config/feeds.json` — add/remove/disable feeds (not in code)
- `config/business_context.md` — update when business tools or ambitions change
- `config/blocked_projects.json` — update when projects are blocked/unblocked/completed
- `data/backlog.json` — adoption tracking (mark items adopted via CLI or JSON edit)
- `data/leaderboard.json` — current Top 5 (auto-managed)
- `data/seen_items.json` — dedup state (auto-managed, pruned at 90 days)
- `data/briefings.json` — dashboard data (append-only, pruned at 90 days)

## Environment variables
| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | _(required)_ | Claude API key for classification |
| `GMAIL_CREDENTIALS_PATH` | `credentials.json` | OAuth client credentials file |
| `GMAIL_TOKEN_PATH` | `token.json` | Saved OAuth token (gitignored) |
| `BRIEFING_RECIPIENTS` | _(empty)_ | Comma-separated recipient addresses |
| `DASHBOARD_URL` | GitHub Pages URL | Full dashboard link |
| `SPENDING_BUDGET_USD` | `10.00` | Monthly API budget cap |

## Architecture notes
- RSS feeds only (no scraping, no X API)
- 4 API calls per daily run (3 layers + leaderboard), all Claude Sonnet 4.6 (`claude-sonnet-4-6`)
- 1 API call per weekly run (synthesis + backlog re-ranking)
- Feed list and blocked projects are config-driven JSON
- Each layer fails independently — partial results are still useful
- Most items are DROPPED — aggressive curation is the core value
- The classifier is a strategic advisor, not a keyword matcher
- Leaderboard is stable (max 2 changes/day) and reflects compounding capability, not recency
- Gmail API reuses the same OAuth pattern as the STR Daily Briefing

## Project Structure
```
ai-intelligence-briefing/
├── .github/workflows/
│   ├── daily-briefing.yml        # 5 AM ET daily
│   └── weekly-rollup.yml         # 9 AM ET Saturday
├── src/
│   ├── main.py                   # Daily orchestrator
│   ├── weekly.py                 # Weekly orchestrator
│   ├── fetch_feeds.py            # RSS fetching, dedup, content extraction
│   ├── classify.py               # 4 API calls: 3 layers + leaderboard
│   ├── backlog.py                # Adoption tracking + CLI
│   ├── generate_email.py         # Daily HTML email builder
│   ├── generate_weekly.py        # Weekly rollup email builder
│   ├── generate_dashboard.py     # Dashboard HTML + data management
│   ├── send_email.py             # Gmail API (send-only)
│   ├── config.py                 # Environment variable loading
│   ├── state.py                  # JSON persistence utilities
│   └── spending_guard.py         # API budget enforcement
├── config/
│   ├── feeds.json                # RSS feed configuration
│   ├── business_context.md       # Classifier system prompt
│   └── blocked_projects.json     # Blocked project registry
├── data/                         # Auto-managed state files
├── docs/
│   └── index.html                # GitHub Pages dashboard
└── tests/
```

## Coding Standards
- Type hints on all function signatures
- Docstrings on all public functions (one-line summary + args/returns)
- Use logging module, not print statements
- All config via environment variables or config files, never hardcoded
- Handle missing/malformed data gracefully — log warning, don't crash
- Never commit credentials. .env and token files are in .gitignore.

## Before Saying You're Done
Run these after every change:
- `python3 -m pytest tests/ -v`
- `python3 -m src.main --dry-run`

## Common Mistakes to Avoid
- RSS feeds use different formats (RSS 2.0, Atom) — feedparser handles both
- Some feeds return bozo errors but still have usable entries — check `parsed.entries` not just `parsed.bozo`
- Gmail API email bodies must be base64url-encoded — use `base64.urlsafe_b64encode`
- The leaderboard prompt must include previous day's leaderboard for stability
- Don't add items to backlog without checking for duplicates (same ID)
- State files may not exist on first run — always use `load_json_or_default`

## Supply Chain Security

This project follows the global supply chain security standard defined in `~/CLAUDE.md`. All dependencies must be pinned to exact versions, GitHub Actions must be SHA-pinned, and pip-audit must run in CI.
