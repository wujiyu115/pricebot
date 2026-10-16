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
        self._error_notified_at: dict[str, float] = {}  # target_id -> 上次源失效推送时间
        self._brief_sent_at: float = 0.0  # 上次聚合简报推送时间（全局）
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
        # 统一以 tick 起点打点：gather 内各协程按 fetch 启动先后差毫秒级打点时，
        # `now - last_poll >= interval` 的临界比较会周期性翻转——快源恰好踩线
        # 通过、慢 0.x 秒的源被系统性挤掉一轮，稳定漂移成 2 倍轮询间隔
        # （2026-10 生产实测：30s 配置下快源 30s / 慢源 60s，详见 AGENTS.md）
        for target in due:
            self._last_poll[target["id"]] = now
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

        try:
            source_cls = get_source_class(source_name)
        except KeyError as exc:
            await self._handle_poll_failure(target, str(exc))
            return

        try:
            source = source_cls(timeout=self.timeout)
            quote = await source.fetch(symbol, target.get("extra") or {})
        except (SourceError, Exception) as exc:
            logger.warning(f"poll {source_name}:{symbol} failed: {exc}")
            prev = self._status.get(target_id) or {}
            await self._handle_poll_failure(target, str(exc), prev_quote=prev.get("quote"))
            return

        if quote.last is None:
            await self._handle_poll_failure(target, "source returned no price")
            return

        now = time.time()
        self._store.add_tick(target_id, now, quote.last, quote.bid, quote.ask)
        self._set_status(target_id, error=None, quote=quote)
        await self._maybe_send_briefing(now)
        await self._evaluate_rules(target, quote, now)

    async def _maybe_send_briefing(self, now: float) -> None:
        """聚合行情简报：全局单一计时，到点后把**所有**标的最新价合并成一条推送。

        配置 monitor.briefing_notify：enabled / interval_days / channels
        （空 = 所有启用渠道）。interval_days 支持小数（0.5 = 12 小时）；
        0 是合法值（任一标的成功轮询即推一条聚合简报），禁用 ``or`` 短路取默认。
        首次成功轮询即推一次；此后按全局间隔计时（不区分标的）。
        """
        cfg = (self._get_config() or {}).get("briefing_notify") or {}
        if not cfg.get("enabled"):
            return
        raw_days = cfg.get("interval_days")
        try:
            interval_days = max(0.0, float(raw_days))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            interval_days = 1.0
        if now - self._brief_sent_at < interval_days * 86400:
            return
        await self._send_aggregated_briefing(now, interval_days=interval_days, cfg=cfg)

    async def send_briefing_now(self) -> dict:
        """手动立即发一条聚合简报（不著 enabled 开关，计时器一并重置）。"""
        cfg = (self._get_config() or {}).get("briefing_notify") or {}
        raw_days = cfg.get("interval_days")
        try:
            interval_days = max(0.0, float(raw_days))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            interval_days = 1.0
        return await self._send_aggregated_briefing(
            time.time(), interval_days=interval_days, cfg=cfg, manual=True
        )

    async def _send_aggregated_briefing(
        self, now: float, interval_days: float, cfg: dict[str, Any], manual: bool = False
    ) -> dict:
        rows: list[str] = []
        quoted = 0
        targets = self._targets.list()
        for target in targets:
            entry = self._status.get(target["id"]) or {}
            quote: Quote | None = entry.get("quote")
            if quote is None or quote.last is None:
                continue  # 无报价标的不逐条列出（非交易时段会很吵），尾部汇总一句
            quoted += 1
            name = target.get("name") or quote.name or quote.symbol
            unit = quote.unit or ""
            change_str = ""
            if quote.prev_close:
                pct = (quote.last - quote.prev_close) / quote.prev_close * 100
                change_str = f"（较昨收 {pct:+.2f}%）"
            rows.append(f"{name}：{quote.last:.2f} {unit}{change_str}".rstrip())

        if not rows:
            logger.info("BRIEFING skipped: no target has a quote yet")
            return {"ok": False, "sent": 0, "detail": "所有标的均无报价，无需简报"}

        total = len(targets)
        body_lines = list(rows)
        if quoted < total:
            body_lines.append(f"（另有 {total - quoted} 个标的暂无报价）")
        if manual:
            interval_str = "手动推送"
        elif interval_days:
            interval_str = f"每 {interval_days:g} 天一次"
        else:
            interval_str = "每次轮询"
        body_lines += [
            "─────",
            f"简报间隔：{interval_str}",
            f"时间：{datetime.fromtimestamp(now).strftime('%Y-%m-%d %H:%M:%S')}",
        ]
        channels = [str(c).strip() for c in (cfg.get("channels") or []) if str(c).strip()] or None
        message = Message(
            title=f"📊 价格简报 · {quoted} 个标的",
            body="\n".join(body_lines),
            group="PriceBot",
            severity="info",
        )
        results = await self._notifier.send(message, channels=channels)
        self._brief_sent_at = now
        summary = " / ".join(rows)
        self._store.add_alert(
            ts=now,
            rule_id="briefing",
            target_id="",
            rule_name="行情简报",
            price=None,
            message=summary,
            channels=channels or [r.channel for r in results],
            results=[{"channel": r.channel, "ok": r.ok, "detail": r.detail} for r in results],
        )
        logger.info(
            f"BRIEFING aggregated {quoted}/{total} targets ({interval_str}) -> {len(results)} channel(s)"
        )
        return {
            "ok": all(r.ok for r in results) if results else False,
            "sent": quoted,
            "total": total,
            "channels": [r.channel for r in results],
            "results": [{"channel": r.channel, "ok": r.ok, "detail": r.detail} for r in results],
        }

    async def _handle_poll_failure(
        self, target: dict[str, Any], error: str, prev_quote: Quote | None = None
    ) -> None:
        """记录失败状态，并按配置推送源失效告警。"""
        self._set_status(target["id"], error=error, quote=prev_quote)
        await self._maybe_notify_source_error(target, error)

    async def _maybe_notify_source_error(self, target: dict[str, Any], error: str) -> None:
        """源失效推送：连续失败达阈值后告警，重复推送按独立间隔节流。

        配置 monitor.source_error_notify：enabled / min_failures /
        repeat_minutes / channels（空 = 所有启用渠道）。注意 0 是合法值
        （repeat_minutes=0 表示每次失败都推），禁用 ``or`` 短路取默认。
        """
        cfg = (self._get_config() or {}).get("source_error_notify") or {}
        if not cfg.get("enabled"):
            return
        status = self._status.get(target["id"]) or {}
        error_count = int(status.get("error_count") or 0)
        raw_min = cfg.get("min_failures")
        try:
            min_failures = max(1, int(raw_min))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            min_failures = 3
        if error_count < min_failures:
            return

        now = time.time()
        raw_repeat = cfg.get("repeat_minutes")
        try:
            repeat_minutes = max(0.0, float(raw_repeat))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            repeat_minutes = 30.0
        last = self._error_notified_at.get(target["id"])
        if last is not None and now - last < repeat_minutes * 60:
            return
        self._error_notified_at[target["id"]] = now

        name = target.get("name") or target.get("symbol") or target["id"]
        channels = [str(c).strip() for c in (cfg.get("channels") or []) if str(c).strip()] or None
        message = Message(
            title=f"⚠️ 数据源失效：{name}",
            body=(
                f"{target.get('source')}:{target.get('symbol')} 连续 {error_count} 次获取失败\n"
                f"最近错误：{error}\n"
                f"时间：{datetime.fromtimestamp(now).strftime('%Y-%m-%d %H:%M:%S')}"
            ),
            group="PriceBot",
            severity="warn",
        )
        results = await self._notifier.send(message, channels=channels)
        self._store.add_alert(
            ts=now,
            rule_id="source_error",
            target_id=target["id"],
            rule_name="源失效",
            price=None,
            message=f"数据源失效：{name}（{error}）",
            channels=channels or [r.channel for r in results],
            results=[{"channel": r.channel, "ok": r.ok, "detail": r.detail} for r in results],
        )
        logger.info(
            f"SOURCE-ERROR ALERT {name} ({error_count} consecutive failures) -> {len(results)} channel(s)"
        )

    async def refresh_now(self, target_id: str) -> dict[str, Any] | None:
        """Manual refresh (API button). Returns the fresh status or None."""
        target = self._targets.get(target_id)
        if not target:
            return None
        async with self._lock:
            self._last_poll[target_id] = time.time()
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
        unit = quote.unit or "元/克"
        change_str = ""
        if quote.prev_close:
            pct = (quote.last - quote.prev_close) / quote.prev_close * 100
            change_str = f"（较昨收 {pct:+.2f}%）"

        title = f"{name} {rule_type_label(rule.type)}"
        lines = [
            f"{name}：{quote.last:.2f} {unit}{change_str}",
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
            # 恢复成功后重置失效推送节流：下次失效需重新累计连续失败次数
            self._error_notified_at.pop(target_id, None)
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
