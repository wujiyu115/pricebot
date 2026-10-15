"""pytest 公共夹具。"""

from __future__ import annotations

import pytest

import tests.helpers as helpers
from app.core.monitor.store import Store
from app.core.monitor.stores import RuleStore, TargetStore


@pytest.fixture(autouse=True)
def _clean_collectors():
    helpers.reset_collectors()
    yield
    helpers.reset_collectors()


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "test.db", retention_days=30)


@pytest.fixture
def target_store(tmp_path):
    return TargetStore(tmp_path / "targets.json")


@pytest.fixture
def rule_store(tmp_path):
    return RuleStore(tmp_path / "rules.json")


@pytest.fixture
def empty_target_store(tmp_path):
    """不注入默认标的（绕过 DEFAULT_TARGETS 播种）。"""
    ts = TargetStore(tmp_path / "targets.json")
    ts._data = []
    ts._save()
    return ts
