"""上金所交易时段判断单测。"""

from __future__ import annotations

from datetime import datetime

from app.core.monitor.trading_hours import is_sge_trading_time, should_poll


def dt(weekday: int, hhmm: str) -> datetime:
    # 2026-10-12 是周一
    base_monday = datetime(2026, 10, 12)
    day = base_monday + __import__("datetime").timedelta(days=weekday)
    hh, mm = map(int, hhmm.split(":"))
    return day.replace(hour=hh, minute=mm)


class TestTradingHours:
    def test_day_session_morning(self):
        assert is_sge_trading_time(dt(0, "09:00")) is True
        assert is_sge_trading_time(dt(2, "10:30")) is True
        assert is_sge_trading_time(dt(0, "11:30")) is True
        assert is_sge_trading_time(dt(0, "11:31")) is False

    def test_day_session_afternoon(self):
        assert is_sge_trading_time(dt(0, "13:30")) is True
        assert is_sge_trading_time(dt(4, "15:30")) is True
        assert is_sge_trading_time(dt(4, "15:31")) is False

    def test_lunch_break(self):
        assert is_sge_trading_time(dt(0, "12:00")) is False

    def test_night_session_evening(self):
        assert is_sge_trading_time(dt(0, "20:00")) is True
        assert is_sge_trading_time(dt(4, "23:59")) is True

    def test_night_session_after_midnight(self):
        # 周二 01:00 属于周一晚
        assert is_sge_trading_time(dt(1, "01:00")) is True
        # 周六 02:00 属于周五晚（weekday=5）
        assert is_sge_trading_time(dt(5, "02:00")) is True
        assert is_sge_trading_time(dt(5, "02:30")) is True
        assert is_sge_trading_time(dt(5, "02:31")) is False
        # 周一 01:00 属于周日晚，无夜盘
        assert is_sge_trading_time(dt(0, "01:00")) is False

    def test_weekend_day(self):
        assert is_sge_trading_time(dt(5, "10:00")) is False
        assert is_sge_trading_time(dt(6, "10:00")) is False


class TestCnStockHours:
    def test_morning_session(self):
        from app.core.monitor.trading_hours import is_cn_stock_trading_time

        assert is_cn_stock_trading_time(dt(0, "09:15")) is True  # 集合竞价
        assert is_cn_stock_trading_time(dt(0, "09:30")) is True
        assert is_cn_stock_trading_time(dt(2, "11:30")) is True

    def test_lunch_break(self):
        from app.core.monitor.trading_hours import is_cn_stock_trading_time

        assert is_cn_stock_trading_time(dt(0, "11:31")) is False
        assert is_cn_stock_trading_time(dt(0, "12:30")) is False

    def test_afternoon_session(self):
        from app.core.monitor.trading_hours import is_cn_stock_trading_time

        assert is_cn_stock_trading_time(dt(0, "13:00")) is True
        assert is_cn_stock_trading_time(dt(4, "15:00")) is True
        assert is_cn_stock_trading_time(dt(4, "15:01")) is False

    def test_weekend_and_evening(self):
        from app.core.monitor.trading_hours import is_cn_stock_trading_time

        assert is_cn_stock_trading_time(dt(5, "10:00")) is False
        assert is_cn_stock_trading_time(dt(6, "10:00")) is False
        assert is_cn_stock_trading_time(dt(0, "09:14")) is False


class TestCnFuturesHours:
    def setup_method(self):
        from app.core.monitor.trading_hours import is_cn_futures_trading_time

        self.fn = is_cn_futures_trading_time

    def test_day_sessions(self):
        assert self.fn(dt(0, "09:00")) is True
        assert self.fn(dt(0, "10:30")) is True
        assert self.fn(dt(0, "11:30")) is True
        assert self.fn(dt(0, "12:00")) is False  # 午休
        assert self.fn(dt(0, "13:30")) is True
        assert self.fn(dt(4, "15:00")) is True
        assert self.fn(dt(0, "08:59")) is False

    def test_night_session(self):
        assert self.fn(dt(0, "21:00")) is True
        assert self.fn(dt(2, "23:59")) is True
        assert self.fn(dt(2, "01:00")) is True  # 周三凌晨=周二夜盘
        assert self.fn(dt(5, "02:30")) is True  # 周六凌晨=周五夜盘
        assert self.fn(dt(5, "02:31")) is False
        assert self.fn(dt(0, "01:00")) is False  # 周一凌晨=周日晚无夜盘
        assert self.fn(dt(6, "22:00")) is False  # 周六晚无夜盘

    def test_should_poll_schedule(self):
        assert should_poll("cn_futures", dt(0, "10:00")) is True
        assert should_poll("cn_futures", dt(6, "10:00")) is False
        assert should_poll("cn_futures", dt(0, "12:00")) is False


class TestShouldPoll:
    def test_always(self):
        assert should_poll("always", dt(6, "10:00")) is True
        assert should_poll(None, dt(6, "10:00")) is True

    def test_sge_schedule(self):
        assert should_poll("sge", dt(0, "10:00")) is True
        assert should_poll("sge", dt(6, "10:00")) is False

    def test_cn_stock_schedule(self):
        assert should_poll("cn_stock", dt(0, "10:00")) is True
        assert should_poll("cn_stock", dt(6, "10:00")) is False
        assert should_poll("cn_stock", dt(0, "12:30")) is False
