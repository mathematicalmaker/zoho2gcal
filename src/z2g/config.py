"""Environment and path configuration.

Loads .env (or .env.example), then secrets/private.env if present.
Resolves relative paths from project root.

If DATA_DIR or Z2G_DATA_DIR is set, that path is used as project root (for Docker).
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import find_dotenv, load_dotenv


def _truthy(v: str | None) -> bool:
    return (v or "").strip().lower() in {"1", "true", "yes", "on"}


# Project root: DATA_DIR / Z2G_DATA_DIR (Docker) or discover via .env
_data_dir = os.environ.get("DATA_DIR") or os.environ.get("Z2G_DATA_DIR")
if _data_dir:
    PROJECT_ROOT = Path(_data_dir).resolve()
    _env_file = PROJECT_ROOT / ".env"
    if not _env_file.exists():
        _env_file = PROJECT_ROOT / ".env.example" if (PROJECT_ROOT / ".env.example").exists() else None
    _env_path = str(_env_file) if _env_file and _env_file.exists() else None
else:
    _env_path = find_dotenv(".env", usecwd=True)
    if not _env_path:
        _env_path = find_dotenv(".env.example", usecwd=True)
    PROJECT_ROOT = Path(_env_path).resolve().parent if _env_path else Path.cwd()

# Load base env
if _env_path:
    load_dotenv(_env_path)

# Auto-load secrets/private.env if it exists (overrides base)
_private_env = PROJECT_ROOT / "secrets" / "private.env"
if _private_env.exists():
    load_dotenv(_private_env, override=True)


def resolve_path(p: str) -> str:
    """
    Resolve a filesystem path from an env string.
    - If absolute: return as-is
    - If relative: resolve relative to PROJECT_ROOT
    """
    path = Path(p)
    return str(path if path.is_absolute() else (PROJECT_ROOT / path).resolve())


def verbose_enabled() -> bool:
    return _truthy(os.environ.get("Z2G_VERBOSE"))


def env(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        raise RuntimeError(f"Missing env var: {name}")
    return v

