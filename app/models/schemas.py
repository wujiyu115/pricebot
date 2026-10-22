"""API 数据模型（pydantic）。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class TargetIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    source: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    enabled: bool = True
    schedule: Literal["always", "sge", "cn_stock", "hk_stock", "us_stock", "cn_futures"] = "always"
    interval_seconds: int | None = Field(default=None, ge=5, le=86400)
    extra: dict[str, Any] = Field(default_factory=dict)


class TargetPatch(BaseModel):
    name: str | None = None
    source: str | None = None
    symbol: str | None = None
    enabled: bool | None = None
    schedule: Literal["always", "sge", "cn_stock", "hk_stock", "us_stock", "cn_futures"] | None = None
    interval_seconds: int | None = Field(default=None, ge=5, le=86400)
    extra: dict[str, Any] | None = None


class VerifyIn(BaseModel):
    """标的保存前的试抓验证入参。"""

    source: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    extra: dict[str, Any] = Field(default_factory=dict)


class RuleIn(BaseModel):
    target_id: str
    name: str = Field(min_length=1, max_length=64)
    type: Literal[
        "cross_above",
        "cross_below",
        "pct_move_up",
        "pct_move_down",
        "price_move_up",
        "price_move_down",
    ]
    threshold: float
    window_minutes: int = Field(default=30, ge=1, le=10080)
    confirm_count: int = Field(default=1, ge=1, le=100)
    cooldown_minutes: int = Field(default=60, ge=0, le=10080)
    channels: list[str] = Field(default_factory=list)
    enabled: bool = True


class RulePatch(BaseModel):
    target_id: str | None = None
    name: str | None = None
    type: str | None = None
    threshold: float | None = None
    window_minutes: int | None = Field(default=None, ge=1, le=10080)
    confirm_count: int | None = Field(default=None, ge=1, le=100)
    cooldown_minutes: int | None = Field(default=None, ge=0, le=10080)
    channels: list[str] | None = None
    enabled: bool | None = None


class SettingsPatchIn(BaseModel):
    patch: dict[str, Any]
    version: str


class ChannelConfigIn(BaseModel):
    enabled: bool | None = None
    values: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "ChannelConfigIn",
    "RuleIn",
    "RulePatch",
    "SettingsPatchIn",
    "TargetIn",
    "TargetPatch",
]
