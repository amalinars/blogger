import json

import pytest

from core.hop_registry import HopRegistry, load_supabase_config


def _write_config(tmp_path, key="test-key"):
    path = tmp_path / "supabase_config.json"
    path.write_text(
        json.dumps(
            {
                "supabase_url": "https://example.supabase.co",
                "supabase_key": key,
                "schema": "proxxies",
            }
        ),
        encoding="utf-8",
    )
    return str(path)


def test_load_supabase_config_handles_missing_or_bad_json(tmp_path):
    assert load_supabase_config(str(tmp_path / "missing.json")) == {}
    bad = tmp_path / "bad.json"
    bad.write_text("{not-json", encoding="utf-8")
    assert load_supabase_config(str(bad)) == {}


def test_registry_disabled_without_credentials_and_returns_empty(tmp_path):
    reg = HopRegistry(config_path=str(tmp_path / "missing.json"))
    assert reg.enabled is False
    assert reg.list_hops() == []
    assert reg.upsert_hops([{"host": "1.2.3.4", "port": 3129}]) is False


def test_list_hops_maps_rows_and_skips_invalid(monkeypatch, tmp_path):
    reg = HopRegistry(config_path=_write_config(tmp_path))
    assert reg.enabled is True

    rows = [
        {
            "id": 7,
            "host": "1.2.3.4",
            "port": 3129,
            "proxy_scheme": "HTTPS",
            "username": "u",
            "password": "p",
            "country": "ID",
        },
        {"id": 8, "host": "", "port": 3129},
        {"id": 9, "host": "5.6.7.8", "port": "bad"},
        {"id": 10, "host": "9.9.9.9", "port": 1080, "proxy_scheme": "socks5"},
    ]
    monkeypatch.setattr(reg, "_rpc", lambda fn, payload: rows)

    hops = reg.list_hops()
    assert [h["host"] for h in hops] == ["1.2.3.4", "9.9.9.9"]
    assert hops[0] == {
        "id": "hop#7",
        "idx": 7,
        "host": "1.2.3.4",
        "port": 3129,
        "username": "u",
        "password": "p",
        "proxy_scheme": "http",
        "country": "ID",
        "source": "supabase",
    }
    assert hops[1]["proxy_scheme"] == "socks5"


def test_list_hops_returns_empty_when_rpc_fails(monkeypatch, tmp_path):
    reg = HopRegistry(config_path=_write_config(tmp_path))
    monkeypatch.setattr(reg, "_rpc", lambda fn, payload: None)
    assert reg.list_hops() == []


def test_upsert_hops_sends_payload(monkeypatch, tmp_path):
    reg = HopRegistry(config_path=_write_config(tmp_path))
    calls = []

    def fake_rpc(fn, payload):
        calls.append((fn, payload))
        return 1

    monkeypatch.setattr(reg, "_rpc", fake_rpc)
    hops = [{"host": "1.2.3.4", "port": 3129, "username": "u", "password": "p"}]

    assert reg.upsert_hops(hops) is True
    assert calls == [("upsert_hop_proxies", {"p_hops": hops})]


def test_upsert_hops_returns_false_when_rpc_fails(monkeypatch, tmp_path):
    reg = HopRegistry(config_path=_write_config(tmp_path))
    monkeypatch.setattr(reg, "_rpc", lambda fn, payload: None)
    assert reg.upsert_hops([{"host": "1.2.3.4", "port": 3129}]) is False


def test_to_hop_rejects_missing_fields():
    assert HopRegistry._to_hop({"host": "", "port": 1}) is None
    assert HopRegistry._to_hop({"host": "1.2.3.4", "port": 0}) is None