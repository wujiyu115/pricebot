"""API 级端到端测试：TestClient 走真实 HTTP 路由（fake 数据源/推送）。"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import tests.helpers as helpers
from app.server.app import create_app

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def client(tmp_path, monkeypatch):
    """把 AppServices 指到临时目录，避免污染真实 data/。"""
    monkeypatch.chdir(tmp_path)
    # 播种默认配置层（模拟镜像内 config/default_settings.json）
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    shutil.copy(REPO_ROOT / "config" / "default_settings.json", config_dir / "default_settings.json")
    import app.server.services as services_mod

    real_init = services_mod.AppServices.__init__

    def patched_init(self, run_path: str):
        real_init(self, str(tmp_path))

    monkeypatch.setattr(services_mod.AppServices, "__init__", patched_init)

    app = create_app(run_path=str(tmp_path))
    with TestClient(app) as client:
        yield client


class TestTargetsAPI:
    def test_default_targets_seeded(self, client):
        resp = client.get("/api/targets")
        assert resp.status_code == 200
        targets = resp.json()["targets"]
        names = {t["name"] for t in targets}
        assert "上金所黄金9999" in names
        assert "上金所黄金T+D" in names

    def test_sources_listed(self, client):
        resp = client.get("/api/targets/sources")
        assert resp.status_code == 200
        names = {s["name"] for s in resp.json()["sources"]}
        assert {"sina", "sge_daily", "generic_http", "fake_test"} <= names

    def test_crud_roundtrip(self, client):
        resp = client.post(
            "/api/targets",
            json={"name": "测试标的", "source": "fake_test", "symbol": "FAKE_GOLD"},
        )
        assert resp.status_code == 201
        target_id = resp.json()["target"]["id"]

        resp = client.patch(f"/api/targets/{target_id}", json={"name": "改名"})
        assert resp.status_code == 200
        assert resp.json()["target"]["name"] == "改名"

        assert client.delete(f"/api/targets/{target_id}").status_code == 200
        assert client.get("/api/targets").json()["targets"] == [
            t for t in client.get("/api/targets").json()["targets"] if t["id"] != target_id
        ]

    def test_invalid_source_rejected(self, client):
        resp = client.post(
            "/api/targets",
            json={"name": "x", "source": "nope", "symbol": "S"},
        )
        assert resp.status_code == 422

    def test_generic_http_extra_roundtrip(self, client):
        """电商/自定义接口标的: extra(url/json_path/regex) 完整保存与更新"""
        extra = {
            "url": "https://www.mi.com/buy/detail?product_id=10000229",
            "regex": '"price":"([0-9.]+)"',
        }
        resp = client.post(
            "/api/targets",
            json={"name": "小米商品监控", "source": "generic_http", "symbol": "MI_10000229", "extra": extra},
        )
        assert resp.status_code == 201
        target = resp.json()["target"]
        assert target["extra"] == extra

        # PATCH 替换 extra
        resp = client.patch(
            f"/api/targets/{target['id']}",
            json={"extra": {"url": "https://example.com/p", "json_path": "data.price"}},
        )
        assert resp.status_code == 200
        assert resp.json()["target"]["extra"] == {"url": "https://example.com/p", "json_path": "data.price"}
        assert client.delete(f"/api/targets/{target['id']}").status_code == 200

    def test_refresh_unknown_target(self, client):
        assert client.post("/api/targets/zzz/refresh").status_code == 404


class TestRulesAPI:
    def _make_target(self, client) -> str:
        resp = client.post(
            "/api/targets",
            json={"name": "测试标的", "source": "fake_test", "symbol": "FAKE_GOLD"},
        )
        return resp.json()["target"]["id"]

    def test_meta(self, client):
        resp = client.get("/api/rules/meta")
        assert resp.status_code == 200
        types = {t["value"] for t in resp.json()["rule_types"]}
        assert "cross_above" in types
        assert "pct_move_down" in types
        assert "fake_push" in {c["name"] for c in resp.json()["channels"]}

    def test_crud(self, client):
        target_id = self._make_target(client)
        resp = client.post(
            "/api/rules",
            json={
                "target_id": target_id,
                "name": "上穿900",
                "type": "cross_above",
                "threshold": 900.0,
                "channels": ["fake_push"],
            },
        )
        assert resp.status_code == 201
        rule_id = resp.json()["rule"]["id"]

        resp = client.patch(f"/api/rules/{rule_id}", json={"threshold": 950.0})
        assert resp.json()["rule"]["threshold"] == 950.0

        resp = client.get("/api/rules")
        assert any(r["id"] == rule_id for r in resp.json()["rules"])
        assert resp.json()["rules"][0]["target_name"] == "测试标的"

        assert client.delete(f"/api/rules/{rule_id}").status_code == 200

    def test_rule_validation(self, client):
        target_id = self._make_target(client)
        # 非法类型
        assert (
            client.post(
                "/api/rules",
                json={"target_id": target_id, "name": "n", "type": "bad", "threshold": 1},
            ).status_code
            == 422
        )
        # 不存在的标的
        assert (
            client.post(
                "/api/rules",
                json={
                    "target_id": "missing",
                    "name": "n",
                    "type": "cross_above",
                    "threshold": 1,
                },
            ).status_code
            == 404
        )


class TestAlertFlow:
    def test_cross_above_end_to_end(self, client):
        # 建标的 + 规则
        resp = client.post(
            "/api/targets",
            json={"name": "测试标的", "source": "fake_test", "symbol": "FAKE_GOLD"},
        )
        target_id = resp.json()["target"]["id"]
        client.post(
            "/api/rules",
            json={
                "target_id": target_id,
                "name": "上穿900",
                "type": "cross_above",
                "threshold": 900.0,
                "channels": ["fake_push"],
            },
        )
        # 启用推送渠道（默认所有渠道都是关闭状态）
        resp = client.put("/api/channels/fake_push", json={"enabled": True, "values": {}})
        assert resp.status_code == 200

        # 手动刷新 -> 引擎轮询 -> 规则触发 -> 推送捕获
        helpers.FakeSource.quotes = [
            helpers.Quote(symbol="FAKE_GOLD", name="测试黄金", last=902.5, prev_close=890.0)
        ]
        resp = client.post(f"/api/targets/{target_id}/refresh")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        assert len(helpers.PUSHED) == 1
        assert "902.50" in helpers.PUSHED[0][1].body

        # 告警落库
        resp = client.get(f"/api/alerts?target_id={target_id}")
        alerts = resp.json()["alerts"]
        assert len(alerts) == 1
        assert alerts[0]["price"] == 902.5

    def test_history_endpoint(self, client):
        resp = client.post(
            "/api/targets",
            json={"name": "测试标的", "source": "fake_test", "symbol": "FAKE_GOLD"},
        )
        target_id = resp.json()["target"]["id"]
        helpers.FakeSource.quotes = [
            helpers.Quote(symbol="FAKE_GOLD", name="测试黄金", last=890.0),
            helpers.Quote(symbol="FAKE_GOLD", name="测试黄金", last=891.0),
        ]
        client.post(f"/api/targets/{target_id}/refresh")
        client.post(f"/api/targets/{target_id}/refresh")

        resp = client.get(f"/api/prices/history?target_id={target_id}&hours=1")
        assert resp.status_code == 200
        ticks = resp.json()["ticks"]
        assert len(ticks) == 2
        assert ticks[0]["price"] == 891.0

    def test_unknown_target_history(self, client):
        assert client.get("/api/prices/history?target_id=zzz").status_code == 404


class TestChannelsAPI:
    def test_list_and_configure(self, client):
        resp = client.get("/api/channels")
        assert resp.status_code == 200
        names = {c["name"] for c in resp.json()["channels"]}
        assert {"bark", "fake_push"} <= names

        resp = client.put(
            "/api/channels/bark",
            json={"enabled": True, "values": {"device_keys": "k1"}},
        )
        assert resp.status_code == 200

        config = {c["name"]: c["config"] for c in client.get("/api/channels").json()["channels"]}
        assert config["bark"]["enabled"] is True
        assert config["bark"]["device_keys"] == "k1"

    def test_test_push_unknown_channel(self, client):
        assert client.post("/api/channels/nope/test").status_code == 404

    def test_fake_channel_test_push(self, client):
        client.put("/api/channels/fake_push", json={"enabled": True, "values": {}})
        resp = client.post("/api/channels/fake_push/test")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert len(helpers.PUSHED) == 1


class TestSettingsAPI:
    def test_get_settings_layers(self, client):
        resp = client.get("/api/settings")
        assert resp.status_code == 200
        body = resp.json()
        assert "default_settings" in body
        assert "user_overrides" in body
        assert "user_settings" in body
        assert body["default_settings"]["monitor"]["interval_seconds"] == 30

    def test_patch_with_version(self, client):
        version = client.get("/api/settings").json()["version"]
        resp = client.put(
            "/api/settings",
            json={"patch": {"monitor": {"interval_seconds": 60}}, "version": version},
        )
        assert resp.status_code == 200
        assert client.get("/api/settings").json()["user_settings"]["monitor"]["interval_seconds"] == 60

    def test_stale_version_rejected(self, client):
        resp = client.put(
            "/api/settings",
            json={"patch": {"monitor": {"interval_seconds": 1}}, "version": "stale"},
        )
        assert resp.status_code == 409

    def test_unset_key(self, client):
        version = client.get("/api/settings").json()["version"]
        client.put(
            "/api/settings",
            json={"patch": {"monitor": {"interval_seconds": 120}}, "version": version},
        )
        assert client.delete("/api/settings/keys/monitor.interval_seconds").status_code == 200
        assert client.get("/api/settings").json()["user_settings"]["monitor"]["interval_seconds"] == 30


class TestDashboard:
    def test_dashboard(self, client):
        resp = client.get("/api/dashboard")
        assert resp.status_code == 200
        body = resp.json()
        assert body["engine"]["running"] is True
        assert body["counts"]["targets"] >= 2
        assert "sina" in body["sources"]

    def test_dashboard_passes_quote_extra(self, client):
        """quote.extra 必须随 dashboard 下发（前端要展示历史最低/价位状态等源附加信息）。"""
        resp = client.post(
            "/api/targets",
            json={"name": "附加信息标的", "source": "fake_test", "symbol": "FAKE_GOLD"},
        )
        target_id = resp.json()["target"]["id"]
        helpers.FakeSource.quotes = [
            helpers.Quote(
                symbol="FAKE_GOLD",
                name="测试黄金",
                last=1759.0,
                extra={"mall": "京东商城", "hist_low": 1499.0, "trend_points": 341},
            )
        ]
        client.post(f"/api/targets/{target_id}/refresh")

        body = client.get("/api/dashboard").json()
        row = next(q for q in body["quotes"] if q["target_id"] == target_id)
        assert row["quote"]["extra"] == {
            "mall": "京东商城",
            "hist_low": 1499.0,
            "trend_points": 341,
        }
