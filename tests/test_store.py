"""SQLite Store 单测。"""

from __future__ import annotations

import time


class TestTicks:
    def test_add_and_get_desc(self, store):
        now = time.time()
        store.add_tick("t1", now - 10, 890.0, 889.5, 890.5)
        store.add_tick("t1", now, 895.0, 894.5, 895.5)
        rows = store.get_ticks("t1")
        assert len(rows) == 2
        assert rows[0]["price"] == 895.0  # 最新在前
        assert rows[1]["price"] == 890.0

    def test_since_filter(self, store):
        now = time.time()
        store.add_tick("t1", now - 7200, 880.0, None, None)
        store.add_tick("t1", now - 60, 890.0, None, None)
        rows = store.get_ticks("t1", since_ts=now - 3600)
        assert len(rows) == 1
        assert rows[0]["price"] == 890.0

    def test_isolated_targets(self, store):
        store.add_tick("t1", time.time(), 1.0, None, None)
        store.add_tick("t2", time.time(), 2.0, None, None)
        assert len(store.get_ticks("t1")) == 1

    def test_window_history_ascending(self, store):
        now = time.time()
        store.add_tick("t1", now - 1000, 880.0, None, None)
        store.add_tick("t1", now - 10, 895.0, None, None)
        history = store.window_history("t1", 600, now)
        assert history == [(now - 10, 895.0)]

    def test_prune(self, store):
        now = time.time()
        store.add_tick("t1", now - 40 * 86400, 800.0, None, None)  # 40 天前
        store.add_tick("t1", now, 890.0, None, None)
        removed = store.prune()
        assert removed == 1
        assert len(store.get_ticks("t1")) == 1


class TestAlerts:
    def test_add_list_and_order(self, store):
        store.add_alert(
            100.0,
            "r1",
            "t1",
            "上穿900",
            900.5,
            "msg",
            ["bark"],
            [{"channel": "bark", "ok": True, "detail": ""}],
        )
        store.add_alert(200.0, "r2", "t1", "涨幅", 910.0, "msg2", [], [])
        alerts = store.list_alerts()
        assert len(alerts) == 2
        assert alerts[0]["ts"] == 200.0  # 新的在前
        assert alerts[1]["results"][0]["ok"] is True  # 200 的 results 为空

    def test_filter_by_target(self, store):
        store.add_alert(100.0, "r1", "t1", "n", 1.0, "m", [], [])
        store.add_alert(101.0, "r2", "t2", "n", 2.0, "m", [], [])
        assert len(store.list_alerts(target_id="t2")) == 1

    def test_clear(self, store):
        store.clear_alerts()
        store.add_alert(1.0, "r", "t", "n", 1.0, "m", [], [])
        assert len(store.list_alerts()) == 1
        store.clear_alerts()
        assert store.list_alerts() == []

    def test_retention_keep_latest_50(self, store):
        """插入超量告警后只保留最新 50 条，且保留的是 ts 最大的那些。"""
        for i in range(60):
            store.add_alert(float(i), f"r{i}", "t", "n", float(i), f"m{i}", [], [])
        alerts = store.list_alerts(limit=500)
        assert len(alerts) == 50
        assert alerts[0]["ts"] == 59.0  # 最新在前
        assert alerts[-1]["ts"] == 10.0  # 0~9 被裁剪

    def test_retention_trims_backlog_on_init(self, store, tmp_path):
        """历史积压（升级前遗留）在 Store 重开时也会被裁剪。"""
        for i in range(70):
            store.add_alert(float(i), f"r{i}", "t", "n", float(i), f"m{i}", [], [])
        db = store.db_path
        store.close()

        from app.core.monitor.store import Store

        reopened = Store(db)
        assert len(reopened.list_alerts(limit=500)) == 50
        assert reopened.list_alerts()[0]["ts"] == 69.0
        reopened.close()
