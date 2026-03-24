"""Shared state file utilities for JSON persistence."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def load_json_or_default(path: Path, default: dict | list) -> dict | list:
    """Load a JSON file, returning a default if missing or corrupt.

    Args:
        path: Path to the JSON file.
        default: Value to return if the file cannot be read.

    Returns:
        Parsed JSON data or the default value.
    """
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not read %s (%s) — using default", path, exc)
        return default


def save_json(path: Path, data: dict | list) -> None:
    """Write data to a JSON file, creating parent directories as needed.

    Args:
        path: Destination file path.
        data: Data to serialize.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not save %s: %s", path, exc)


def generate_item_id(url: str, title: str) -> str:
    """Generate a deterministic ID for an RSS item.

    Args:
        url: Item source URL.
        title: Item title.

    Returns:
        12-character hex hash string.
    """
    normalized = f"{url.strip().lower()}|{title.strip().lower()}"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]
