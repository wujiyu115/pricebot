"""监控引擎端到端单测（fake 数据源，验证轮询→落库→防抖→推送全链路）。"""

from __future__ import annotations

import datetime

import tests.helpers as helpers
from app.core.monitor.engine import MonitorEngine
from app.core.monitor.rules import Rule
from app.core.notify.manager import NotificationManager


def build_engine(store, target_store, rule_store, monitor_config=None) -> MonitorEngine:
    config = monitor_config or {"interval_seconds": 30}
    notifier = NotificationManager(lambda: {"fake_push": {"enabled": True}})
    return MonitorEngine(
        target_store=target_store,
        rule_store=rule_store,
        store=store,
        notifier=notifier,
        monitor_config_getter=lambda: config,
    )


def add_target(target_store) -> dict:
    return target_store.add(
        {"name": "测试黄金", "source": "fake_test", "symbol": "FAKE_GOLD", "schedule": "always"}
    )


class TestEnginePolling:
    async def test_poll_stores_tick_and_status(self, store, empty_target_store, rule_store):
        target = add_target(empty_target_store)
        helpers.FakeSource.quotes = [
            helpers.Quote(symbol="FAKE_GOLD", name="测试黄金", last=895.0, prev_close=890.0)
        ]
        engine = build_engine(store, empty_target_store, rule_store)
        result = await engine.refresh_now(target["id"])

        assert result is not None
        assert result["quote"].last == 895.0
        assert result["last_error"] is None
        ticks = store.get_ticks(target["id"])
        assert len(ticks) == 1
        assert ticks[0]["price"] == 895.0

    async def test_poll_error_recorded(self, store, empty_target_store, rule_store):
        target = add_target(empty_target_store)
        helpers.FakeSource.quotes = []  # fetch 会抛 SourceError
        engine = build_engine(store, empty_target_store, rule_store)
        result = await engine.refresh_now(target["id"])
        assert result is not None
        assert result.get("last_error")
        assert result.get("error_count") == 1
        assert store.get_ticks(target["id"]) == []

    async def test_refresh_unknown_target(self, store, empty_target_store, rule_store):
        engine = build_engine(store, empty_target_store, rule_store)
        assert await engine.refresh_now("missing") is None


class TestEngineRules:
    async def test_cross_above_fires_and_pushes(self, store, empty_target_store, rule_store):
        target = add_target(empty_target_store)
        rule_store.add(
            Rule(
                id="r1",
                target_id=target["id"],
                name="金价上穿900",
                type="cross_above",
                threshold=900.0,
                channels=["fake_push"],
            ).as_dict()
        )
        helpers.FakeSource.quotes = [
            helpers.Quote(symbol="FAKE_GOLD", name="测试黄金", last=905.0, prev_close=890.0)
        ]
        engine = build_engine(store, empty_target_store, rule_store)

        await engine.refresh_now(target["id"])

        assert len(helpers.PUSHED) == 1
        channel, message = helpers.PUSHED[0]
        assert channel == "fake_push"
        assert "上穿" in message.title
        assert "905.00" in message.body

        alerts = store.list_alerts()
        assert len(alerts) == 1
        assert alerts[0]["rule_name"] == "金价上穿900"
        assert alerts[0]["price"] == 905.0

    async def test_condition_not_met_no_push(self, store, empty_target_store, rule_store):
        target = add_target(empty_target_store)
        rule_store.add(
            Rule(
                id="r1",
                target_id=target["id"],
                name="金价上穿900",
                type="cross_above",
                threshold=900.0,
            ).as_dict()
        )
        helpers.FakeSource.quotes = [
            helpers.Quote(symbol="FAKE_GOLD", name="测试黄金", last=880.0)
        ]
        engine = build_engine(store, empty_target_store, rule_store)
        await engine.refresh_now(target["id"])
        assert helpers.PUSHED == []
        assert store.list_alerts() == []

    async def test_confirm_count_debounces(self, store, empty_target_store, rule_store):
        target = add_target(empty_target_store)
        rule_store.add(
            Rule(
                id="r1",
                target_id=target["id"],
                name="金价上穿900",
                type="cross_above",
                threshold=900.0,
                confirm_count=3,
                cooldown_minutes=0,
                channels=["fake_push"],
            ).as_dict()
        )
        engine = build_engine(store, empty_target_store, rule_store)

        for price in (905.0, 905.0, 905.0):
            helpers.FakeSource.quotes = [
                helpers.Quote(symbol="FAKE_GOLD", name="测试黄金", last=price)
            ]
            await engine.refresh_now(target["id"])

        # 前两次 pending，第三次才触发一次
        assert len(helpers.PUSHED) == 1
        assert len(store.list_alerts()) == 1

        # 触发后 streak 归零：需重新连续确认 3 次才会再次触发
        for price in (906.0, 906.0):
            helpers.FakeSource.quotes = [
                helpers.Quote(symbol="FAKE_GOLD", name="测试黄金", last=price)
            ]
            await engine.refresh_now(target["id"])
        assert len(helpers.PUSHED) == 1  # 前两次仍是 pending

        helpers.FakeSource.quotes = [
            helpers.Quote(symbol="FAKE_GOLD", name="测试黄金", last=906.0)
        ]
        await engine.refresh_now(target["id"])
        assert len(helpers.PUSHED) == 2  # 冷却为 0，第三次确认后再次触发

    async def test_cooldown_suppresses_refire(self, store, empty_target_store, rule_store):
        target = add_target(empty_target_store)
        rule_store.add(
            Rule(
                id="r1",
                target_id=target["id"],
                name="下穿880",
                type="cross_below",
                threshold=880.0,
                cooldown_minutes=60,
                channels=["fake_push"],
            ).as_dict()
        )
        engine = build_engine(store, empty_target_store, rule_store)

        for price in (875.0, 875.0):
            helpers.FakeSource.quotes = [
                helpers.Quote(symbol="FAKE_GOLD", name="测试黄金", last=price)
            ]
            await engine.refresh_now(target["id"])

        # 第一次触发，第二次被 60 分钟冷却压掉
        assert len(helpers.PUSHED) == 1

    async def test_window_rule_uses_history(self, store, empty_target_store, rule_store):
        target = add_target(empty_target_store)
        rule_store.add(
            Rule(
                id="r1",
                target_id=target["id"],
                name="30分钟涨1%",
                type="pct_move_up",
                threshold=1.0,
                window_minutes=30,
                channels=["fake_push"],
            ).as_dict()
        )
        engine = build_engine(store, empty_target_store, rule_store)

        # 第一笔：880.0（成为窗口基准价）
        helpers.FakeSource.quotes = [
            helpers.Quote(symbol="FAKE_GOLD", name="测试黄金", last=880.0)
        ]
        await engine.refresh_now(target["id"])
        assert helpers.PUSHED == []

        # 第二笔：890.0 -> +1.14%，触发
        helpers.FakeSource.quotes = [
            helpers.Quote(symbol="FAKE_GOLD", name="测试黄金", last=890.0)
        ]
        await engine.refresh_now(target["id"])
        assert len(helpers.PUSHED) == 1
        assert "窗口基准" in helpers.PUSHED[0][1].body


