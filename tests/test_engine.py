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


class TestUnifiedTickStamps:
    async def test_tick_stamps_all_targets_with_same_timestamp(self, store, empty_target_store, rule_store):
        """同一 tick 内所有标的时间戳一致——防 2 倍间隔漂移（>= 临界比较翻转）"""
        add_target(empty_target_store)
        empty_target_store.add(
            {"name": "二号标的", "source": "fake_test", "symbol": "FAKE_GOLD", "schedule": "always"}
        )
        helpers.FakeSource.quotes = [
            helpers.Quote(symbol="FAKE_GOLD", name="测试黄金", last=890.0),
            helpers.Quote(symbol="FAKE_GOLD", name="测试黄金", last=891.0),
        ]
        engine = build_engine(store, empty_target_store, rule_store)
        await engine._tick()

        stamps = list(engine._last_poll.values())
        assert len(stamps) == 2
        assert len(set(stamps)) == 1, f"同一 tick 的 last_poll 应一致，实际: {stamps}"

    async def test_manual_refresh_stamps_last_poll(self, store, empty_target_store, rule_store):
        """手动刷新也要打点：30s 内引擎不重复轮询"""
        target = add_target(empty_target_store)
        helpers.FakeSource.quotes = [
            helpers.Quote(symbol="FAKE_GOLD", name="测试黄金", last=890.0),
            helpers.Quote(symbol="FAKE_GOLD", name="测试黄金", last=891.0),
        ]
        engine = build_engine(store, empty_target_store, rule_store)
        await engine.refresh_now(target["id"])
        assert target["id"] in engine._last_poll

        # 手动刷新后立刻 _tick：不应重复轮询（quote 已被手动刷新消耗）
        await engine._tick()
        ticks = store.get_ticks(target["id"])
        assert len(ticks) == 1, "手动刷新后 30s 内引擎不应重复轮询"


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
        helpers.FakeSource.quotes = [helpers.Quote(symbol="FAKE_GOLD", name="测试黄金", last=880.0)]
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
            helpers.FakeSource.quotes = [helpers.Quote(symbol="FAKE_GOLD", name="测试黄金", last=price)]
            await engine.refresh_now(target["id"])

        # 前两次 pending，第三次才触发一次
        assert len(helpers.PUSHED) == 1
        assert len(store.list_alerts()) == 1

        # 触发后 streak 归零：需重新连续确认 3 次才会再次触发
        for price in (906.0, 906.0):
            helpers.FakeSource.quotes = [helpers.Quote(symbol="FAKE_GOLD", name="测试黄金", last=price)]
            await engine.refresh_now(target["id"])
        assert len(helpers.PUSHED) == 1  # 前两次仍是 pending

        helpers.FakeSource.quotes = [helpers.Quote(symbol="FAKE_GOLD", name="测试黄金", last=906.0)]
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
            helpers.FakeSource.quotes = [helpers.Quote(symbol="FAKE_GOLD", name="测试黄金", last=price)]
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
        helpers.FakeSource.quotes = [helpers.Quote(symbol="FAKE_GOLD", name="测试黄金", last=880.0)]
        await engine.refresh_now(target["id"])
        assert helpers.PUSHED == []

        # 第二笔：890.0 -> +1.14%，触发
        helpers.FakeSource.quotes = [helpers.Quote(symbol="FAKE_GOLD", name="测试黄金", last=890.0)]
        await engine.refresh_now(target["id"])
        assert len(helpers.PUSHED) == 1
        assert "窗口基准" in helpers.PUSHED[0][1].body


class TestLiveView:
    async def test_live_view_shape(self, store, empty_target_store, rule_store):
        target = add_target(empty_target_store)
        empty_target_store.add(
            {"name": "停用标的", "source": "fake_test", "symbol": "FAKE_GOLD", "enabled": False}
        )
        helpers.FakeSource.quotes = [helpers.Quote(symbol="FAKE_GOLD", name="测试黄金", last=895.0)]
        engine = build_engine(store, empty_target_store, rule_store)
        await engine.refresh_now(target["id"])

        view = engine.get_live_view()
        assert len(view) == 2
        by_name = {v["target"]["name"]: v for v in view}
        assert by_name["测试黄金"]["quote"]["last"] == 895.0
        assert by_name["停用标的"]["quote"] is None


