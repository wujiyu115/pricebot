"""配置分层纯函数单测。"""

from __future__ import annotations

from app.core.config.layering import (
    apply_patch,
    config_hash,
    deep_merge,
    rebuild_effective,
    strip_defaults,
    unset_path,
)


def test_deep_merge_nested():
    base = {"a": 1, "b": {"x": 1, "y": 2}, "c": 3}
    merged = deep_merge(base, {"b": {"y": 20}, "d": 4})
    assert merged == {"a": 1, "b": {"x": 1, "y": 20}, "c": 3, "d": 4}
    # base 不被修改
    assert base["b"]["y"] == 2


def test_deep_merge_override_scalar_with_dict():
    merged = deep_merge({"a": 1}, {"a": {"b": 2}})
    assert merged == {"a": {"b": 2}}


def test_rebuild_effective_in_place():
    target = deep_merge({"monitor": {"interval": 30}}, {})
    rebuild_effective(target, {"monitor": {"interval": 60}}, {"monitor": {"enabled": True}})
    assert target["monitor"] == {"interval": 60, "enabled": True}


def test_apply_patch_sparse():
    overrides = {"notify": {"bark": {"enabled": True}}}
    apply_patch(overrides, {"notify": {"bark": {"device_keys": "k1"}}})
    assert overrides["notify"]["bark"] == {"enabled": True, "device_keys": "k1"}


def test_unset_path_removes_nested():
    data = {"notify": {"bark": {"sound": "x"}, "telegram": {}}}
    assert unset_path(data, "notify.bark.sound") is True
    assert "sound" not in data["notify"]["bark"]
    assert unset_path(data, "notify.bark.sound") is False
    assert unset_path(data, "notify.missing.key") is False


def test_strip_defaults():
    defaults = {"a": 1, "b": {"x": 1}, "c": 3}
    user = {"a": 1, "b": {"x": 2}, "c": 3}
    assert strip_defaults(user, defaults) == {"b": {"x": 2}}


def test_config_hash_changes():
    assert config_hash({"a": 1}) == config_hash({"a": 1})
    assert config_hash({"a": 1}) != config_hash({"a": 2})
    # key order irrelevant
    assert config_hash({"a": 1, "b": 2}) == config_hash({"b": 2, "a": 1})