class TestLiveView:
    async def test_live_view_shape(self, store, empty_target_store, rule_store):
        target = add_target(empty_target_store)
        empty_target_store.add(
            {"name": "停用标的", "source": "fake_test", "symbol": "FAKE_GOLD", "enabled": False}
        )
        helpers.FakeSource.quotes = [
            helpers.Quote(symbol="FAKE_GOLD", name="测试黄金", last=895.0)
        ]
        engine = build_engine(store, empty_target_store, rule_store)
        await engine.refresh_now(target["id"])

        view = engine.get_live_view()
        assert len(view) == 2
        by_name = {v["target"]["name"]: v for v in view}
        assert by_name["测试黄金"]["quote"]["last"] == 895.0
        assert by_name["停用标的"]["quote"] is None


class TestTickScheduling:
    async def test_disabled_target_not_polled(self, store, empty_target_store, rule_store):
        target = add_target(empty_target_store)
        empty_target_store.update(target["id"], {"enabled": False})
        helpers.FakeSource.quotes = [
            helpers.Quote(symbol="FAKE_GOLD", name="测试黄金", last=895.0)
        ]
        engine = build_engine(store, empty_target_store, rule_store)
        await engine._tick()
        assert store.get_ticks(target["id"]) == []

    async def test_sge_schedule_skips_weekend(self, store, empty_target_store, rule_store, monkeypatch):
        import datetime

        target = add_target(empty_target_store)
        empty_target_store.update(target["id"], {"schedule": "sge"})
        helpers.FakeSource.quotes = [
            helpers.Quote(symbol="FAKE_GOLD", name="测试黄金", last=895.0)
        ]
        engine = build_engine(store, empty_target_store, rule_store)

        # 周六 10:00，非交易时段
        saturday = datetime.datetime(2026, 10, 17, 10, 0)
        monkeypatch.setattr(
            "app.core.monitor.engine.datetime", SimpleDatetime(saturday)
        )
        await engine._tick()
        assert store.get_ticks(target["id"]) == []


class SimpleDatetime:
    """让 engine.datetime.now() 返回固定时间。"""

    def __init__(self, fixed: datetime.datetime) -> None:
        self._fixed = fixed

    def now(self):
        return self._fixed