class TestSourceErrorNotify:
    """源失效推送：连续失败阈值 + 独立重复间隔 + 独立渠道。"""

    @staticmethod
    def _config(**overrides) -> dict:
        cfg = {
            "interval_seconds": 30,
            "source_error_notify": {
                "enabled": True,
                "min_failures": 2,
                "repeat_minutes": 30,
                "channels": ["fake_push"],
            },
        }
        cfg["source_error_notify"].update(overrides)
        return cfg

    async def test_fires_after_consecutive_failures(self, store, empty_target_store, rule_store):
        target = add_target(empty_target_store)
        helpers.FakeSource.quotes = []  # fetch 抛 SourceError
        engine = build_engine(store, empty_target_store, rule_store, self._config())

        await engine.refresh_now(target["id"])  # 失败 1：未达阈值，不推
        assert helpers.PUSHED == []
        await engine.refresh_now(target["id"])  # 失败 2：达标，推送
        assert len(helpers.PUSHED) == 1
        title, msg = helpers.PUSHED[0]
        assert title == "fake_push"
        assert "数据源失效" in msg.title
        assert "测试黄金" in msg.title
        assert "连续 2 次获取失败" in msg.body

        alerts = store.list_alerts(limit=10)
        assert len(alerts) == 1
        assert alerts[0]["rule_id"] == "source_error"
        assert alerts[0]["rule_name"] == "源失效"
        assert alerts[0]["price"] is None

    async def test_repeat_interval_throttles(self, store, empty_target_store, rule_store):
        target = add_target(empty_target_store)
        helpers.FakeSource.quotes = []
        engine = build_engine(
            store, empty_target_store, rule_store, self._config(min_failures=1, repeat_minutes=30)
        )

        await engine.refresh_now(target["id"])
        await engine.refresh_now(target["id"])  # 间隔内：节流
        await engine.refresh_now(target["id"])
        assert len(helpers.PUSHED) == 1

    async def test_repeat_zero_pushes_every_failure(self, store, empty_target_store, rule_store):
        target = add_target(empty_target_store)
        helpers.FakeSource.quotes = []
        engine = build_engine(
            store, empty_target_store, rule_store, self._config(min_failures=1, repeat_minutes=0)
        )

        await engine.refresh_now(target["id"])
        await engine.refresh_now(target["id"])
        assert len(helpers.PUSHED) == 2  # repeat=0 不节流

    async def test_recovery_resets_counter_and_throttle(self, store, empty_target_store, rule_store):
        target = add_target(empty_target_store)
        engine = build_engine(store, empty_target_store, rule_store, self._config())

        helpers.FakeSource.quotes = []
        await engine.refresh_now(target["id"])
        await engine.refresh_now(target["id"])  # 推送 1 次
        assert len(helpers.PUSHED) == 1

        helpers.FakeSource.quotes = [helpers.Quote(symbol="FAKE_GOLD", name="测试黄金", last=895.0)]
        await engine.refresh_now(target["id"])  # 恢复：error_count 归零、节流重置
        assert engine.get_live_view()[0]["error_count"] == 0

        helpers.FakeSource.quotes = []
        await engine.refresh_now(target["id"])  # 重新失败 1 次：需重新累计
        assert len(helpers.PUSHED) == 1
        await engine.refresh_now(target["id"])  # 失败 2 次：重新达标，再推
        assert len(helpers.PUSHED) == 2

    async def test_independent_channels(self, store, empty_target_store, rule_store):
        """源失效推送只走配置的渠道，不影响规则推送渠道。"""
        target = add_target(empty_target_store)
        # fake_push2 未在 notify 配置中启用 -> send 返回 disabled
        from app.core.notify.manager import NotificationManager

        config = self._config(channels=["fake_push", "fake_push2"])
        notifier = NotificationManager(
            lambda: {"fake_push": {"enabled": True}, "fake_push2": {"enabled": False}}
        )
        engine = MonitorEngine(
            target_store=empty_target_store,
            rule_store=rule_store,
            store=store,
            notifier=notifier,
            monitor_config_getter=lambda: config,
        )
        helpers.FakeSource.quotes = []
        await engine.refresh_now(target["id"])
        await engine.refresh_now(target["id"])
        assert len(helpers.PUSHED) == 1  # 只有 fake_push 成功
        alerts = store.list_alerts(limit=10)
        assert alerts[0]["channels"] == ["fake_push", "fake_push2"]

    async def test_disabled_by_default(self, store, empty_target_store, rule_store):
        target = add_target(empty_target_store)
        helpers.FakeSource.quotes = []
        engine = build_engine(store, empty_target_store, rule_store)  # 无该配置
        for _ in range(5):
            await engine.refresh_now(target["id"])
        assert helpers.PUSHED == []
        assert store.list_alerts(limit=10) == []


