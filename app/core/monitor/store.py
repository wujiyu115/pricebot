"""SQLite 持久化：价格历史 tick + 告警日志。

只在后台线程的 event loop 里同步调用（sqlite3 是阻塞 IO）；API 层读取
一律经 ``services.run_coro`` 投递到后台 loop，避免阻塞 uvicorn 事件循环。
"""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from ...utils.logger import logger

_SCHEMA = """
CREATE TABLE IF NOT EXISTS ticks (
    target_id TEXT NOT NULL,
    ts REAL NOT NULL,
    price REAL NOT NULL,
    bid REAL,
    ask REAL
);
CREATE INDEX IF NOT EXISTS idx_ticks_target_ts ON ticks(target_id, ts);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    rule_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    rule_name TEXT NOT NULL,
    price REAL,
    message TEXT NOT NULL,
    channels TEXT NOT NULL,
    results TEXT
);
CREATE INDEX IF NOT EXISTS idx_alerts_ts ON alerts(ts DESC);
"""

# 告警历史只保留最新 N 条（插入后自动裁剪，历史积压在启动时也会被裁剪）
ALERTS_MAX_ROWS = 50


class Store:
    def __init__(self, db_path: str | Path, retention_days: int = 90) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.retention_days = retention_days
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._trim_alerts()
            self._conn.commit()

    # ------------------------------------------------------------------ ticks
    def add_tick(self, target_id: str, ts: float, price: float, bid: float | None, ask: float | None) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO ticks (target_id, ts, price, bid, ask) VALUES (?, ?, ?, ?, ?)",
                (target_id, ts, price, bid, ask),
            )
            self._conn.commit()

    def get_ticks(
        self, target_id: str, since_ts: float | None = None, limit: int = 5000
    ) -> list[dict[str, Any]]:
        with self._lock:
            if since_ts is None:
                rows = self._conn.execute(
                    "SELECT ts, price, bid, ask FROM ticks WHERE target_id = ? ORDER BY ts DESC LIMIT ?",
                    (target_id, limit),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT ts, price, bid, ask FROM ticks "
                    "WHERE target_id = ? AND ts >= ? ORDER BY ts DESC LIMIT ?",
                    (target_id, since_ts, limit),
                ).fetchall()
        return [{"ts": r["ts"], "price": r["price"], "bid": r["bid"], "ask": r["ask"]} for r in rows]

    def window_history(self, target_id: str, window_seconds: float, now: float) -> list[tuple[float, float]]:
        """升序 (epoch, price)，窗口起点前后各留一点余量供基准价计算。"""
        since = now - window_seconds - 120.0
        rows = self.get_ticks(target_id, since_ts=since)
        rows.reverse()
        return [(r["ts"], r["price"]) for r in rows]

    def prune(self) -> int:
        cutoff = time.time() - self.retention_days * 86400
        with self._lock:
            cur = self._conn.execute("DELETE FROM ticks WHERE ts < ?", (cutoff,))
            self._conn.commit()
        return cur.rowcount or 0

    def _trim_alerts(self) -> int:
        """删除超出 ALERTS_MAX_ROWS 的旧告警（按 ts 新旧保留最新 N 条）。"""
        cur = self._conn.execute(
            "DELETE FROM alerts WHERE id NOT IN "
            "(SELECT id FROM alerts ORDER BY ts DESC, id DESC LIMIT ?)",
            (ALERTS_MAX_ROWS,),
        )
        return cur.rowcount or 0

    # ----------------------------------------------------------------- alerts
    def add_alert(
        self,
        ts: float,
        rule_id: str,
        target_id: str,
        rule_name: str,
        price: float | None,
        message: str,
        channels: list[str],
        results: list[dict[str, Any]],
    ) -> None:
        import json

        with self._lock:
            self._conn.execute(
                "INSERT INTO alerts (ts, rule_id, target_id, rule_name, price, message, channels, results) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    ts,
                    rule_id,
                    target_id,
                    rule_name,
                    price,
                    message,
                    json.dumps(channels, ensure_ascii=False),
                    json.dumps(results, ensure_ascii=False),
                ),
            )
            removed = self._trim_alerts()
            if removed:
                logger.info("trimmed %d old alerts (keep latest %d)", removed, ALERTS_MAX_ROWS)
            self._conn.commit()

    def list_alerts(self, limit: int = 50, target_id: str | None = None) -> list[dict[str, Any]]:
        import json

        with self._lock:
            if target_id:
                rows = self._conn.execute(
                    "SELECT * FROM alerts WHERE target_id = ? ORDER BY ts DESC LIMIT ?",
                    (target_id, limit),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM alerts ORDER BY ts DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        out = []
        for r in rows:
            try:
                results = json.loads(r["results"] or "[]")
            except ValueError:
                results = []
            # channels 写入侧是 json.dumps（见 add_alert）；兼容历史逗号分隔行
            raw_channels = r["channels"] or ""
            try:
                channels = json.loads(raw_channels)
                if not isinstance(channels, list):
                    channels = [str(channels)]
            except ValueError:
                channels = [c.strip() for c in raw_channels.split(",") if c.strip()]
            out.append(
                {
                    "id": r["id"],
                    "ts": r["ts"],
                    "rule_id": r["rule_id"],
                    "target_id": r["target_id"],
                    "rule_name": r["rule_name"],
                    "price": r["price"],
                    "message": r["message"],
                    "channels": channels,
                    "results": results,
                }
            )
        return out

    def clear_alerts(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM alerts")
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()
        logger.info(f"store closed: {self.db_path}")


__all__ = ["Store"]
