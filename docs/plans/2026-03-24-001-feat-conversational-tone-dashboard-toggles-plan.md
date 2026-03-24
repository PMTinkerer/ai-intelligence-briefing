---
title: "feat: Conversational briefing tone and dashboard completion toggles"
type: feat
status: completed
date: 2026-03-24
deepened: 2026-03-24
---

# feat: Conversational briefing tone and dashboard completion toggles

## Overview

Two changes to how the briefing communicates with its reader: (1) rewrite the classifier prompts and email template so the daily briefing reads like a patient teacher walking you through developments — not a textbook summary — and (2) add interactive toggle checkboxes to the dashboard's Backlog tab so items can be marked as completed directly in the browser.

## Problem Frame

The daily email is factual and terse. The classifier prompts instruct outputs like "1-2 sentence plain-language description" and "2-3 sentences specific to the operator's context," producing clinical text. The email template reinforces this with data-card-style layout and section headers like "Today's Briefing." The user wants a tone that feels like a knowledgeable mentor sitting next to them, explaining what happened, why it matters to *their* business, and how to act on it.

Separately, the dashboard's Backlog tab shows pending items but the only way to mark them as adopted is via CLI (`python src/backlog.py --adopt <id>`) or editing JSON. The user expected interactive toggle buttons in the browser.

## Requirements Trace

- R1. Daily email briefing reads in a warm, conversational teacher tone — not clinical or textbook-like
- R2. Each item explains what the development is, what it means for the user's business, and how/why to implement it — in approachable language
- R3. Expandable implementation and learning sections read like walkthrough guidance from a mentor, not reference cards
- R4. Dashboard Backlog tab has interactive toggle checkboxes to mark items as completed
- R5. Toggle state persists across browser sessions (localStorage)
- R6. Existing aggressive curation philosophy is preserved — tone changes, not filtering standards

## Scope Boundaries

- Tone changes apply to daily email and classifier prompts only (weekly rollup is out of scope unless the user requests it later)
- Toggle buttons appear on the Backlog tab only — not Briefings, Leaderboard, or Trend tabs
- Dashboard toggles use localStorage for persistence; they do not sync back to `data/backlog.json` on the server. The user can still use the CLI for repo-level sync
- No changes to feed sources, scoring logic, tier definitions, or delivery schedule
- No changes to the leaderboard prompt or leaderboard email section (already reads differently)
- Layer 3 items (industry news) use a simpler schema (`summary` instead of `what_it_is`/`why_it_matters`) — the tone change applies to the `summary` field instruction

## Context & Research

### Relevant Code and Patterns

- `src/classify.py` — Classifier prompts at `_LAYER_1_PROMPT`, `_LAYER_2_PROMPT`, `_LAYER_3_PROMPT`. These control the *content* of all briefing text. Output schema defines fields like `what_it_is`, `why_it_matters`, `expandable_implement`, `expandable_learn`, `summary`
- `config/business_context.md` — System prompt injected into Layer 1. Sets the "strategic advisor" persona. The classifier philosophy section already has the right *intent* ("You are a strategic advisor to an ambitious operator") but the output instructions are clinical
- `src/generate_email.py` — Email template with section renderers (`_render_items`, `_render_header`, `_render_quiet_day`, etc.). Uses inline-styled HTML table layout
- `src/generate_dashboard.py` — Self-contained HTML generator. Dashboard uses embedded JSON data and vanilla JS. Backlog tab renders via `renderBacklog()` function. Currently read-only
- `src/backlog.py` — CLI for `--adopt <id>`. The backlog item lifecycle: `pending` → `adopted` or `archived`
- `src/state.py` — `load_json_or_default()` / `save_json()` pattern for all state files
- `tests/test_email.py` — 9 tests covering subject lines, section rendering, quiet day, filter transparency
- `tests/test_classify.py` — 9 tests covering classification, JSON parsing, budget enforcement
- `tests/test_dashboard.py` — 3 tests covering data append, HTML output

### Institutional Learnings

No `docs/solutions/` directory exists in this project.

## Key Technical Decisions

