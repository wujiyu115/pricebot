"""ConfigManager: two-layer settings with sparse user overrides."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from ...utils.logger import logger
from .layering import (
    apply_patch,
    config_hash,
    deep_merge,
    rebuild_effective,
    unset_path,
)


class ConfigManager:
    """Loads default + sparse user settings, keeps the effective config in memory.

    Business code reads ``user_config`` (the merged dict). Objects that capture
    ``user_config`` by reference keep working after :meth:`apply_user_patch`
    because the dict is rebuilt in place.
    """

    def __init__(self, config_dir: str | Path) -> None:
        self.config_dir = Path(config_dir)
        self.default_path = self.config_dir / "default_settings.json"
        self.user_path = self.config_dir / "user_settings.json"
        self._lock = threading.RLock()

        self.default_config: dict[str, Any] = self._load_json(self.default_path, fallback={})
        self.user_overrides: dict[str, Any] = self._load_json(self.user_path, fallback={})
        self.user_config: dict[str, Any] = deep_merge(self.default_config, self.user_overrides)

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _load_json(path: Path, fallback: dict[str, Any]) -> dict[str, Any]:
        try:
            if path.is_file():
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            return fallback
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(f"Failed to load config {path}: {exc}; using fallback")
            return fallback

    def save_user_config(self) -> None:
        with self._lock:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            tmp = self.user_path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(self.user_overrides, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp.replace(self.user_path)

    # ------------------------------------------------------------------ public
    @property
    def version(self) -> str:
        with self._lock:
            return config_hash(self.user_overrides)

    def apply_user_patch(self, patch: dict[str, Any]) -> None:
        """Apply a sparse patch (only keys the user really changed) and persist."""
        with self._lock:
            apply_patch(self.user_overrides, patch)
            rebuild_effective(self.user_config, self.default_config, self.user_overrides)
            self.save_user_config()
            logger.info(f"Settings patch applied, {len(patch)} top-level key(s)")

    def unset_user_key(self, path: str) -> bool:
        with self._lock:
            removed = unset_path(self.user_overrides, path)
            if removed:
                rebuild_effective(self.user_config, self.default_config, self.user_overrides)
                self.save_user_config()
                logger.info(f"Settings key {path!r} removed from user layer")
            return removed


__all__ = ["ConfigManager"]
