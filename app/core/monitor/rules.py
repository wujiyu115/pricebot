"""告警规则求值：纯函数，无 IO，全部可单测。

规则类型:
  - cross_above / cross_below : 最新价 >= / <= 阈值
  - pct_move_up / pct_move_down : 窗口内涨/跌幅 >= 阈值(%)
  - price_move_up / price_move_down : 窗口内绝对涨/跌 >= 阈值(元)

防抖: 条件需连续 ``confirm_count`` 次轮询成立才触发；触发后进入
``cooldown_minutes`` 冷却。状态机见 :class:`RuleState`。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

RuleType = Literal[
    "cross_above",
    "cross_below",
    "pct_move_up",
    "pct_move_down",
    "price_move_up",
    "price_move_down",
]

RULE_TYPES: list[dict[str, str]] = [
    {"value": "cross_above", "label": "上穿阈值", "hint": "最新价 ≥ 阈值时触发"},
    {"value": "cross_below", "label": "下穿阈值", "hint": "最新价 ≤ 阈值时触发"},
    {"value": "pct_move_up", "label": "窗口涨幅%", "hint": "N 分钟内涨幅 ≥ 阈值(%)"},
    {"value": "pct_move_down", "label": "窗口跌幅%", "hint": "N 分钟内跌幅 ≥ 阈值(%)"},
    {"value": "price_move_up", "label": "窗口涨额", "hint": "N 分钟内上涨 ≥ 阈值(元)"},
    {"value": "price_move_down", "label": "窗口跌额", "hint": "N 分钟内下跌 ≥ 阈值(元)"},
]


@dataclass
class Rule:
    id: str
    target_id: str
    name: str
    type: RuleType
    threshold: float
    window_minutes: int = 30
    confirm_count: int = 1
    cooldown_minutes: int = 60
    channels: list[str] = field(default_factory=list)
    enabled: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "target_id": self.target_id,
            "name": self.name,
            "type": self.type,
            "threshold": self.threshold,
            "window_minutes": self.window_minutes,
            "confirm_count": self.confirm_count,
            "cooldown_minutes": self.cooldown_minutes,
            "channels": list(self.channels),
            "enabled": self.enabled,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> Rule:
        # 注意：cooldown_minutes=0（无冷却）是合法值，不能用 `or` 取默认
        def _get(key: str, default: Any) -> Any:
            value = data.get(key)
            return default if value is None else value

        return Rule(
            id=str(data["id"]),
            target_id=str(data["target_id"]),
            name=str(_get("name", "")),
            type=_get("type", "cross_above"),  # type: ignore[arg-type,assignment]
            threshold=float(_get("threshold", 0.0)),
            window_minutes=int(_get("window_minutes", 30)),
            confirm_count=max(1, int(_get("confirm_count", 1))),
            cooldown_minutes=int(_get("cooldown_minutes", 60)),
            channels=[str(c) for c in (_get("channels", []) or [])],
            enabled=bool(_get("enabled", True)),
        )


@dataclass
class RuleState:
    """防抖状态（engine 内存态，不持久化）。"""

    streak: int = 0
    last_fired: float | None = None
    last_condition: bool | None = None


@dataclass
class FireDecision:
    """一次轮询后的决策。"""

    fired: bool
    streak: int
    pending: bool  # 条件成立但未达 confirm_count
    cooldown: bool  # 刚触发过，冷却中


def window_base_price(history: list[tuple[float, float]], now: float, window_seconds: float) -> float | None:
    """窗口基准价：窗口起点处（或窗口内最早）的价格。

    ``history`` 是 (epoch, price) 升序列表，只包含窗口附近的点。
    """
    window_start = now - window_seconds
    in_window = [(ts, p) for ts, p in history if ts >= window_start]
    candidates = in_window or history
    if not candidates:
        return None
    return candidates[0][1]


def evaluate_condition(rule: Rule, last: float, history: list[tuple[float, float]], now: float) -> bool:
    """求规则条件当前是否成立（不含防抖/冷却）。"""
    if rule.type == "cross_above":
        return last >= rule.threshold
    if rule.type == "cross_below":
        return last <= rule.threshold

    base = window_base_price(history, now, rule.window_minutes * 60)
    if base is None:
        return False
    delta = last - base
    if rule.type == "pct_move_up":
        return base != 0 and (delta / base) * 100.0 >= rule.threshold
    if rule.type == "pct_move_down":
        return base != 0 and (delta / base) * 100.0 <= -rule.threshold
    if rule.type == "price_move_up":
        return delta >= rule.threshold
    if rule.type == "price_move_down":
        return delta <= -rule.threshold
    return False


def describe_condition(
    rule: Rule, last: float, history: list[tuple[float, float]], now: float
) -> dict[str, Any]:
    """供告警文案/前端展示用的条件细节。"""
    detail: dict[str, Any] = {"type": rule.type, "threshold": rule.threshold}
    if rule.type.startswith(("pct_", "price_")):
        base = window_base_price(history, now, rule.window_minutes * 60)
        detail["window_minutes"] = rule.window_minutes
        detail["base_price"] = base
        if base:
            detail["change"] = last - base
            detail["change_pct"] = (last - base) / base * 100.0
    return detail


def update_rule_state(
    rule: Rule,
    state: RuleState,
    condition_true: bool,
    now: float,
) -> FireDecision:
    """推进防抖状态机，返回是否应当触发。"""
    state.last_condition = condition_true
    if condition_true:
        state.streak += 1
    else:
        state.streak = 0

    if state.streak == 0:
        return FireDecision(fired=False, streak=0, pending=False, cooldown=False)

    if state.streak < rule.confirm_count:
        return FireDecision(fired=False, streak=state.streak, pending=True, cooldown=False)

    if state.last_fired is not None and now - state.last_fired < rule.cooldown_minutes * 60:
        return FireDecision(fired=False, streak=state.streak, pending=False, cooldown=True)

    state.last_fired = now
    state.streak = 0
    return FireDecision(fired=True, streak=0, pending=False, cooldown=False)


def rule_type_label(rule_type: str) -> str:
    for item in RULE_TYPES:
        if item["value"] == rule_type:
            return item["label"]
    return rule_type


__all__ = [
    "RULE_TYPES",
    "FireDecision",
    "Rule",
    "RuleState",
    "describe_condition",
    "evaluate_condition",
    "rule_type_label",
    "update_rule_state",
    "window_base_price",
]
