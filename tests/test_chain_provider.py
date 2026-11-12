import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from automation.chain_provider import ChainProxyProvider, parse_hop_file
from automation.proxy_bridge import _split_host_port
from proxy_chain_tester import ChainError


@pytest.fixture(autouse=True)
def _no_supabase(monkeypatch):
    """Default: Supabase kosong supaya test memakai file fallback."""
    monkeypatch.setattr(
        "automation.chain_provider.list_hops_from_supabase", lambda: []
    )


def test_parse_hop_file_supports_scheme_and_bare_credentials(tmp_path):
    path = tmp_path / "hops.txt"
    path.write_text(
        "\n".join(
            [
                "http://user:pass@1.2.3.4:3129",
                "5.6.7.8:3129",
                "# komentar",
                "baris-rusak",
            ]
        ),
        encoding="utf-8",
    )

    hops = parse_hop_file(str(path))
    assert len(hops) == 2
    assert hops[0]["host"] == "1.2.3.4"
    assert hops[0]["username"] == "user"
    assert hops[0]["password"] == "pass"
    assert hops[0]["proxy_scheme"] == "http"
    assert hops[1]["host"] == "5.6.7.8"
    assert hops[1]["username"] == ""
    assert hops[1]["port"] == 3129


def test_provider_picks_unique_random_hops_and_recovers_from_blacklist(tmp_path):
    path = tmp_path / "hops.txt"
    path.write_text(
        "\n".join(f"user:pass@10.0.0.{i}:3129" for i in range(1, 6)),
        encoding="utf-8",
    )
    provider = ChainProxyProvider(scrape_file=str(path), hop_tries=2)

    first = provider._pick_hops(2)
    assert len(first) == 2
    assert len({hop["host"] for hop in first}) == 2

    for hop in first:
        provider._blacklist_hop(hop)
    fallback = provider._pick_hops(2)
    assert len(fallback) == 2


def test_split_host_port_variants():
    assert _split_host_port("example.com:8080") == ("example.com", 8080)
    assert _split_host_port("example.com") == ("example.com", 80)
    assert _split_host_port("[2001:db8::1]:443") == ("2001:db8::1", 443)
    assert _split_host_port("203.0.113.9:3129") == ("203.0.113.9", 3129)


def test_chain_error_carries_stage_and_proxy_index():
    exc = ChainError("tidak bisa connect", status=407, stage="proxy_connect", proxy_index=12)
    assert exc.status == 407
    assert exc.stage == "proxy_connect"
    assert exc.proxy_index == 12


def test_probe_parses_asn_isp_and_org(monkeypatch, tmp_path):
    path = tmp_path / "hops.txt"
    path.write_text("user:pass@10.0.0.1:3129\n", encoding="utf-8")
    provider = ChainProxyProvider(scrape_file=str(path))

    body = (
        '{"query":"90.214.34.176","country":"United Kingdom",'
        '"countryCode":"GB","isp":"Sky UK Limited","org":"Sky Broadband",'
        '"as":"AS5607 Sky UK Limited"}'
    )

    def fake_fetch(chain, target, timeout=None, verbose=False):
        return {
            "body": body,
            "exit_ip": "90.214.34.176",
            "latency_ms": 42,
        }

    monkeypatch.setattr(
        "automation.chain_provider.fetch_through_chain", fake_fetch
    )

    result = provider._probe([{"idx": 1}])

    assert result["exit_ip"] == "90.214.34.176"
    assert result["asn"] == "AS5607 Sky UK Limited"
    assert result["isp"] == "Sky UK Limited"
    assert result["org"] == "Sky Broadband"
    assert result["country_code"] == "GB"


def test_provider_prefers_supabase_hops(monkeypatch, tmp_path):
    db_hops = [
        {
            "id": "hop#1",
            "idx": 1,
            "host": "10.9.9.9",
            "port": 3129,
            "username": "u",
            "password": "p",
            "proxy_scheme": "http",
            "source": "supabase",
        }
    ]
    monkeypatch.setattr(
        "automation.chain_provider.list_hops_from_supabase", lambda: db_hops
    )
    path = tmp_path / "hops.txt"
    path.write_text("user:pass@10.0.0.1:3129\n", encoding="utf-8")

    provider = ChainProxyProvider(scrape_file=str(path))

    assert provider.hops == db_hops


def test_provider_falls_back_to_file_when_supabase_fails(monkeypatch, tmp_path):
    def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr("automation.chain_provider.list_hops_from_supabase", boom)
    path = tmp_path / "hops.txt"
    path.write_text("user:pass@10.0.0.1:3129\n", encoding="utf-8")

    provider = ChainProxyProvider(scrape_file=str(path))

    assert len(provider.hops) == 1
    assert provider.hops[0]["host"] == "10.0.0.1"
    assert provider.hops[0]["source"] == "scrape"


def test_provider_raises_when_both_sources_empty(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "automation.chain_provider.list_hops_from_supabase", lambda: []
    )
    path = tmp_path / "hops.txt"
    path.write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="hop_proxy_list"):
        ChainProxyProvider(scrape_file=str(path))


def test_provider_defaults_keep_gologin_channel(tmp_path):
    from core.proxy_manager import CHANNEL_GOLOGIN

    path = tmp_path / "hops.txt"
    path.write_text("user:pass@10.0.0.1:3129\n", encoding="utf-8")
    provider = ChainProxyProvider(scrape_file=str(path))

    assert provider.target == "gologin"
    assert provider.channel == CHANNEL_GOLOGIN
    assert provider.strict_channel is True


def test_provider_accepts_monetag_target_and_automation_channel(tmp_path):
    from core.proxy_manager import CHANNEL_AUTOMATION

    path = tmp_path / "hops.txt"
    path.write_text("user:pass@10.0.0.1:3129\n", encoding="utf-8")
    provider = ChainProxyProvider(
        scrape_file=str(path),
        target="monetag",
        channel=CHANNEL_AUTOMATION,
        strict_channel=False,
        target_max_uses_per_day=5,
        target_cooldown_seconds=3600,
    )

    assert provider.target == "monetag"
    assert provider.channel == CHANNEL_AUTOMATION
    assert provider.strict_channel is False
    assert provider.target_max_uses_per_day == 5
    assert provider.target_cooldown_seconds == 3600


def test_provider_rejects_non_floppydata_residential(tmp_path):
    path = tmp_path / "hops.txt"
    path.write_text("user:pass@10.0.0.1:3129\n", encoding="utf-8")

    class FakePM:
        def __init__(self):
            self.released = []

        def acquire_proxy(self, **kwargs):
            return {"id": 1, "host": "geo.other.com", "port": 10080, "leased_by": "lease-1"}

        def release_proxy(self, proxy, caller_id=None, **kwargs):
            self.released.append((proxy.get("id"), caller_id))

    pm = FakePM()
    provider = ChainProxyProvider(
        scrape_file=str(path),
        target="monetag",
        channel="automation",
        strict_channel=False,
        residential_host_contains="floppydata",
        proxy_manager=pm,
    )

    assert provider.next_proxy() is None
    assert pm.released == [(1, "lease-1")]
