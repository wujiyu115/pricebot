"""规则求值与防抖状态机单测（纯函数，无 IO）。"""

from __future__ import annotations

import time

from app.core.monitor.rules import (
    Rule,
    RuleState,
    evaluate_condition,
    update_rule_state,
    window_base_price,
)


def make_rule(rule_type: str = "cross_above", threshold: float = 900.0, **kwargs) -> Rule:
    return Rule(
        id="r1",
        target_id="t1",
        name="test rule",
        type=rule_type,  # type: ignore[arg-type]
        threshold=threshold,
        **kwargs,
    )


class TestCrossRules:
    def test_cross_above_true(self):
        rule = make_rule("cross_above", 900)
        assert evaluate_condition(rule, 900.0, [], time.time()) is True
        assert evaluate_condition(rule, 950.0, [], time.time()) is True

    def test_cross_above_false(self):
        rule = make_rule("cross_above", 900)
        assert evaluate_condition(rule, 899.99, [], time.time()) is False

    def test_cross_below(self):
        rule = make_rule("cross_below", 880)
        assert evaluate_condition(rule, 880.0, [], time.time()) is True
        assert evaluate_condition(rule, 900.0, [], time.time()) is False


class TestWindowRules:
    def setup_method(self):
        self.now = 1_000_000.0
        # 30 分钟窗口：起点价 880 -> 现在 900
        self.history = [
            (self.now - 1800, 880.0),
            (self.now - 900, 890.0),
            (self.now - 60, 899.0),
        ]

    def test_pct_move_up(self):
        rule = make_rule("pct_move_up", 2.0, window_minutes=30)
        # (900-880)/880 = 2.27% >= 2%
        assert evaluate_condition(rule, 900.0, self.history, self.now) is True
        assert evaluate_condition(rule, 890.0, self.history, self.now) is False

    def test_pct_move_down(self):
        rule = make_rule("pct_move_down", 1.0, window_minutes=30)
        # (875-880)/880 = -0.57%，不触发；870 -> -1.14% 触发
        assert evaluate_condition(rule, 875.0, self.history, self.now) is False
        assert evaluate_condition(rule, 870.0, self.history, self.now) is True

    def test_price_move_up(self):
        rule = make_rule("price_move_up", 15.0, window_minutes=30)
        assert evaluate_condition(rule, 895.0, self.history, self.now) is True
        assert evaluate_condition(rule, 894.0, self.history, self.now) is False

    def test_empty_history_never_fires(self):
        rule = make_rule("pct_move_up", 0.1)
        assert evaluate_condition(rule, 900.0, [], self.now) is False

    def test_window_base_price_boundary(self):
        # 窗口内的点参与，窗口外的点被忽略
        base = window_base_price(self.history, self.now, 1800)
        assert base == 880.0
        base = window_base_price(self.history, self.now, 1000)
        assert base == 890.0


class TestDebounce:
    def test_confirm_count_requires_streak(self):
        rule = make_rule("cross_above", 900, confirm_count=3, cooldown_minutes=60)
        state = RuleState()

        d = update_rule_state(rule, state, True, 1.0)
        assert d.pending and not d.fired
        d = update_rule_state(rule, state, True, 2.0)
        assert d.pending and not d.fired
        d = update_rule_state(rule, state, True, 3.0)
        assert d.fired

    def test_streak_resets_on_condition_break(self):
        rule = make_rule("cross_above", 900, confirm_count=3, cooldown_minutes=0)
        state = RuleState()
        update_rule_state(rule, state, True, 1.0)
        update_rule_state(rule, state, True, 2.0)
        d = update_rule_state(rule, state, False, 3.0)
        assert not d.fired and d.streak == 0
        d = update_rule_state(rule, state, True, 4.0)
        assert d.pending

    def test_cooldown_blocks_refire(self):
        rule = make_rule("cross_above", 900, confirm_count=1, cooldown_minutes=60)
        state = RuleState()
        assert update_rule_state(rule, state, True, 0.0).fired
        # 冷却期内（<60min）不再触发
        d = update_rule_state(rule, state, True, 60.0 - 1)
        assert not d.fired and d.cooldown
        # 冷却结束后可再次触发
        assert update_rule_state(rule, state, True, 3600.0).fired

    def test_zero_cooldown_always_fires(self):
        rule = make_rule("cross_above", 900, cooldown_minutes=0)
        state = RuleState()
        assert update_rule_state(rule, state, True, 1.0).fired
        assert update_rule_state(rule, state, True, 1.1).fired


class TestRuleSerialization:
    def test_roundtrip(self):
        rule = make_rule("pct_move_up", 1.5, window_minutes=120, confirm_count=2, cooldown_minutes=10)
        data = rule.as_dict()
        restored = Rule.from_dict(data)
        assert restored.threshold == 1.5
        assert restored.window_minutes == 120
        assert restored.confirm_count == 2
        assert restored.type == "pct_move_up"

    def test_confirm_count_min_one(self):
        rule = Rule.from_dict(
            {
                "id": "x",
                "target_id": "t",
                "name": "n",
                "type": "cross_above",
                "threshold": 1,
                "confirm_count": 0,
            }
        )
        assert rule.confirm_count == 1