class TestBriefingNotify:
    """聚合行情简报：所有标的最新价合并成**一条**推送，全局单一计时。"""

    @staticmethod
    def _config(**overrides) -> dict:
        cfg = {
            "interval_seconds": 30,
            "briefing_notify": {"enabled": True, "interval_days": 1, "channels": ["fake_push"]},
        }
        cfg["briefing_notify"].update(overrides)
        return cfg

    @staticmethod
    def _quote(price: float) -> helpers.Quote:
        return helpers.Quote(symbol="FAKE_GOLD", name="测试黄金", last=price, prev_close=900.0, unit="元/克")

    async def test_first_success_then_interval(self, store, empty_target_store, rule_store):
        import time

        target = add_target(empty_target_store)
        engine = build_engine(store, empty_target_store, rule_store, self._config())

        helpers.FakeSource.quotes = [self._quote(897.0)]
        await engine.refresh_now(target["id"])  # 首次成功即推（聚合）
        assert len(helpers.PUSHED) == 1
        msg = helpers.PUSHED[0][1]
        assert "价格简报" in msg.title
        assert "1 个标的" in msg.title
        assert "测试黄金" in msg.body
        assert "897.00" in msg.body
        assert "较昨收 -0.33%" in msg.body
        assert "每 1 天一次" in msg.body
        alerts = store.list_alerts(limit=10)
        assert alerts[0]["rule_id"] == "briefing" and alerts[0]["price"] is None

        for _ in range(3):
            helpers.FakeSource.quotes = [self._quote(898.0)]
            await engine.refresh_now(target["id"])  # 间隔未到：不推
        assert len(helpers.PUSHED) == 1

        # 时间回拨：上次推送时间改为 1 天前 -> 再推
        engine._brief_sent_at = time.time() - 86400 - 1
        helpers.FakeSource.quotes = [self._quote(900.0)]
        await engine.refresh_now(target["id"])
        assert len(helpers.PUSHED) == 2
        assert "900.00" in helpers.PUSHED[1][1].body

    async def test_all_targets_in_one_message(self, store, empty_target_store, rule_store):
        import time

        t1 = add_target(empty_target_store)
        t2 = empty_target_store.add(
            {"name": "另一个", "source": "fake_test", "symbol": "FAKE_GOLD", "schedule": "always"}
        )
        t3 = empty_target_store.add(
            {"name": "暂无报价", "source": "fake_test", "symbol": "FAKE_GOLD", "schedule": "always"}
        )
        engine = build_engine(store, empty_target_store, rule_store, self._config())

        # 首次成功轮询即推：此刻只有 t1 有报价，消息仅含 1 个标的
        helpers.FakeSource.quotes = [self._quote(895.0), self._quote(896.0), self._quote(897.0)]
        await engine.refresh_now(t1["id"])
        assert len(helpers.PUSHED) == 1
        msg = helpers.PUSHED[0][1]
        assert "1 个标的" in msg.title
        assert "测试黄金" in msg.body and "895.00" in msg.body
        # 其余标的尚未轮询：尾部汇总一句
        assert "另有 2 个标的暂无报价" in msg.body

        await engine.refresh_now(t2["id"])  # 计时未到：不推
        assert len(helpers.PUSHED) == 1

        # 回拨后轮询第 3 个标的：一条消息聚齐全部 3 个报价
        engine._brief_sent_at = time.time() - 86400 - 1
        await engine.refresh_now(t3["id"])
        assert len(helpers.PUSHED) == 2
        body = helpers.PUSHED[1][1].body
        assert "3 个标的" in helpers.PUSHED[1][1].title
        assert all(n in body for n in ("测试黄金", "另一个", "暂无报价"))
        assert "895.00" in body and "896.00" in body and "897.00" in body
        assert "暂无报价" not in body.split("─────")[0].replace("暂无报价：", "")  # 无报价行不出现

    async def test_manual_send_ignores_enabled(self, store, empty_target_store, rule_store):
        target = add_target(empty_target_store)
        engine = build_engine(store, empty_target_store, rule_store)  # 未启用简报

        # 无任何报价：手动触发不发
        result = await engine.send_briefing_now()
        assert result["ok"] is False and result["sent"] == 0
        assert helpers.PUSHED == []

        helpers.FakeSource.quotes = [self._quote(893.0)]
        await engine.refresh_now(target["id"])  # enabled=False：周期简报不推
        assert helpers.PUSHED == []

        result = await engine.send_briefing_now()  # 手动触发不著 enabled
        assert result["ok"] is True and result["sent"] == 1
        assert len(helpers.PUSHED) == 1
        assert "手动推送" in helpers.PUSHED[0][1].body

        # 手动发送重置计时器：紧接着的周期检查不会立即再推
        helpers.FakeSource.quotes = [self._quote(894.0)]
        await engine.refresh_now(target["id"])
        assert len(helpers.PUSHED) == 1

    async def test_interval_zero_pushes_every_poll(self, store, empty_target_store, rule_store):
        target = add_target(empty_target_store)
        engine = build_engine(store, empty_target_store, rule_store, self._config(interval_days=0))

        for i in range(3):
            helpers.FakeSource.quotes = [self._quote(895.0 + i)]
            await engine.refresh_now(target["id"])
        assert len(helpers.PUSHED) == 3  # 0 = 每次成功轮询都推
        assert "每次轮询" in helpers.PUSHED[0][1].body

    async def test_failures_do_not_reset_timer(self, store, empty_target_store, rule_store):
        import time

        target = add_target(empty_target_store)
        engine = build_engine(store, empty_target_store, rule_store, self._config())
        tid = target["id"]

        helpers.FakeSource.quotes = [self._quote(895.0)]
        await engine.refresh_now(tid)  # 首推，计时开始
        helpers.FakeSource.quotes = []
        await engine.refresh_now(tid)  # 失败：不影响计时
        engine._brief_sent_at = time.time() - 86400 - 1
        helpers.FakeSource.quotes = [self._quote(896.0)]
        await engine.refresh_now(tid)
        assert len(helpers.PUSHED) == 2

    async def test_independent_channels(self, store, empty_target_store, rule_store):
        from app.core.notify.manager import NotificationManager

        config = self._config(channels=["fake_push", "other"])
        notifier = NotificationManager(lambda: {"fake_push": {"enabled": True}})
        engine = MonitorEngine(
            target_store=empty_target_store,
            rule_store=rule_store,
            store=store,
            notifier=notifier,
            monitor_config_getter=lambda: config,
        )
        target = add_target(empty_target_store)
        helpers.FakeSource.quotes = [self._quote(895.0)]
        await engine.refresh_now(target["id"])
        assert len(helpers.PUSHED) == 1  # 只走 fake_push
        alerts = store.list_alerts(limit=10)
        assert alerts[0]["channels"] == ["fake_push", "other"]

    async def test_disabled_by_default(self, store, empty_target_store, rule_store):
        target = add_target(empty_target_store)
        engine = build_engine(store, empty_target_store, rule_store)  # 无该配置
        for i in range(5):
            helpers.FakeSource.quotes = [self._quote(895.0 + i)]
            await engine.refresh_now(target["id"])
        assert helpers.PUSHED == []
        assert store.list_alerts(limit=10) == []


