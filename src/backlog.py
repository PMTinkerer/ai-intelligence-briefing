"""Adoption backlog management — track, auto-archive, and report on actionable items."""

from __future__ import annotations

import argparse
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.state import generate_item_id, load_json_or_default, save_json

logger = logging.getLogger(__name__)

_AUTO_ARCHIVE_DAYS = 21
_ADOPTION_RATE_WINDOW_DAYS = 28


def update_backlog(
    classified_items: list[dict],
    backlog_path: Path,
) -> dict:
    """Add new actionable items and auto-archive stale ones.

    GAME_CHANGER and WORTH_YOUR_TIME items with a non-empty expandable_implement
    are added as pending. Items pending for 21+ days are auto-archived.

    Args:
        classified_items: Today's classified items (all tiers).
        backlog_path: Path to backlog.json.

    Returns:
        Summary dict with keys: total_pending, total_adopted, total_archived,
        adoption_rate_4w, new_this_run, archived_this_run, oldest_pending.
    """
    data = load_json_or_default(backlog_path, {"items": [], "stats": {}})
    items = data.get("items", [])
    existing_ids = {i["id"] for i in items}
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Add new actionable items
    new_count = 0
    for ci in classified_items:
        if ci.get("tier") not in ("GAME_CHANGER", "WORTH_YOUR_TIME"):
            continue
        if not ci.get("expandable_implement"):
            continue

        item_id = ci.get("id", generate_item_id(ci.get("url", ""), ci.get("title", "")))
        if item_id in existing_ids:
            continue

        items.append({
            "id": item_id,
            "title": ci.get("title", ""),
            "source_url": ci.get("url", ""),
            "tier": ci["tier"],
            "layer": ci.get("layer", 0),
            "expandable_implement": ci.get("expandable_implement", ""),
            "status": "pending",
            "date_added": today,
            "date_adopted": None,
            "date_archived": None,
        })
        existing_ids.add(item_id)
        new_count += 1

    # Auto-archive items pending 21+ days
    archive_cutoff = (datetime.now(timezone.utc) - timedelta(days=_AUTO_ARCHIVE_DAYS)).strftime("%Y-%m-%d")
    archived_count = 0
    for item in items:
        if item["status"] == "pending" and item.get("date_added", "9999") <= archive_cutoff:
            item["status"] = "archived"
            item["date_archived"] = today
            archived_count += 1

    # Calculate days_pending for each pending item
    for item in items:
        if item["status"] == "pending":
            added = datetime.strptime(item["date_added"], "%Y-%m-%d")
            item["days_pending"] = (datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0) - added.replace(tzinfo=timezone.utc)).days
        else:
            item["days_pending"] = 0

    # Compute stats
    summary = _compute_stats(items)
    summary["new_this_run"] = new_count
    summary["archived_this_run"] = archived_count

    # Find oldest pending
    pending = [i for i in items if i["status"] == "pending"]
    if pending:
        oldest = sorted(pending, key=lambda x: x["date_added"])[:3]
        summary["oldest_pending"] = [
            {"title": i["title"], "days_pending": i["days_pending"]}
            for i in oldest
        ]
    else:
        summary["oldest_pending"] = []

    data["items"] = items
    data["stats"] = {
        "total_added": len(items),
        "total_adopted": sum(1 for i in items if i["status"] == "adopted"),
        "total_archived": sum(1 for i in items if i["status"] == "archived"),
        "adoption_rate_4w": summary["adoption_rate_4w"],
    }

    save_json(backlog_path, data)
    logger.info("Backlog updated: +%d new, %d archived, %d pending",
                new_count, archived_count, summary["total_pending"])

    return summary


def mark_adopted(item_id: str, backlog_path: Path) -> bool:
    """Mark a backlog item as adopted.

    Args:
        item_id: The item's ID hash.
        backlog_path: Path to backlog.json.

    Returns:
        True if item was found and updated, False otherwise.
    """
    data = load_json_or_default(backlog_path, {"items": [], "stats": {}})
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    for item in data.get("items", []):
        if item["id"] == item_id:
            item["status"] = "adopted"
            item["date_adopted"] = today
            save_json(backlog_path, data)
            logger.info("Marked item '%s' as adopted", item.get("title", item_id))
            return True

    logger.warning("Item '%s' not found in backlog", item_id)
    return False


def get_backlog_stats(backlog_path: Path) -> dict:
    """Compute backlog stats without modifying the file.

    Args:
        backlog_path: Path to backlog.json.

    Returns:
        Stats dict.
    """
    data = load_json_or_default(backlog_path, {"items": [], "stats": {}})
    return _compute_stats(data.get("items", []))


def _compute_stats(items: list[dict]) -> dict:
    """Compute summary statistics from backlog items.

    Args:
        items: List of backlog item dicts.

    Returns:
        Dict with total_pending, total_adopted, total_archived, adoption_rate_4w.
    """
    total_pending = sum(1 for i in items if i["status"] == "pending")
    total_adopted = sum(1 for i in items if i["status"] == "adopted")
    total_archived = sum(1 for i in items if i["status"] == "archived")

    # 4-week adoption rate: adopted / (adopted + archived) for items resolved in last 28 days
    cutoff = (datetime.now(timezone.utc) - timedelta(days=_ADOPTION_RATE_WINDOW_DAYS)).strftime("%Y-%m-%d")
    recent_adopted = sum(
        1 for i in items
        if i["status"] == "adopted" and (i.get("date_adopted") or "0000") >= cutoff
    )
    recent_archived = sum(
        1 for i in items
        if i["status"] == "archived" and (i.get("date_archived") or "0000") >= cutoff
    )
    resolved = recent_adopted + recent_archived
    adoption_rate = round(recent_adopted / resolved, 2) if resolved > 0 else 0.0

    return {
        "total_pending": total_pending,
        "total_adopted": total_adopted,
        "total_archived": total_archived,
        "adoption_rate_4w": adoption_rate,
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(description="Manage adoption backlog")
    parser.add_argument("--adopt", metavar="ID", help="Mark an item as adopted by its ID")
    parser.add_argument("--list", action="store_true", help="List pending items")
    parser.add_argument("--path", default="data/backlog.json", help="Path to backlog.json")
    args = parser.parse_args()

    backlog_path = Path(args.path)

    if args.adopt:
        ok = mark_adopted(args.adopt, backlog_path)
        if ok:
            print(f"Marked {args.adopt} as adopted.")
        else:
            print(f"Item {args.adopt} not found.")

    elif args.list:
        data = load_json_or_default(backlog_path, {"items": []})
        pending = [i for i in data.get("items", []) if i["status"] == "pending"]
        if not pending:
            print("No pending items.")
        else:
            for item in sorted(pending, key=lambda x: x.get("date_added", "")):
                days = item.get("days_pending", "?")
                print(f"  [{item['id']}] {item['title']} ({days}d pending, {item['tier']})")

    else:
        stats = get_backlog_stats(backlog_path)
        print(f"Pending: {stats['total_pending']}, Adopted: {stats['total_adopted']}, "
              f"Archived: {stats['total_archived']}, 4w rate: {stats['adoption_rate_4w']:.0%}")
