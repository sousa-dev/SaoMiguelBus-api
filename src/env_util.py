"""Load src/src/.env for scripts that run outside Django (e.g. run.py)."""

from __future__ import annotations

from pathlib import Path

from decouple import Config, RepositoryEnv, config as auto_config

_ENV_FILE = Path(__file__).resolve().parent / 'src' / '.env'


def get_config() -> Config:
    if _ENV_FILE.is_file():
        return Config(RepositoryEnv(str(_ENV_FILE)))
    return auto_config


def web_bind_address() -> str:
    cfg = get_config()
    host = cfg('WEB_HOST', default='127.0.0.1')
    port = cfg('WEB_PORT', default='8000')
    return f'{host}:{port}'
