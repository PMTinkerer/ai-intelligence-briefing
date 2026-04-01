"""AI classification of RSS items across three layers plus leaderboard generation."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import anthropic

from src.config import SPENDING_BUDGET_USD, SPENDING_LOG_PATH, SPENDING_WARN_THRESHOLD
from src.spending_guard import can_spend, load_ledger, record_spend, save_ledger

logger = logging.getLogger(__name__)

_MODEL = "claude-sonnet-4-6"

# ---------------------------------------------------------------------------
# Layer classification
# ---------------------------------------------------------------------------

_TIER_DEFINITIONS = """\
Classify each item into exactly one tier:

GAME_CHANGER — Shifts the landscape. Changes what's possible, changes strategy, opens a door that was previously closed. Rare — maybe 1-3 per week, some weeks zero.

WORTH_YOUR_TIME — Makes you measurably better or faster at something. Not transformative, but genuinely useful. Would you set aside 20 minutes to try it?

NOTED — Passed the filter but isn't urgent. Stored in the archive. Does NOT appear in the daily email unless fewer than 3 items across Tiers 1 and 2.

DROPPED — Does not belong in the briefing. Bug fixes for unused features, enterprise-only features, platform-specific patches, UI tweaks, incremental docs updates. Most items should be DROPPED.

A typical daily briefing should contain 3-7 items total across ALL layers. Be aggressive about dropping items. The value of this tool is what it EXCLUDES.
"""

_LAYER_1_PROMPT = """\
You are classifying Anthropic product updates for an operator. Here is the full business context:

{business_context}

{tier_definitions}

{blocked_projects_section}

VOICE & TONE: Write as if you're a knowledgeable, endlessly patient teacher who genuinely wants this person to understand and succeed. You're sitting next to them, walking them through what just happened and why they should care. Never lecture. Never use jargon without explaining it. Be warm, direct, and practical. Keep it concise — warm doesn't mean wordy.

For each item, return a JSON object. Items classified as DROPPED should still be included in the response with tier "DROPPED" so we can count them.

For items that are NOT dropped, provide:
- "what_it_is": In 2-3 sentences, explain what this development is as if you're telling a smart friend what just happened. Plain language, no marketing speak.
- "why_it_matters": In 3-4 sentences, connect this to the operator's specific situation. Explain the implication like a mentor pointing out why they should pay attention — what changes for them, what becomes possible, what they should think about differently.
- "expandable_implement": Walk them through it step by step, like a patient teacher sitting next to them. Include the actual commands, config snippets, or code they need, but wrap each step in a brief explanation of what it does and why. If not applicable, null.
- "expandable_learn": Explain the underlying concept like you're building their understanding from the ground up. Start with what they already know, connect to the new idea, and suggest a small experiment they can try to make it click. If not applicable, null.
- "unblocks_project": which blocked project and why, or null

Respond with ONLY valid JSON matching this schema:
{{
  "items": [
    {{
      "id": "<item id>",
      "tier": "GAME_CHANGER" | "WORTH_YOUR_TIME" | "NOTED" | "DROPPED",
      "what_it_is": "...",
      "why_it_matters": "...",
      "expandable_implement": "..." or null,
      "expandable_learn": "..." or null,
      "unblocks_project": "..." or null
    }}
  ]
}}
"""

_LAYER_2_PROMPT = """\
You are classifying practitioner insights and blog posts for an ambitious business operator who uses AI as a force multiplier. He builds with Claude Code, runs GitHub Actions pipelines, and manages a short-term rental portfolio.

Current tools: Claude Code (VS Code), Claude.ai, Anthropic API, GitHub Actions, Gmail API, Python 3.9+
Current projects: STR Daily Briefing (production), Inspector Scheduling System (production), AI Intelligence Briefing (this tool), Cleaning Cost Calculator
Stage 4 gaps: debugging tracebacks, MCP integrations, Claude Code Skills, multi-system orchestration, autonomous agent loops

{blocked_projects_section}

{tier_definitions}

VOICE & TONE: Write as if you're a knowledgeable, endlessly patient teacher who genuinely wants this person to understand and succeed. You're sitting next to them, walking them through what someone wrote and why it matters for their work. Never lecture. Never use jargon without explaining it. Be warm, direct, and practical. Keep it concise — warm doesn't mean wordy.

For practitioner posts that are just commentary or hot takes without actionable substance, classify as DROPPED.

