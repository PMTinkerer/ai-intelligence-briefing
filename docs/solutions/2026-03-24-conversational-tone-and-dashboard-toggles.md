# Conversational Tone Rewrite & Dashboard Completion Toggles

**Date:** 2026-03-24
**Status:** Shipped
**Branch:** `feat/conversational-tone-dashboard-toggles`

## Problem

The daily email briefing read like a textbook — clinical, terse, data-card style. The user wanted it to feel like an endlessly patient teacher walking them through each development: what it is, what it means for their business, and how/why to implement it. Separately, the dashboard's Backlog tab had no interactive way to mark items as completed — the only path was CLI (`python src/backlog.py --adopt <id>`) or editing JSON directly.

## What We Changed

### 1. Classifier Prompts (`src/classify.py`)

**Before:** Output instructions were clinical — "1-2 sentence plain-language description", "paste-ready artifact", "key concept, mental model, docs link."

**After:** Added a `VOICE & TONE` block to all three layer prompts instructing the classifier to write as a warm, patient teacher. Field-by-field changes:

| Field | Before | After |
|-------|--------|-------|
| `what_it_is` | "1-2 sentence plain-language description" | "2-3 sentences, explain as if telling a smart friend what just happened" |
| `why_it_matters` | "2-3 sentences specific to the operator's context" | "3-4 sentences, connect to their specific business like a mentor" |
| `expandable_implement` | "paste-ready artifact" | "Walk through step-by-step like a teacher sitting next to them, include commands but explain each step" |
| `expandable_learn` | "key concept, mental model, docs link" | "Teach the concept building on what they already know, suggest an experiment" |
| Layer 3 `summary` | "1-2 sentence summary" | "2-3 sentence conversational summary" |

**Key decision:** Field names (`what_it_is`, `why_it_matters`, etc.) and JSON schema stayed exactly the same. Only the prompt instructions changed. This preserved backward compatibility with all existing data, dashboard rendering, and tests.

**Cost consideration:** Conversational text is longer than terse text. Output tokens cost $15/MTok. Estimated ~$0.50-1.00/month increase against the $10 budget. Prompts guide toward "warm and direct, not verbose" to control this.

### 2. Email Template (`src/generate_email.py`)

Softened section headers and static text to match the conversational tone:

| Element | Before | After |
|---------|--------|-------|
| Items header | "Today's Briefing" | "Here's what caught my attention today" |
| Implement label | "Help me implement this" | "Let me walk you through this" |
| Learn label | "Help me learn this" | "Here's what you need to know" |
| Filter transparency | "Reviewed X items. Surfaced Y. Noted Z. Dropped W." | "I looked through X items today. Y were worth your time, Z were noted for the record, and I dropped W." |
| Quiet day | "Quiet day — nothing worth your time today. All systems running. The filter is working." | "Nothing jumped out at me today — and that's a good thing. I'm still watching everything. When something matters, you'll be the first to know." |

**What didn't change:** Subject line format, leaderboard section, backlog summary, CTA button, footer. These are functional or already read well.

### 3. Dashboard Backlog Toggles (`src/generate_dashboard.py`)

Added interactive checkboxes to the Backlog tab:

- Each pending item gets a checkbox
- Toggle state persists via `localStorage` (keyed as `backlog_completed_{id}`)
- Checked items get strikethrough + 50% opacity, moved to a "Completed" section below
- Counter shows "X of Y items completed"
- "Clear completed" button resets all toggles
- Orphaned localStorage keys are garbage-collected on page load (handles items auto-archived by the 21-day pipeline)

**Architecture decision:** localStorage, not server sync. The dashboard is a static GitHub Pages site with no backend. localStorage is pragmatic for a single-user personal dashboard. Trade-off: state is device-local. The CLI `--adopt` command remains the canonical way to sync status back to `data/backlog.json`.

**Stale state handling:** When the daily pipeline auto-archives an item after 21 days, it disappears from the rendered backlog (status changes from `pending` to `archived`). The `pruneBacklogStorage()` function removes orphaned localStorage keys on every render so the counter stays accurate.

### 4. Dashboard Labels (`src/generate_dashboard.py`)

Updated expandable section labels in the Briefings tab to match the email: "Let me walk you through this" / "Here's what you need to know."

## What We Didn't Change (Scope Boundaries)

- **Weekly rollup** — Uses a separate prompt in `src/generate_weekly.py`. Can be updated for consistency in a follow-up.
- **Leaderboard prompt** — Already reads differently from the item prompts. Left as-is.
- **Tier definitions / scoring logic** — Tone changed, not curation standards. The aggressive filtering philosophy is preserved.
- **Feed sources or delivery schedule** — Untouched.
- **Briefings/Leaderboard/Trend tabs** — Toggles only on Backlog tab.

## Tests Updated

- `tests/test_email.py`: Updated 2 assertions — `test_daily_email_filter_transparency` (new wording) and `test_daily_email_quiet_day` (new message)
- `tests/test_dashboard.py`: Added `test_dashboard_backlog_has_toggle_checkboxes` verifying checkbox inputs, localStorage usage, toggle/clear functions, garbage collection, and counter element
- `tests/test_classify.py`: No changes needed — tests mock API responses, don't assert on prompt text

**Final verification:** 51/51 tests pass. `--dry-run` pipeline executes successfully.

## Lessons Learned

1. **The tone lives in the classifier prompts, not the email template.** The email template is just presentation — the actual text content comes from the classifier's output fields. To change how the briefing *reads*, you change the classifier prompt instructions first, then adjust the template framing second.

2. **Changing prompt output style has a cost impact.** Conversational text is ~30-50% longer than terse text. At $15/MTok output, this is material on a $10/month budget. Always include length guidance in tone instructions ("warm doesn't mean wordy") to prevent runaway verbosity.

3. **localStorage garbage collection is necessary for dashboard overlays.** When client-side state (localStorage) overlays server-generated data (backlog JSON embedded at build time), items can be removed server-side (auto-archived) while localStorage retains stale keys. Always cross-reference localStorage against the current rendered set and prune orphans.

4. **Identify specific test assertions that will break before changing text.** The plan's deepening pass identified `"Reviewed 25 items"` and `"Quiet day"` as exact string assertions in tests. Knowing this upfront prevented a debug cycle.

5. **Field names are API contracts — change instructions, not schema.** Keeping `what_it_is`, `why_it_matters`, etc. unchanged preserved compatibility with existing `briefings.json` data, dashboard rendering, backlog pipeline, and all tests. The tone shift is entirely in prompt instructions.

6. **Historical data will show a tone shift.** Old items in `briefings.json` retain their original terse text. The dashboard Briefings tab will show a visible difference when scrolling through history. This resolves naturally as entries are pruned at 90 days. Not worth retroactive re-classification.
