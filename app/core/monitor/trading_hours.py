"""上金所交易时段判断。

参考交易日历（简化，节假日休市由数据源空报价体现）:
- 日盘: 周一~周五 09:00-11:30, 13:30-15:30
- 夜盘: 周一~周五 20:00 - 次日 02:30（周六凌晨无夜盘，周日晚无夜盘）
"""

from __future__ import annotations

from datetime import datetime
from datetime import time as dtime

_NIGHT_START = dtime(20, 0)
_NIGHT_END = dtime(2, 30)  # 次日凌晨
_DAY_SESSIONS = (
    (dtime(9, 0), dtime(11, 30)),
    (dtime(13, 30), dtime(15, 30)),
)
# A股: 9:15 集合竞价起有成交价, 11:30-13:00 午休
_CN_STOCK_SESSIONS = (
    (dtime(9, 15), dtime(11, 30)),
    (dtime(13, 0), dtime(15, 0)),
)
# 国内期货（简化并集）: 日盘 9:00-11:30/13:30-15:00, 夜盘 21:00-次日 2:30
# （各品种夜盘截止不同（23:00/01:00/02:30），并集覆盖无遗漏，收盘后报价静止无副作用）
_CN_FUTURES_DAY = (
    (dtime(9, 0), dtime(11, 30)),
    (dtime(13, 30), dtime(15, 0)),
)


def is_sge_trading_time(dt: datetime) -> bool:
    """True when ``dt`` falls in an SGE trading session."""
    weekday = dt.weekday()  # 0=Mon ... 6=Sun
    t = dt.time()

    # 日盘：周一~周五
    if weekday < 5 and any(start <= t <= end for start, end in _DAY_SESSIONS):
        return True

    # 夜盘 20:00-24:00：周一~周五
    if weekday < 5 and t >= _NIGHT_START:
        return True

    # 夜盘 00:00-02:30：属于前一晚，周二~周六
    return 0 < weekday <= 5 and t <= _NIGHT_END


def is_cn_stock_trading_time(dt: datetime) -> bool:
    """A股交易时段: 周一~周五 9:15-11:30, 13:00-15:00（含集合竞价）。"""
    if dt.weekday() >= 5:
        return False
    t = dt.time()
    return any(start <= t <= end for start, end in _CN_STOCK_SESSIONS)


def is_cn_futures_trading_time(dt: datetime) -> bool:
    """国内期货交易时段（简化并集）。

    日盘: 周一~周五 9:00-11:30, 13:30-15:00
    夜盘: 21:00 起至次日 02:30（周五晚无夜盘 -> 周六凌晨不算）;
    周日晚无夜盘 -> 周一凌晨 00:00-02:30 不算。
    """
    weekday = dt.weekday()
    t = dt.time()
    # 日盘
    if weekday < 5 and any(start <= t <= end for start, end in _CN_FUTURES_DAY):
        return True
    # 夜盘前半段 21:00-24:00（周一~周五）
    if weekday < 5 and t >= dtime(21, 0):
        return True
    # 夜盘后半段 00:00-02:30（周二~周六）
    return 0 < weekday <= 5 and t <= _NIGHT_END


def now_is_sge_trading_time() -> bool:
    return is_sge_trading_time(datetime.now())


def should_poll(schedule: str | None, dt: datetime) -> bool:
    """schedule: "always"(默认) | "sge" | "cn_stock" | "cn_futures" | None。"""
    if not schedule or schedule == "always":
        return True
    if schedule == "sge":
        return is_sge_trading_time(dt)
    if schedule == "cn_stock":
        return is_cn_stock_trading_time(dt)
    if schedule == "cn_futures":
        return is_cn_futures_trading_time(dt)
    return True


__all__ = [
    "is_cn_futures_trading_time",
    "is_cn_stock_trading_time",
    "is_sge_trading_time",
    "now_is_sge_trading_time",
    "should_poll",
]
