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


def now_is_sge_trading_time() -> bool:
    return is_sge_trading_time(datetime.now())


def should_poll(schedule: str | None, dt: datetime) -> bool:
    """schedule: "always"(默认) | "sge" | None。"""
    if not schedule or schedule == "always":
        return True
    if schedule == "sge":
        return is_sge_trading_time(dt)
    return True


__all__ = ["is_sge_trading_time", "now_is_sge_trading_time", "should_poll"]
