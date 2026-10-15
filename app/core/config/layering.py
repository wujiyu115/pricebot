"""Configuration layering pure functions.

Two layers exist, mirroring StreamCap's approach:

- default layer: ``config/default_settings.json`` shipped in the repo/image
- user layer: ``config/user_settings.json`` holding only explicitly changed keys

The effective value only ever exists in memory (``deep_merge`` of both layers)
and is never written back wholesale -- writes only persist the sparse user layer.
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge ``override`` into a copy of ``base`` and return it."""
    result: dict[str, Any] = copy.deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def rebuild_effective(target: dict[str, Any], base: dict[str, Any], override: dict[str, Any]) -> None:
    """Rebuild ``target`` in place so objects holding a reference keep seeing
    the fresh merged config (they captured the dict by reference)."""
    merged = deep_merge(base, override)
    target.clear()
    target.update(merged)


def apply_patch(user_overrides: dict[str, Any], patch: dict[str, Any]) -> None:
    """Apply a sparse patch onto the user layer in place."""
    merged = deep_merge(user_overrides, patch)
    user_overrides.clear()
    user_overrides.update(merged)


def unset_path(data: dict[str, Any], path: str) -> bool:
    """Remove a dotted path from ``data``. Returns True when something was removed."""
    keys = path.split(".")
    node: Any = data
    for key in keys[:-1]:
        if not isinstance(node, dict) or key not in node:
            return False
        node = node[key]
    if isinstance(node, dict) and keys[-1] in node:
        del node[keys[-1]]
        return True
    return False


def strip_defaults(user: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``user`` without keys that deep-equal ``defaults``.

    Only used for one-shot migrations of legacy full-dump user files.
    """
    kept: dict[str, Any] = {}
    for key, value in user.items():
        default_value = defaults.get(key)
        if isinstance(value, dict) and isinstance(default_value, dict):
            nested = strip_defaults(value, default_value)
            if nested:
                kept[key] = nested
        elif value != default_value or key not in defaults:
            kept[key] = copy.deepcopy(value)
    return kept


def config_hash(config: dict[str, Any]) -> str:
    """Stable hash used as an optimistic-lock version for settings writes."""
    canonical = json.dumps(config, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


__all__ = [
    "apply_patch",
    "config_hash",
    "deep_merge",
    "rebuild_effective",
    "strip_defaults",
    "unset_path",
]
