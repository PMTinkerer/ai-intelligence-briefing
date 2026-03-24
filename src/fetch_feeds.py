"""RSS/Atom feed fetching, deduplication, and content extraction."""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser
import requests
from bs4 import BeautifulSoup

from src.state import generate_item_id, load_json_or_default

logger = logging.getLogger(__name__)

# Content length caps per spec
_CONTENT_CAP_LAYER_1_2 = 2000
_CONTENT_CAP_LAYER_3 = 500
_SHORT_DESCRIPTION_THRESHOLD = 100
_FULL_PAGE_TIMEOUT = 10
_FULL_PAGE_DELAY = 1.0
_USER_AGENT = "AI-Intelligence-Briefing/1.0 (RSS reader; +https://github.com/pmtinkerer)"


def load_feed_config(path: Path) -> list[dict]:
    """Read feeds.json and return only enabled feeds.

    Args:
        path: Path to the feeds.json config file.

    Returns:
        List of feed dicts with keys: name, url, layer, enabled.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    feeds = data.get("feeds", [])
    enabled = [f for f in feeds if f.get("enabled", True)]
    logger.info("Loaded %d enabled feeds (of %d total)", len(enabled), len(feeds))
    return enabled


def fetch_all_feeds(feeds: list[dict], hours_back: int = 24) -> list[dict]:
    """Fetch and parse all RSS/Atom feeds, returning items from the last N hours.

    Each feed is fetched independently — one failure does not block others.

    Args:
        feeds: List of feed config dicts from load_feed_config().
        hours_back: Only include items published within this many hours.

    Returns:
        List of item dicts with keys: title, url, source_name, layer,
        published, description.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)
    all_items: list[dict] = []
    failed_feeds: list[str] = []

    for feed_cfg in feeds:
        name = feed_cfg["name"]
        url = feed_cfg["url"]
        layer = feed_cfg["layer"]

        try:
            parsed = feedparser.parse(url)
            if parsed.bozo and not parsed.entries:
                logger.warning("Feed '%s' returned no entries (bozo: %s)", name, parsed.bozo_exception)
                failed_feeds.append(name)
                continue

            count = 0
            for entry in parsed.entries:
                pub_date = _parse_entry_date(entry)
                if pub_date and pub_date < cutoff:
                    continue

                item = {
                    "title": entry.get("title", "").strip(),
                    "url": entry.get("link", "").strip(),
                    "source_name": name,
                    "layer": layer,
                    "published": pub_date.isoformat() if pub_date else None,
                    "description": _extract_description(entry),
                }

                if item["title"] and item["url"]:
                    all_items.append(item)
                    count += 1

            logger.info("Feed '%s': %d items within %dh window", name, count, hours_back)

        except Exception:
            logger.warning("Failed to fetch feed '%s' (%s)", name, url, exc_info=True)
            failed_feeds.append(name)

    logger.info("Fetched %d total items from %d feeds (%d failed: %s)",
                len(all_items), len(feeds), len(failed_feeds),
                ", ".join(failed_feeds) if failed_feeds else "none")

    return all_items


def extract_content(items: list[dict]) -> list[dict]:
    """Enrich items with full content when RSS description is too short.

    For items with descriptions under 100 characters, fetches the linked page
    and extracts article text. Caps content at 2000 chars (Layer 1/2) or
    500 chars (Layer 3).

    Args:
        items: List of item dicts from fetch_all_feeds().

    Returns:
        Same items list with 'content' field added to each.
    """
    fetched_count = 0
    for item in items:
        desc = item.get("description", "")
        cap = _CONTENT_CAP_LAYER_3 if item.get("layer") == 3 else _CONTENT_CAP_LAYER_1_2

        if len(desc) >= _SHORT_DESCRIPTION_THRESHOLD:
            item["content"] = desc[:cap]
            continue

        # Short description — try fetching full page
        url = item.get("url", "")
        if not url:
            item["content"] = desc[:cap]
            continue

        try:
            if fetched_count > 0:
                time.sleep(_FULL_PAGE_DELAY)

            resp = requests.get(url, timeout=_FULL_PAGE_TIMEOUT,
                                headers={"User-Agent": _USER_AGENT})
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "lxml")
            # Try semantic containers first, then fall back to body
            article = soup.find("article") or soup.find("main") or soup.find("body")
            text = article.get_text(separator=" ", strip=True) if article else ""
            item["content"] = text[:cap] if text else desc[:cap]
            fetched_count += 1
            logger.debug("Fetched full page for '%s' (%d chars)", item.get("title", "?"), len(item["content"]))

        except Exception:
            logger.debug("Could not fetch full page for '%s' — using RSS description", item.get("title", "?"))
            item["content"] = desc[:cap]

    if fetched_count:
        logger.info("Fetched %d full pages for short descriptions", fetched_count)

    return items


