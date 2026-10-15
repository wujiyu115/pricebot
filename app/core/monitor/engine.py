"""监控引擎：后台线程轮询标的 -> 落库 -> 规则求值 -> 推送。"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from collections.abc import Callable
from datetime import datetime
from typing import Any

from ...utils.logger import logger
from ..notify.base import Message
from ..notify.manager import NotificationManager
from ..sources import get_source_class
from ..sources.base import Quote, SourceError
from .rules import (
    FireDecision,
    Rule,
    RuleState,
    describe_condition,
    evaluate_condition,
    rule_type_label,
    update_rule_state,
)
from .store import Store
from .stores import RuleStore, TargetStore
from .trading_hours import should_poll


class MonitorEngine:
    """Owns the polling loop. One instance per process."""

    def __init__(
        self,
        target_store: TargetStore,
        rule_store: RuleStore,
        store: Store,
        notifier: NotificationManager,
        monitor_config_getter: Callable[[], dict[str, Any]],
    ) -> None:
        self._targets = target_store
        self._rules = rule_store
        self._store = store
        self._notifier = notifier
        # 配置惰性读取：settings 写入会整体重建嵌套 dict，引用捕获会脱钩
        self._get_config = monitor_config_getter

        self._rule_states: dict[str, RuleState] = defaultdict(RuleState)
        self._last_poll: dict[str, float] = {}
        self._status: dict[str, dict[str, Any]] = {}  # target_id -> runtime status
        self._lock = asyncio.Lock()
        self._stopping = asyncio.Event()

    # ------------------------------------------------------------------ props
    @property
    def interval(self) -> int:
        config = self._get_config() or {}
        return max(5, int(config.get("interval_seconds") or 30))

    @property
    def timeout(self) -> float:
        config = self._get_config() or {}
        return float(config.get("source_timeout_seconds") or 10)

    # ------------------------------------------------------------------- loop
    async def run_forever(self) -> None:
        logger.info("monitor engine started")
        prune_interval = 6 * 3600
        last_prune = 0.0
        while not self._stopping.is_set():
            started = time.time()
            try:
                await self._tick()
            except Exception:
                logger.exception("monitor tick failed")
            if time.time() - last_prune > prune_interval:
                try:
                    removed = self._store.prune()
                    if removed:
                        logger.info(f"pruned {removed} old ticks")
                except Exception:
                    logger.exception("prune failed")
                last_prune = time.time()
            elapsed = time.time() - started
            await asyncio.sleep(max(1.0, self.interval - elapsed))
        logger.info("monitor engine stopped")

    def stop(self) -> None:
        self._stopping.set()

    # ------------------------------------------------------------------- tick
    async def _tick(self) -> None:
        now = time.time()
        now_dt = datetime.now()
        due = []
        for target in self._targets.list_enabled():
            interval = self._target_interval(target)
            if now - self._last_poll.get(target["id"], 0) >= interval and should_poll(
                target.get("schedule"), now_dt
            ):
                due.append(target)

        if not due:
            return
        await asyncio.gather(*(self._poll_target(t) for t in due))

    def _target_interval(self, target: dict[str, Any]) -> int:
        override = target.get("interval_seconds")
        if override:
            try:
                return max(5, int(override))
            except (TypeError, ValueError):
                pass
        return self.interval

    # ------------------------------------------------------------------ poll
    async def _poll_target(self, target: dict[str, Any]) -> None:
        target_id = target["id"]
        source_name = target.get("source") or ""
        symbol = target.get("symbol") or ""
        async with self._lock:
            self._last_poll[target_id] = time.time()

        try:
            source_cls = get_source_class(source_name)
        except KeyError as exc:
            self._set_status(target_id, error=str(exc), quote=None)
            return

        try:
            source = source_cls(timeout=self.timeout)
            quote = await source.fetch(symbol, target.get("extra") or {})
        except (SourceError, Exception) as exc:
            logger.warning(f"poll {source_name}:{symbol} failed: {exc}")
            prev = self._status.get(target_id) or {}
            self._set_status(target_id, error=str(exc), quote=prev.get("quote"))
            return

        if quote.last is None:
            self._set_status(target_id, error="source returned no price", quote=None)
            return

        now = time.time()
        self._store.add_tick(target_id, now, quote.last, quote.bid, quote.ask)
        self._set_status(target_id, error=None, quote=quote)
        await self._evaluate_rules(target, quote, now)

    async def refresh_now(self, target_id: str) -> dict[str, Any] | None:
        """Manual refresh (API button). Returns the fresh status or None."""
        target = self._targets.get(target_id)
        if not target:
            return None
        await self._poll_target(target)
        return self._status.get(target_id)

    # ------------------------------------------------------------------ rules
    async def _evaluate_rules(self, target: dict[str, Any], quote: Quote, now: float) -> None:
        rules = self._rules.list_enabled_for(target["id"])
        if not rules:
            return
        max_window = max((r.window_minutes for r in rules), default=30)
        history = self._store.window_history(target["id"], max_window * 60 + 120, now)

        for rule in rules:
            try:
                await self._evaluate_rule(rule, target, quote, history, now)
            except Exception:
                logger.exception(f"rule evaluation failed: {rule.id} {rule.name}")

    async def _evaluate_rule(
        self,
        rule: Rule,
        target: dict[str, Any],
        quote: Quote,
        history: list[tuple[float, float]],
        now: float,
    ) -> None:
        assert quote.last is not None
        condition = evaluate_condition(rule, quote.last, history, now)
        state = self._rule_states[rule.id]
        decision: FireDecision = update_rule_state(rule, state, condition, now)
        status_view = self._rule_status(rule, decision)
        self._status.setdefault(target["id"], {}).setdefault("rules", {})[rule.id] = status_view
        if not decision.fired:
            return

        message_text, detail = self._build_message(rule, target, quote, history, now)
        channels = rule.channels or None
        icon = "🟢" if "up" in rule.type or rule.type == "cross_above" else "🔴"
        results = await self._notifier.send(
            Message(title=f"{icon} {message_text}", body=detail, group="PriceBot"),
            channels=channels,
        )
        self._store.add_alert(
            ts=now,
            rule_id=rule.id,
            target_id=target["id"],
            rule_name=rule.name,
            price=quote.last,
            message=message_text,
            channels=rule.channels or [r.channel for r in results],
            results=[{"channel": r.channel, "ok": r.ok, "detail": r.detail} for r in results],
        )
        logger.info(f"ALERT {target.get('name')} {message_text} -> {len(results)} channel(s)")

    def _rule_status(self, rule: Rule, decision: FireDecision) -> dict[str, Any]:
        return {
            "condition": decision.fired or decision.pending or decision.cooldown,
            "streak": decision.streak,
            "pending": decision.pending,
            "cooldown": decision.cooldown,
            "fired": decision.fired,
        }

    def _build_message(
        self,
        rule: Rule,
        target: dict[str, Any],
        quote: Quote,
        history: list[tuple[float, float]],
        now: float,
    ) -> tuple[str, str]:
        assert quote.last is not None
        name = target.get("name") or quote.name or quote.symbol
        change_str = ""
        if quote.prev_close:
            pct = (quote.last - quote.prev_close) / quote.prev_close * 100
            change_str = f"（较昨收 {pct:+.2f}%）"

        title = f"{name} {rule_type_label(rule.type)}"
        lines = [
            f"{name}：{quote.last:.2f} 元/克{change_str}",
            f"规则：{rule.name}（{rule_type_label(rule.type)}",
        ]
        detail = describe_condition(rule, quote.last, history, now)
        if detail.get("threshold") is not None:
            lines[1] += f" 阈值 {detail['threshold']:g}"
        if detail.get("window_minutes"):
            lines[1] += f"，{detail['window_minutes']} 分钟窗口"
            if detail.get("base_price"):
                lines.append(
                    f"窗口基准 {detail['base_price']:.2f} → 现价 {quote.last:.2f}"
                    f"（{detail.get('change', 0):+.2f} / {detail.get('change_pct', 0):+.2f}%）"
                )
        lines[1] += "）"
        if quote.bid and quote.ask:
            lines.append(f"买一 {quote.bid:.2f} / 卖一 {quote.ask:.2f}")
        lines.append(f"时间：{datetime.fromtimestamp(now).strftime('%Y-%m-%d %H:%M:%S')}")
        return title, "\n".join(lines)

    # ----------------------------------------------------------------- status
    def _set_status(self, target_id: str, error: str | None, quote: Quote | None) -> None:
        entry = self._status.setdefault(target_id, {})
        if error is not None:
            entry["last_error"] = error
            entry["error_count"] = int(entry.get("error_count") or 0) + 1
        else:
            entry["last_error"] = None
            entry["error_count"] = 0
        if quote is not None:
            entry["quote"] = quote
        entry["updated_at"] = time.time()

    def get_live_view(self) -> list[dict[str, Any]]:
        """Snapshot for the dashboard: target + last quote + rule states."""
        out = []
        for target in self._targets.list():
            entry = self._status.get(target["id"]) or {}
            quote: Quote | None = entry.get("quote")
            view: dict[str, Any] = {
                "target": target,
                "last_poll": entry.get("updated_at"),
                "last_error": entry.get("last_error"),
                "error_count": entry.get("error_count") or 0,
                "quote": quote.as_dict() if quote else None,
                "rules": entry.get("rules") or {},
            }
            out.append(view)
        return out


__all__ = ["MonitorEngine"]