class TestTickScheduling:
    async def test_disabled_target_not_polled(self, store, empty_target_store, rule_store):
        target = add_target(empty_target_store)
        empty_target_store.update(target["id"], {"enabled": False})
        helpers.FakeSource.quotes = [helpers.Quote(symbol="FAKE_GOLD", name="测试黄金", last=895.0)]
        engine = build_engine(store, empty_target_store, rule_store)
        await engine._tick()
        assert store.get_ticks(target["id"]) == []

    async def test_sge_schedule_skips_weekend(self, store, empty_target_store, rule_store, monkeypatch):
        import datetime

        target = add_target(empty_target_store)
        empty_target_store.update(target["id"], {"schedule": "sge"})
        helpers.FakeSource.quotes = [helpers.Quote(symbol="FAKE_GOLD", name="测试黄金", last=895.0)]
        engine = build_engine(store, empty_target_store, rule_store)

        # 周六 10:00，非交易时段
        saturday = datetime.datetime(2026, 10, 17, 10, 0)
        monkeypatch.setattr("app.core.monitor.engine.datetime", SimpleDatetime(saturday))
        await engine._tick()
        assert store.get_ticks(target["id"]) == []


class SimpleDatetime:
    """让 engine.datetime.now() 返回固定时间。"""

    def __init__(self, fixed: datetime.datetime) -> None:
        self._fixed = fixed

    def now(self):
        return self._fixed