def deduplicate(
    items: list[dict],
    seen_path: Path,
) -> tuple[list[dict], dict]:
    """Filter out previously seen items and handle cross-layer dedup.

    Args:
        items: List of item dicts from fetch_all_feeds().
        seen_path: Path to seen_items.json.

    Returns:
        Tuple of (new_items, updated_seen_dict) where updated_seen_dict
        includes the newly seen items and has entries >90 days pruned.
    """
    seen_data = load_json_or_default(seen_path, {"items": {}, "last_run": None})
    seen_items = seen_data.get("items", {})

    # Prune entries older than 90 days
    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=90)).strftime("%Y-%m-%d")
    seen_items = {
        k: v for k, v in seen_items.items()
        if isinstance(v, dict) and v.get("first_seen", "9999") >= cutoff_date
    }

    # Cross-layer dedup: if same URL in Layer 2 and Layer 3, keep Layer 2
    url_to_items: dict[str, list[dict]] = {}
    for item in items:
        url_to_items.setdefault(item["url"], []).append(item)

    deduped_items: list[dict] = []
    for url, url_items in url_to_items.items():
        if len(url_items) > 1:
            # Keep the item from the lowest layer number (highest priority)
            best = min(url_items, key=lambda x: x["layer"])
            deduped_items.append(best)
        else:
            deduped_items.append(url_items[0])

    # Filter against seen items
    new_items: list[dict] = []
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    for item in deduped_items:
        item_id = generate_item_id(item["url"], item["title"])
        item["id"] = item_id

        if item_id in seen_items:
            continue

        new_items.append(item)
        seen_items[item_id] = {
            "title": item["title"],
            "first_seen": today,
            "source_name": item["source_name"],
            "layer": item["layer"],
        }

    updated_seen = {
        "items": seen_items,
        "last_run": datetime.now(timezone.utc).isoformat(),
    }

    logger.info("Dedup: %d input → %d new (filtered %d seen, %d cross-layer dupes)",
                len(items), len(new_items),
                len(items) - len(deduped_items) + len(deduped_items) - len(new_items),
                len(items) - len(deduped_items))

    return new_items, updated_seen


def _parse_entry_date(entry: dict) -> datetime | None:
    """Extract a timezone-aware datetime from a feedparser entry.

    Args:
        entry: A feedparser entry dict.

    Returns:
        Timezone-aware datetime, or None if no date found.
    """
    for field in ("published_parsed", "updated_parsed"):
        parsed = entry.get(field)
        if parsed:
            try:
                dt = datetime(*parsed[:6], tzinfo=timezone.utc)
                return dt
            except (TypeError, ValueError):
                continue
    return None


def _extract_description(entry: dict) -> str:
    """Extract the best available text description from a feedparser entry.

    Args:
        entry: A feedparser entry dict.

    Returns:
        Plain text description, stripped of HTML tags.
    """
    # Prefer summary, then content
    raw = entry.get("summary", "")
    if not raw and entry.get("content"):
        raw = entry["content"][0].get("value", "")

    if not raw:
        return ""

    # Strip HTML tags
    soup = BeautifulSoup(raw, "lxml")
    text = soup.get_text(separator=" ", strip=True)
    return text
