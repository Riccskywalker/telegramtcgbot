import pytest
from tcgbot.core.config import load_core_config
from tcgbot.telegram.config import load_config


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    for key in ('PTCG_API_KEY', 'PTCG_API_BASE', 'TELEGRAM_BOT_TOKEN', 'BOT_LANG', 'ADMIN_CHAT_ID'):
        monkeypatch.delenv(key, raising=False)
    return monkeypatch


def test_missing_key_exits_with_signup_url(env):
    with pytest.raises(RuntimeError, match='https://pokemontcgapi.com/free-api-key'):
        load_config()


def test_missing_telegram_token(env):
    env.setenv('PTCG_API_KEY', 'test')
    with pytest.raises(RuntimeError, match='TELEGRAM_BOT_TOKEN'):
        load_config()


def test_env_defaults_and_no_secrets_in_repr(env):
    env.setenv('PTCG_API_KEY', 'private-key')
    env.setenv('TELEGRAM_BOT_TOKEN', 'private-token')
    cfg = load_config()
    assert cfg.core.api_base == 'https://api.pokemontcgapi.com/v1'
    assert cfg.bot_lang == 'en' and cfg.admin_chat_id is None
    assert 'private-key' not in repr(cfg) and 'private-token' not in repr(cfg)


def test_optional_admin_and_base(env):
    env.setenv('PTCG_API_KEY', 'test')
    env.setenv('TELEGRAM_BOT_TOKEN', 'test')
    env.setenv('ADMIN_CHAT_ID', '123')
    env.setenv('PTCG_API_BASE', 'http://localhost:8080/v1/')
    assert load_config().admin_chat_id == 123
    assert load_core_config().api_base == 'http://localhost:8080/v1'


@pytest.mark.parametrize('admin', ['invalid', '-123', '0'])
def test_invalid_admin_rejected(env, admin):
    env.setenv('PTCG_API_KEY', 'test')
    env.setenv('TELEGRAM_BOT_TOKEN', 'test')
    env.setenv('ADMIN_CHAT_ID', admin)
    with pytest.raises(RuntimeError, match='ADMIN_CHAT_ID'):
        load_config()


def test_entrypoint_fails_before_network_when_key_missing(env):
    import os
    import subprocess
    import sys
    from pathlib import Path
    # Run the actual module with a fresh empty working directory and no credentials.
    proc_env = {'PATH': os.environ.get('PATH', ''), 'PYTHONPATH': str(Path(__file__).resolve().parents[1])}
    result = subprocess.run([sys.executable, '-m', 'tcgbot'], env=proc_env,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    assert 'PTCG_API_KEY is required' in result.stderr
    assert 'https://pokemontcgapi.com/free-api-key' in result.stderr
    assert 'Traceback' not in result.stderr
