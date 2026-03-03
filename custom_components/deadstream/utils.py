"""Utility helpers for Deadstream."""
from __future__ import annotations

import json
from typing import Any

from .const import AVAILABLE_COLLECTIONS, COLLECTION_LABELS, DEFAULT_COLLECTIONS


def normalize_collections(value: Any) -> list[str]:
    """Normalize collection config into canonical known collection IDs."""
    known_by_lower = {c.lower(): c for c in AVAILABLE_COLLECTIONS}
    label_by_lower = {label.lower(): cid for cid, label in COLLECTION_LABELS.items()}

    if isinstance(value, dict):
        candidates = [str(k).strip() for k, enabled in value.items() if enabled]
    elif isinstance(value, str):
        raw = value.strip()
        if raw.startswith("[") and raw.endswith("]"):
            try:
                decoded = json.loads(raw)
            except json.JSONDecodeError:
                decoded = None
            if isinstance(decoded, list):
                candidates = [str(v).strip() for v in decoded]
            else:
                candidates = [p.strip() for p in raw.strip("[]").split(",") if p.strip()]
        else:
            candidates = [p.strip() for p in raw.split(",") if p.strip()]
    elif isinstance(value, (list, tuple, set)):
        candidates = [str(v).strip() for v in value if str(v).strip()]
    else:
        candidates = []

    normalized: list[str] = []
    for item in candidates:
        key = item.strip("\"'").lower()
        canonical = known_by_lower.get(key) or label_by_lower.get(key)
        if canonical and canonical not in normalized:
            normalized.append(canonical)

    return normalized or [*DEFAULT_COLLECTIONS]
