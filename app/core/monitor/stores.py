"""标的与规则的 JSON 持久化存储（线程安全 CRUD，支持热更新）。

引擎每轮 tick 都重新读取 ``list()``，所以 API 侧的增删改立即生效，
无需重启或通知。文件写入走 tmp+rename 原子替换。
"""

from __future__ import annotations

import json
import threading
import uuid
from pathlib import Path
from typing import Any, ClassVar

from ...utils.logger import logger
from .rules import Rule


def new_id() -> str:
    return uuid.uuid4().hex[:8]


class _JsonStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.RLock()
        self._data: list[dict[str, Any]] = self._load()

    def _load(self) -> list[dict[str, Any]]:
        try:
            if self.path.is_file():
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return data
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(f"failed to load {self.path}: {exc}")
        return []

    def _save(self) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.path)

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(item) for item in self._data]

    def get(self, item_id: str) -> dict[str, Any] | None:
        with self._lock:
            for item in self._data:
                if item.get("id") == item_id:
                    return dict(item)
        return None

    def add(self, item: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            if not item.get("id"):
                item["id"] = new_id()
            self._data.append(item)
            self._save()
            return dict(item)

    def update(self, item_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        with self._lock:
            for idx, item in enumerate(self._data):
                if item.get("id") == item_id:
                    merged = {**item, **patch, "id": item_id}
                    self._data[idx] = merged
                    self._save()
                    return dict(merged)
        return None

    def remove(self, item_id: str) -> bool:
        with self._lock:
            before = len(self._data)
            self._data = [i for i in self._data if i.get("id") != item_id]
            removed = len(self._data) < before
            if removed:
                self._save()
        return removed


class TargetStore(_JsonStore):
    """监控标的: id/name/source/symbol/enabled/interval_seconds/schedule/extra."""

    DEFAULT_TARGETS: ClassVar[list[dict[str, Any]]] = [
        {
            "name": "上金所黄金9999",
            "source": "sina",
            "symbol": "SGE_AU9999",
            "enabled": True,
            "schedule": "sge",
        },
        {
            "name": "上金所黄金T+D",
            "source": "sina",
            "symbol": "SGE_AUTD",
            "enabled": True,
            "schedule": "sge",
        },
        {
            "name": "上证指数",
            "source": "sina_stock",
            "symbol": "sh000001",
            "enabled": True,
            "schedule": "cn_stock",
        },
    ]

    def __init__(self, path: Path) -> None:
        super().__init__(path)
        if not self._data:
            for target in self.DEFAULT_TARGETS:
                self.add(dict(target))

    def list_enabled(self) -> list[dict[str, Any]]:
        return [t for t in self.list() if t.get("enabled", True)]


class RuleStore(_JsonStore):
    """告警规则（结构见 monitor/rules.py 的 Rule）。"""

    def list_rules(self) -> list[Rule]:
        return [Rule.from_dict(item) for item in self.list()]

    def list_enabled_for(self, target_id: str) -> list[Rule]:
        return [rule for rule in self.list_rules() if rule.enabled and rule.target_id == target_id]


__all__ = ["RuleStore", "TargetStore", "new_id"]