For items that are NOT dropped, provide:
- "what_it_is": In 2-3 sentences, explain what this post or insight is about as if you're telling a smart friend what you just read.
- "why_it_matters": In 3-4 sentences, connect this to the operator's specific work. Explain how this technique, pattern, or insight could change the way they approach something they're already doing.
- "expandable_implement": For items that demonstrate a technique, walk them through how to apply it — step by step, like a patient teacher. Include concrete commands or code, but explain each step so they understand what's happening, not just what to type. If not applicable, null.
- "expandable_learn": For items that explain a concept or paradigm, teach the key mental model in a way that builds on what they already know. Suggest a small experiment they can try to make the idea real. If not applicable, null.
- "unblocks_project": which blocked project and why, or null

Respond with ONLY valid JSON matching this schema:
{{
  "items": [
    {{
      "id": "<item id>",
      "tier": "GAME_CHANGER" | "WORTH_YOUR_TIME" | "NOTED" | "DROPPED",
      "what_it_is": "...",
      "why_it_matters": "...",
      "expandable_implement": "..." or null,
      "expandable_learn": "..." or null,
      "unblocks_project": "..." or null
    }}
  ]
}}
"""

_LAYER_3_PROMPT = """\
You are classifying AI industry news for an ambitious 30-year-old business operator who uses AI as a force multiplier to build operational automation and transferable problem-solving skills. He is NOT trying to become an AI expert — he is building AI fluency so he can attack any problem in any industry.

VOICE & TONE: Write as if you're a knowledgeable friend catching them up on what happened in the industry today. Be conversational and direct — explain what happened and why it matters to someone building real things with AI. No hype, no jargon without context.

Select the top 10 most relevant items, ranked. "Relevant" means relevant to someone building deep operational capabilities with AI. Drop everything else.

Foundation model releases from major labs are always relevant. Hardware breakthroughs relevant if they change economics for small operators. Applied case studies showing AI transforming operations in any industry are relevant. Funding announcements usually aren't relevant. Policy/regulation only if it affects tool usage. Pure hype gets dropped.

Respond with ONLY valid JSON:
{{
  "items": [
    {{
      "id": "<item id>",
      "tier": "GAME_CHANGER" | "WORTH_YOUR_TIME" | "NOTED" | "DROPPED",
      "summary": "2-3 sentence conversational summary explaining what happened and why it matters to someone building with AI",
      "rank": 1
    }}
  ]
}}
"""

_LEADERBOARD_PROMPT = """\
You are maintaining a Top 5 Impact Leaderboard for an ambitious 30-year-old business operator. He is NOT trying to become an AI developer or build an AI product. He is building AI fluency the way an elite leader builds communication skills — not to become a writer, but to be able to walk into any room, any industry, any problem, and operate at a level others can't match. AI is his force multiplier. His current business (short-term rental management) is today's training ground. His horizon is 10 years.

Rank the 5 highest-leverage capabilities, tools, techniques, patterns, or actions he could invest time in RIGHT NOW. "Highest leverage" means: what would create the most compounding value over 12+ months, considering BOTH immediate business execution AND long-term capability building as an operator and problem-solver?

The leaderboard should NOT be a list of AI features to learn. It should be a list of things that make him more formidable — period.

Rules:
- The list should be STABLE. Don't churn items on and off daily. A new release should only displace an existing item if it's genuinely more impactful, not just newer.
- Mix of time horizons: some "try this in 20 minutes today" and some "invest 2-3 sessions into understanding this paradigm."
- DO NOT over-weight items just because they connect to a named project. A transformative capability that doesn't connect to any existing project can outrank an incremental improvement to a named one.
- DO NOT let the blocked projects list dominate the ranking.
- DO NOT make this a list of AI tools to learn. Include applied patterns, cross-industry case studies, and capability-building investments.
- Consider what the operator's competitors are NOT doing. Edge-building capabilities rank higher than consensus ones.
- Each item needs a clear, honest rationale with a specific mechanism by which it compounds.
- Max 2 items can change per day unless something truly landscape-shifting happens.

{business_context}

Today's classified items (Tiers 1 and 2 only):
{todays_items}

Current backlog (pending items):
{backlog_summary}

Previous day's leaderboard:
{previous_leaderboard}

Blocked projects:
{blocked_projects}

