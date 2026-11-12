import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from automation.chain_provider import ChainProxyProvider, parse_hop_file
from automation.proxy_bridge import _split_host_port
from proxy_chain_tester import ChainError


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