- **Tone change via prompt instructions, not field renaming**: The JSON schema field names (`what_it_is`, `why_it_matters`, etc.) stay the same. Only the prompt instructions for *how* to write those fields change. This preserves backward compatibility with existing briefing data, dashboard rendering, and tests
- **localStorage for dashboard toggles**: The dashboard is a static GitHub Pages site with no backend. localStorage is the pragmatic choice for a single-user personal dashboard. Trade-off: state is device-local and won't sync to `data/backlog.json` automatically. A note in the UI makes this clear
- **No additional API calls, minor output cost increase**: The tone change is purely in the prompt instructions. No new API calls, no model changes. However, conversational text is longer than terse text — expect classifier output tokens to increase ~30-50% per call. At $15/MTok output, this could add ~$0.50-1.00/month against the $10 budget. Well within limits but worth monitoring after the first live run
- **Preserve the filter transparency line**: The factual "Reviewed X items. Surfaced Y." line stays, but gets a warmer framing. This is a trust-building feature and should not be made vague

## Open Questions

### Resolved During Planning

- **Should Layer 3 get the same tone treatment?** Yes. Layer 3 uses a `summary` field instead of `what_it_is`/`why_it_matters`, but the prompt instruction for that field should also shift from terse to conversational
- **Should the weekly rollup tone change too?** Out of scope for now. The weekly rollup (`src/generate_weekly.py` + `src/weekly.py`) uses a separate synthesis prompt. Can be addressed in a follow-up if the user wants consistency

### Deferred to Implementation

- **Exact wording of prompt instructions**: The precise phrasing for "write like a patient teacher" will be tuned during implementation. The plan establishes the *direction*, not the exact prompt text
- **Visual styling of toggled backlog items**: Whether checked items get strikethrough, opacity reduction, or move to a separate section — exact treatment determined during implementation

## Implementation Units

- [x] **Unit 1: Rewrite classifier prompts for conversational teacher tone**

**Goal:** Change the output instructions in all three layer prompts so the classifier produces warm, walkthrough-style text instead of clinical descriptions.

**Requirements:** R1, R2, R3, R6

**Dependencies:** None

**Files:**
- Modify: `src/classify.py`
- Test: `tests/test_classify.py`

**Approach:**
- In `_LAYER_1_PROMPT` and `_LAYER_2_PROMPT`, replace output field instructions:
  - `what_it_is`: from "1-2 sentence plain-language description" → instruct to explain the development conversationally, as if telling a smart friend what just happened
  - `why_it_matters`: from "2-3 sentences specific to the operator's context" → instruct to connect it to the user's specific business and explain the implication warmly, like a mentor pointing out why they should care
  - `expandable_implement`: from "paste-ready artifact" → instruct to walk through the implementation step-by-step like a patient teacher sitting next to them, still including concrete commands/snippets but wrapped in explanatory prose
  - `expandable_learn`: from "key concept, mental model, docs link" → instruct to explain the concept like a teacher building understanding, with suggested experiments framed conversationally
- In `_LAYER_3_PROMPT`, update `summary` field instruction from "1-2 sentence summary" → instruct for a conversational summary that explains what happened and why it matters
- Add a voice/tone instruction at the top of each prompt: something like "Write as if you're a knowledgeable, endlessly patient teacher who genuinely wants this person to understand and succeed. Never lecture. Never use jargon without explaining it. Be warm, direct, and practical."
- Do NOT change tier definitions, JSON schema, field names, or classification standards
- Be mindful that longer conversational output = more output tokens = higher cost per call. Guide the tone toward warm and direct, not verbose. The goal is a conversational teacher, not a rambling one. Keep `what_it_is` to 2-3 sentences, `why_it_matters` to 3-4 sentences — longer than today but not unbounded

**Patterns to follow:**
- Existing prompt structure in `classify.py` — system prompt with format instructions and JSON schema
- `business_context.md` already models good conversational persona writing (the "Classifier Philosophy" section)

