import json
import pytest
from pathlib import Path
from automation.traffic_bot import load_proxies

def test_load_proxies_handles_empty_file(tmp_path):
    empty_file = tmp_path / "proxies.json"
    empty_file.write_text("", encoding="utf-8")
    result = load_proxies(str(empty_file))
    assert isinstance(result, list)
    assert len(result) == 0

def test_load_proxies_handles_malformed_json(tmp_path):
    bad_file = tmp_path / "proxies.json"
    bad_file.write_text("{not valid json", encoding="utf-8")
    result = load_proxies(str(bad_file))
    assert isinstance(result, list)
    assert len(result) == 0

def test_load_proxies_valid(tmp_path):
    valid_file = tmp_path / "proxies.json"
    valid_file.write_text(json.dumps([{"host": "1.2.3.4", "port": 8080}]), encoding="utf-8")
    result = load_proxies(str(valid_file))
    assert len(result) == 1
    assert result[0]["host"] == "1.2.3.4"
