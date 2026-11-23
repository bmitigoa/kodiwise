"""Step 8: the README's limits and thresholds are the config module's, byte for byte."""
import re
from pathlib import Path

import pytest

from agent.core import config

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text(encoding="utf-8").replace("\r\n", "\n")


def readme_block() -> str:
    m = re.search(r"<!-- limits:start -->\n(.*?)\n<!-- limits:end -->", README, re.S)
    assert m, "README.md lost its limits markers"
    return m.group(1)


def test_readme_limits_table_is_generated_from_the_config_module():
    assert readme_block() == config.table(), "run: python -m agent.core.config and paste it between the markers"


def test_every_limit_is_documented_once_with_its_env_override():
    names = [l.name for l in config.LIMITS]
    assert len(names) == len(set(names))
    block = readme_block()
    for l in config.LIMITS:
        assert f"`{l.name}`" in block and f"`{l.env}`" in block


def test_readme_prose_numbers_match_the_config_and_the_deploy_script():
    assert f"{config.CHAT_USER_DAILY} messages per user per day" in README
    caps = set(re.findall(r"-DailyCap (\d+)", README))
    rpms = set(re.findall(r"-Rpm (\d+)", README))
    assert len(caps) == 1 and len(rpms) == 1, "every deploy example in the README must use the same caps"
    cap, rpm = caps.pop(), rpms.pop()
    assert f"{cap} Gemini requests per model per day" in README
    assert f"{rpm} requests per minute" in README
    deploy = (ROOT / "infra" / "deploy_chat.ps1").read_text(encoding="utf-8")
    assert "--max-instances=1" in deploy and "CHAT_MAX_INSTANCES=1" in deploy
    assert f"$UserDaily = {config.CHAT_USER_DAILY}" in deploy
    assert "-DailyCap" in deploy and "-Rpm" in deploy


def test_defaults_are_inside_their_own_bounds():
    for l in config.LIMITS:
        assert l.lo <= l.default <= l.hi, l.name


def test_environment_overrides_apply_and_bad_ones_are_ignored(monkeypatch):
    monkeypatch.setenv("KW_MAX_TOOL_CALLS", "3")
    monkeypatch.setenv("KW_MAX_KM", "not a number")
    monkeypatch.setenv("KW_MAX_BEDROOMS", "999")           # above its hard bound
    monkeypatch.setenv("CHAT_USER_DAILY", "20")
    import importlib
    importlib.reload(config)
    try:
        assert config.MAX_TOOL_CALLS == 3 and config.CHAT_USER_DAILY == 20
        assert config.MAX_KM == 50.0 and config.MAX_BEDROOMS == 10
    finally:
        for k in ("KW_MAX_TOOL_CALLS", "KW_MAX_KM", "KW_MAX_BEDROOMS", "CHAT_USER_DAILY"):
            monkeypatch.delenv(k, raising=False)
        importlib.reload(config)


def test_the_code_uses_the_config_values_not_its_own_copies():
    from agent.core import tools, validate
    from chat import engine, guard, pii
    assert tools.MAX_PREDICTIONS == config.MAX_PREDICTIONS and tools.DEFAULT_MAX_KM == config.DEFAULT_MAX_KM
    assert validate.MAX_RENT == config.MAX_RENT and validate.MAX_BEDROOMS == config.MAX_BEDROOMS
    assert engine.MAX_TOOL_CALLS == config.MAX_TOOL_CALLS and engine.MAX_HISTORY == config.MAX_HISTORY
    assert guard.MIN_CHECKED == config.MIN_CHECKED_AMOUNT and pii.MAX_MESSAGE_CHARS == config.MAX_MESSAGE_CHARS


def test_no_secret_looking_value_in_config():
    text = (ROOT / "agent" / "core" / "config.py").read_text(encoding="utf-8")
    assert not re.search(r"AIza[0-9A-Za-z_-]{20,}|-----BEGIN|sk-[A-Za-z0-9]{20,}", text)