**Test scenarios:**
- Classification still returns valid JSON with all expected fields
- Markdown code fence stripping still works
- Budget enforcement still triggers correctly
- Layer isolation still holds (one layer failing doesn't break others)
- Existing test mocks may need response text updates if tests assert on prompt content

**Verification:**
- `python3 -m pytest tests/test_classify.py -v` passes
- `python3 -m src.main --dry-run` produces output with warmer, more conversational text in item descriptions

---

- [x] **Unit 2: Update email template for conversational presentation**

**Goal:** Adjust the email template's framing, section headers, and quiet-day message to complement the new conversational tone from the classifier.

**Requirements:** R1, R2

**Dependencies:** Unit 1 (the classifier produces the text; this unit adjusts how it's framed)

**Files:**
- Modify: `src/generate_email.py`
- Test: `tests/test_email.py`

**Approach:**
- Soften section headers:
  - "Today's Briefing" → something warmer like "Here's what I found for you today" or "What caught my attention today"
  - "Help me implement this" → "Let me walk you through this" or "Here's how to try this"
  - "Help me learn this" → "Let me explain this" or "Here's what you need to know"
- Adjust the filter transparency line to feel conversational while preserving the factual content (e.g., "I looked through X items today. Y were worth your time, Z were noted for the record, and I dropped W.")
- Warm up the quiet-day message (currently: "Quiet day — nothing worth your time today. All systems running. The filter is working.") to something that feels more like a mentor check-in
- Consider adding a brief 1-sentence conversational intro before the items section
- Keep the CTA button text and footer factual — those don't need tone changes
- Preserve all inline CSS patterns and email-client-compatible table layout

**Patterns to follow:**
- Existing `_render_*()` composable section pattern in `generate_email.py`
- All text escaped via `html.escape()` before embedding

**Test scenarios:**
- Subject line format unchanged (this is functional, not tone)
- NOTED items still excluded from email
- Leaderboard rendering unchanged
- Backlog summary rendering unchanged
- Valid HTML output
- New section header text appears in rendered output
- Expandable section labels updated
- **Specific tests that will break and need updating:**
  - `test_daily_email_filter_transparency` — asserts `"Reviewed 25 items"` and `"Dropped 18"`. Update assertions to match new conversational wording (e.g., `"I looked through 25 items"` and `"dropped 18"`)
  - `test_daily_email_quiet_day` — asserts `"Quiet day"`. Update to match new warm quiet-day message

**Verification:**
- `python3 -m pytest tests/test_email.py -v` passes
- Visual inspection of `--dry-run` output shows warmer framing around the same data

---

- [x] **Unit 3: Add completion toggles to dashboard Backlog tab**

**Goal:** Add interactive checkboxes to pending backlog items on the dashboard so the user can mark items as completed. State persists via localStorage.

**Requirements:** R4, R5

**Dependencies:** None (independent of tone changes)

**Files:**
- Modify: `src/generate_dashboard.py`
- Test: `tests/test_dashboard.py`

**Approach:**
- In the `renderBacklog()` JS function, add a checkbox element to each pending item
- On toggle, save state to localStorage keyed by item ID (e.g., `backlog_completed_{id}`)
- Checked items get visual treatment: muted opacity or strikethrough, moved to a "Completed" section below pending items
- Add a counter line: "X of Y items completed" — **important: the counter must cross-reference localStorage keys against currently rendered item IDs, not count all localStorage keys.** When the daily pipeline auto-archives an item after 21 days, it disappears from `backlogItems` (status changes from `pending` to `archived`). Orphaned localStorage keys for archived items should be silently ignored, not counted
- On page load, read localStorage and apply saved toggle state. Prune any localStorage keys whose item ID no longer appears in the rendered backlog (garbage collection for archived items)
- Add a "Clear completed" button that removes checked items from localStorage and re-renders
- Update the note at the bottom: keep the CLI instruction for repo sync, but frame it conversationally (e.g., "These toggles save in your browser. To sync back to the repo: `python src/backlog.py --adopt <id>`")
- No changes to the data flow — `backlogItems` JSON blob is still injected at build time. Toggles are a client-side overlay

**Patterns to follow:**
- Existing `renderBacklog()` function structure in `generate_dashboard.py`
- Existing filter state pattern (`activeLayer`, `activeTier`) for managing UI state
- `esc()` helper for HTML escaping

**Test scenarios:**
- Dashboard HTML contains checkbox input elements in the backlog section
- Dashboard HTML contains localStorage read/write JavaScript
- Backlog items render correctly with and without localStorage data
- "Clear completed" button is present
- Counter text is present
- localStorage garbage collection logic is present (pruning keys for items no longer in the rendered list)

**Verification:**
- `python3 -m pytest tests/test_dashboard.py -v` passes
- Visual inspection of generated `docs/index.html` shows toggle checkboxes on backlog items
- Toggles persist after page refresh (manual browser test)

---

- [x] **Unit 4: Update dashboard expandable section labels to match email tone**

**Goal:** Align the dashboard's expandable section labels with the new conversational labels from Unit 2.

**Requirements:** R2 (consistency between email and dashboard)

**Dependencies:** Unit 2 (establishes the new labels)

**Files:**
- Modify: `src/generate_dashboard.py`
- Test: `tests/test_dashboard.py`

**Approach:**
- In the `renderBriefings()` JS function, update the `<summary>` text for expandable sections to match whatever labels Unit 2 establishes (e.g., "Help me implement this" → "Let me walk you through this")
- No other dashboard changes needed for tone — the item text itself already comes from the classifier (changed in Unit 1)

**Patterns to follow:**
- Existing expandable `<details>` pattern in `renderBriefings()`

**Test scenarios:**
- Dashboard HTML output contains the updated expandable labels
- Expandable sections still render correctly

**Verification:**
- `python3 -m pytest tests/test_dashboard.py -v` passes
- `python3 -m src.main --dry-run` regenerates dashboard with updated labels

## System-Wide Impact

- **Interaction graph:** The classifier prompts feed into both the email generator and the dashboard generator. Changing the prompt output style affects both outputs. Unit 4 ensures the dashboard labels stay consistent with the email
- **Error propagation:** No change. Each layer still fails independently. The tone change is in prompt text, not control flow
- **API cost increase:** Conversational output is longer than terse output. Output tokens cost $15/MTok (5x input). Rough estimate: if each item's combined text fields grow from ~100 words to ~150 words across 3 layer calls, monthly output cost increases ~$0.50-1.00. Current budget is $10/month. This is well within limits but should be monitored via `data/spend_log.json` after the first live run. If costs approach the warning threshold (80%), the prompt can be tightened to "warm but concise" without losing the teacher tone
- **State lifecycle risks:** The localStorage toggle state is independent of `data/backlog.json`. When the daily pipeline auto-archives a pending item after 21 days (`_AUTO_ARCHIVE_DAYS` in `backlog.py`), it changes to `archived` status and disappears from `renderBacklog()`'s `pending` filter. The localStorage key for that item becomes orphaned. Mitigation: the toggle rendering logic must cross-reference localStorage against currently rendered IDs, and prune orphaned keys on page load. The "Clear completed" button provides manual cleanup. No risk of data corruption — localStorage is a client-side overlay, not a mutation of source data
- **Historical data tone inconsistency:** Old items stored in `briefings.json` retain their original terse text. The dashboard Briefings tab will show a visible tone shift at the cutover date — terse items before, conversational items after. This is cosmetic and acceptable; retroactively rewriting old data would require re-classifying and is not worth the API cost. It resolves naturally as old entries are pruned at 90 days
- **API surface parity:** The CLI `--adopt` command and the dashboard toggle are parallel paths to the same concept (marking items done). They don't conflict but also don't sync automatically. This is documented in the UI. An item marked "completed" via the dashboard toggle is a visual-only state; the pipeline still considers it `pending` until adopted via CLI or auto-archived at 21 days
- **Integration coverage:** The `--dry-run` pipeline test exercises the full flow including email generation and dashboard rebuild, which will catch regressions in both tone and toggle rendering

## Risks & Dependencies

- **Tone is subjective**: The classifier may need prompt iteration after the first live run. Plan for a review cycle after the first daily email with the new prompts. The `--dry-run` flag allows previewing without sending. Mitigation: run `--dry-run` after implementation and visually review the output before merging
- **Output cost increase**: Longer conversational text means more output tokens at $15/MTok. Estimated ~$0.50-1.00/month increase. Mitigation: prompt should guide toward "warm and direct" not "verbose." Monitor `data/spend_log.json` after first live run. If costs spike, tighten length guidance in prompts without losing conversational tone
- **localStorage limits**: localStorage is device-specific. If the user accesses the dashboard from multiple devices, toggle state won't sync. Acceptable for a single-user personal dashboard
- **localStorage stale state**: Items auto-archived by the pipeline (21 days) disappear from the rendered backlog but leave orphaned localStorage keys. Mitigation: garbage-collect orphaned keys on page load by cross-referencing against rendered item IDs
- **Historical data tone shift**: Items in `briefings.json` from before this change retain their terse text. The dashboard Briefings tab will show a visible tone difference when scrolling through history. This resolves naturally as old data is pruned at 90 days. Not worth retroactive re-classification
- **Test brittleness**: Specific tests that will break: `test_daily_email_filter_transparency` (asserts `"Reviewed 25 items"`, `"Dropped 18"`), `test_daily_email_quiet_day` (asserts `"Quiet day"`). These must be updated in Unit 2 with the new wording. Other email tests check for data content (item titles, tier labels) which won't change

## Sources & References

- Related code: `src/classify.py`, `src/generate_email.py`, `src/generate_dashboard.py`, `config/business_context.md`
- Related tests: `tests/test_email.py`, `tests/test_classify.py`, `tests/test_dashboard.py`