Respond with ONLY valid JSON:
{{
  "leaderboard": [
    {{
      "rank": 1,
      "title": "Short specific title",
      "category": "NEW_CAPABILITY" | "SKILL_GAP" | "BLOCKED_PROJECT" | "STRATEGIC_MOVE" | "PARADIGM_SHIFT" | "APPLIED_PATTERN",
      "rationale": "2-3 sentences, specific and honest",
      "first_step": "One concrete action with time estimate",
      "time_investment": "e.g. 20 minutes, 2-3 sessions, ongoing practice",
      "days_on_leaderboard": <integer>
    }}
  ],
  "changes_today": ["Description of what entered/exited and why"]
}}
"""


def classify_layer(
    items: list[dict],
    layer: int,
    business_context: str,
    blocked_projects: list[dict],
    api_key: str,
) -> dict:
    """Classify items for a single layer via one API call.

    Args:
        items: List of item dicts for this layer.
        layer: Layer number (1, 2, or 3).
        business_context: Full business context markdown.
        blocked_projects: List of blocked project dicts.
        api_key: Anthropic API key.

    Returns:
        Dict with "items" (classified) and "dropped_count".
    """
    if not items:
        return {"items": [], "dropped_count": 0}

    # Build blocked projects section
    bp_lines = []
    for bp in blocked_projects:
        bp_lines.append(f"- {bp['project']}: {bp['blocker']}")
        for cond in bp.get("unblock_conditions", []):
            bp_lines.append(f"  - Unblocks if: {cond}")
    blocked_section = "Blocked projects (check releases against these):\n" + "\n".join(bp_lines) if bp_lines else ""

    # Select prompt template
    if layer == 1:
        system = _LAYER_1_PROMPT.format(
            business_context=business_context,
            tier_definitions=_TIER_DEFINITIONS,
            blocked_projects_section=blocked_section,
        )
    elif layer == 2:
        system = _LAYER_2_PROMPT.format(
            tier_definitions=_TIER_DEFINITIONS,
            blocked_projects_section=blocked_section,
        )
    else:
        system = _LAYER_3_PROMPT

    # Build user message with items
    items_for_prompt = []
    for item in items:
        items_for_prompt.append({
            "id": item.get("id", ""),
            "title": item.get("title", ""),
            "source_name": item.get("source_name", ""),
            "content": item.get("content", item.get("description", "")),
            "url": item.get("url", ""),
        })

    user_msg = f"Classify these {len(items_for_prompt)} items:\n\n{json.dumps(items_for_prompt, indent=2)}"

    # Spending guard
    ledger = load_ledger(Path(SPENDING_LOG_PATH))
    if not can_spend(ledger, SPENDING_BUDGET_USD, estimated_cost=0.10,
                     warn_threshold=SPENDING_WARN_THRESHOLD):
        logger.warning("Budget exceeded — skipping Layer %d classification", layer)
        return {"items": [], "dropped_count": len(items)}

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=_MODEL,
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": user_msg}],
        )

        usage = response.usage
        cost = record_spend(ledger, "anthropic", _MODEL,
                            usage.input_tokens, usage.output_tokens,
                            f"classify_layer_{layer}")
        save_ledger(ledger, Path(SPENDING_LOG_PATH))
        logger.info("Layer %d classification: $%.4f (in=%d, out=%d)",
                     layer, cost, usage.input_tokens, usage.output_tokens)

        # Parse response — handle potential markdown code fences
        raw_text = response.content[0].text.strip()
        if raw_text.startswith("```"):
            raw_text = raw_text.split("\n", 1)[1] if "\n" in raw_text else raw_text
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3].strip()

        result = json.loads(raw_text)
        classified = result.get("items", [])

        # Merge classification back into original items
        class_map = {c["id"]: c for c in classified if "id" in c}
        output_items = []
        dropped_count = 0

        for item in items:
            item_id = item.get("id", "")
            classification = class_map.get(item_id, {})
            tier = classification.get("tier", "DROPPED")

            if tier == "DROPPED":
                dropped_count += 1
                continue

            merged = {**item, **classification}
            merged["tier"] = tier
            merged["layer"] = layer
            output_items.append(merged)

        # Count items not in class_map as dropped
        dropped_count += len(items) - len(class_map)
        # Avoid double-counting
        dropped_count = min(dropped_count, len(items) - len(output_items))

        logger.info("Layer %d: %d items → %d classified, %d dropped",
                     layer, len(items), len(output_items), dropped_count)

        return {"items": output_items, "dropped_count": dropped_count}

    except Exception:
        logger.warning("Layer %d classification failed", layer, exc_info=True)
        return {"items": [], "dropped_count": len(items)}


def classify_all(
    items: list[dict],
    business_context: str,
    blocked_projects: list[dict],
    api_key: str,
) -> tuple[list[dict], dict]:
    """Classify items across all three layers independently.

    Args:
        items: All fetched items with 'layer' field.
        business_context: Full business context markdown.
        blocked_projects: List of blocked project dicts.
        api_key: Anthropic API key.

    Returns:
        Tuple of (all_classified_items, dropped_counts_by_layer).
    """
    # Group by layer
    by_layer: dict[int, list[dict]] = {1: [], 2: [], 3: []}
    for item in items:
        layer = item.get("layer", 3)
        by_layer.setdefault(layer, []).append(item)

    all_classified: list[dict] = []
    dropped_counts: dict[str, int] = {}

    for layer in (1, 2, 3):
        layer_items = by_layer.get(layer, [])
        if not layer_items:
            dropped_counts[f"layer_{layer}"] = 0
            continue

        result = classify_layer(layer_items, layer, business_context, blocked_projects, api_key)
        all_classified.extend(result["items"])
        dropped_counts[f"layer_{layer}"] = result["dropped_count"]

    logger.info("Classification complete: %d items surfaced, dropped: %s",
                len(all_classified), dropped_counts)

    return all_classified, dropped_counts


# ---------------------------------------------------------------------------
# Leaderboard generation
# ---------------------------------------------------------------------------

def generate_leaderboard(
    classified_items: list[dict],
    previous_leaderboard: dict,
    backlog_items: list[dict],
    business_context: str,
    blocked_projects: list[dict],
    api_key: str,
) -> dict:
    """Generate the Top 5 Impact Leaderboard via API call.

    Args:
        classified_items: Today's Tier 1 and 2 items.
        previous_leaderboard: Previous day's leaderboard data.
        backlog_items: Current pending backlog items.
        business_context: Full business context markdown.
        blocked_projects: Blocked project dicts.
        api_key: Anthropic API key.

    Returns:
        Leaderboard dict with "leaderboard" and "changes_today" keys.
        On failure, returns previous leaderboard with incremented days.
    """
    # Filter to Tier 1 and 2 only
    top_items = [
        {"title": i.get("title"), "tier": i.get("tier"), "what_it_is": i.get("what_it_is", "")}
        for i in classified_items
        if i.get("tier") in ("GAME_CHANGER", "WORTH_YOUR_TIME")
    ]

    prev_entries = previous_leaderboard.get("leaderboard", [])
    backlog_summary = [
        {"title": b.get("title"), "status": b.get("status"), "days_pending": b.get("days_pending", 0)}
        for b in backlog_items
        if b.get("status") == "pending"
    ][:10]

    bp_text = json.dumps(blocked_projects, indent=2) if blocked_projects else "None"

    system = _LEADERBOARD_PROMPT.format(
        business_context=business_context,
        todays_items=json.dumps(top_items, indent=2) if top_items else "No new items today.",
        backlog_summary=json.dumps(backlog_summary, indent=2) if backlog_summary else "Backlog empty.",
        previous_leaderboard=json.dumps(prev_entries, indent=2) if prev_entries else "No previous leaderboard (first run).",
        blocked_projects=bp_text,
    )

    # Spending guard
    ledger = load_ledger(Path(SPENDING_LOG_PATH))
    if not can_spend(ledger, SPENDING_BUDGET_USD, estimated_cost=0.08,
                     warn_threshold=SPENDING_WARN_THRESHOLD):
        logger.warning("Budget exceeded — using previous leaderboard")
        return _fallback_leaderboard(previous_leaderboard)

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=_MODEL,
            max_tokens=2048,
            system=system,
            messages=[{"role": "user", "content": "Generate today's Top 5 Impact Leaderboard."}],
        )

        usage = response.usage
        cost = record_spend(ledger, "anthropic", _MODEL,
                            usage.input_tokens, usage.output_tokens,
                            "leaderboard")
        save_ledger(ledger, Path(SPENDING_LOG_PATH))
        logger.info("Leaderboard generation: $%.4f (in=%d, out=%d)",
                     cost, usage.input_tokens, usage.output_tokens)

        raw_text = response.content[0].text.strip()
        if raw_text.startswith("```"):
            raw_text = raw_text.split("\n", 1)[1] if "\n" in raw_text else raw_text
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3].strip()

        result = json.loads(raw_text)
        return {
            "leaderboard": result.get("leaderboard", []),
            "changes_today": result.get("changes_today", []),
        }

    except Exception:
        logger.warning("Leaderboard generation failed — using previous", exc_info=True)
        return _fallback_leaderboard(previous_leaderboard)


def _fallback_leaderboard(previous: dict) -> dict:
    """Return previous leaderboard with incremented days_on_leaderboard.

    Args:
        previous: Previous leaderboard dict.

    Returns:
        Updated leaderboard dict.
    """
    entries = previous.get("leaderboard", [])
    for entry in entries:
        entry["days_on_leaderboard"] = entry.get("days_on_leaderboard", 0) + 1
    return {
        "leaderboard": entries,
        "changes_today": ["Leaderboard unchanged (generation failed)"],
    }
