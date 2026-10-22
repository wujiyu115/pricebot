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
# 港股: 9:30-12:00, 13:00-16:00（含开盘前竞价时段已并入连续时段，节假日休市由空报价体现）
_HK_STOCK_SESSIONS = (
    (dtime(9, 30), dtime(12, 0)),
    (dtime(13, 0), dtime(16, 0)),
)
# 美股（北京时间并集窗口，覆盖夏令时 21:30-04:00 / 冬令时 22:30-05:00）:
# 晚盘 21:30-24:00 + 凌晨 00:00-05:00（凌晨段归属前一夜，周二~周六）
_US_EVENING_START = dtime(21, 30)
_US_MORNING_END = dtime(5, 0)


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


def is_hk_stock_trading_time(dt: datetime) -> bool:
    """港股交易时段: 周一~周五 9:30-12:00, 13:00-16:00（港节假日休市无法识别，报价静止无副作用）。"""
    if dt.weekday() >= 5:
        return False
    t = dt.time()
    return any(start <= t <= end for start, end in _HK_STOCK_SESSIONS)


def is_us_stock_trading_time(dt: datetime) -> bool:
    """美股交易时段（北京时间并集窗口 21:30-次日05:00，覆盖夏/冬令时）。

    夏令时盘中 = 21:30-04:00，冬令时 = 22:30-05:00；并集 21:30-05:00 覆盖两者，
    超出实际盘中时报价静止无副作用。凌晨段归属前一夜：周二~周六算交易，
    周一凌晨（=美东周日晚）与周六晚起（=美东周六）不算。
    """
    weekday = dt.weekday()
    t = dt.time()
    if weekday < 5 and t >= _US_EVENING_START:  # 周一~周五晚盘
        return True
    return 0 < weekday <= 5 and t <= _US_MORNING_END  # 周二~周六凌晨


def now_is_sge_trading_time() -> bool:
    return is_sge_trading_time(datetime.now())


def should_poll(schedule: str | None, dt: datetime) -> bool:
    """schedule: "always"(默认) | "sge" | "cn_stock" | "hk_stock" | "us_stock" | "cn_futures" | None。"""
    if not schedule or schedule == "always":
        return True
    if schedule == "sge":
        return is_sge_trading_time(dt)
    if schedule == "cn_stock":
        return is_cn_stock_trading_time(dt)
    if schedule == "hk_stock":
        return is_hk_stock_trading_time(dt)
    if schedule == "us_stock":
        return is_us_stock_trading_time(dt)
    if schedule == "cn_futures":
        return is_cn_futures_trading_time(dt)
    return True


__all__ = [
    "is_cn_futures_trading_time",
    "is_cn_stock_trading_time",
    "is_hk_stock_trading_time",
    "is_sge_trading_time",
    "is_us_stock_trading_time",
    "now_is_sge_trading_time",
    "should_poll",
]
