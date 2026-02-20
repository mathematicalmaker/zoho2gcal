#!/usr/bin/env python3
"""Sync .env from .env.example: keep structure and comments from the example, use values from .env.

Run from project root:
  uv run python scripts/sync_env.py
  # or: python scripts/sync_env.py

In Docker, .env lives under DATA_DIR (e.g. /data). The script uses DATA_DIR when set so it works
when run inside the container (e.g. docker exec z2g python /app/scripts/sync_env.py).

Reads .env.example line-by-line (preserving order, comments, blank lines). For each KEY=VALUE
line, outputs KEY=<value from .env if present, else example value>, preserving any trailing
inline comment. If .env does not exist, creates it from .env.example (all example values).
"""

import os
from pathlib import Path


def _parse_env_file(path: Path) -> dict[str, str]:
    """Parse KEY=VALUE from a .env file; first occurrence wins. No expansion or quotes."""
    out: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if "=" not in line or line.strip().startswith("#"):
            continue
        key, _, rest = line.partition("=")
        key = key.strip()
        if not key:
            continue
        # Value is the rest of the line; strip so we don't keep leading space
        value = rest.strip()
        # If value has trailing inline comment ( # ...), take only the value part for storage
        if " #" in value:
            value = value.split(" #", 1)[0].strip()
        if key not in out:
            out[key] = value
    return out


def _parse_example_line(line: str) -> tuple[str, str, str] | None:
    """If line is KEY=VALUE (optional trailing # comment), return (key, example_value, trailing). Else None."""
    if "=" not in line or line.strip().startswith("#"):
        return None
    key, _, rest = line.partition("=")
    key = key.strip()
    if not key:
        return None
    # rest is value + optional " # comment"
    rest_stripped = rest.strip()
    if " #" in rest_stripped:
        example_value = rest_stripped.split(" #", 1)[0].strip()
        trailing = " #" + rest_stripped.split(" #", 1)[1]
    else:
        example_value = rest_stripped
        trailing = ""
    return (key, example_value, trailing)


def sync_env(example_path: Path, env_path: Path) -> None:
    """Write env_path using example_path structure and comments; values from env_path if it exists."""
    current = _parse_env_file(env_path) if env_path.exists() else {}
    example_lines = example_path.read_text().splitlines()
    output: list[str] = []
    for line in example_lines:
        parsed = _parse_example_line(line)
        if parsed is None:
            # Comment, blank, or not KEY=VALUE: keep line as-is
            output.append(line)
            continue
        key, example_value, trailing = parsed
        value = current.get(key, example_value)
        output.append(f"{key}={value}{trailing}")
    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text("\n".join(output) + "\n")
    print(f"Wrote {env_path} (structure from {example_path}, values from existing .env or example)")


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    example_path = root / ".env.example"
    data_dir = Path(os.environ.get("DATA_DIR", str(root)))
    env_path = data_dir / ".env"
    if not example_path.exists():
        raise SystemExit(f".env.example not found at {example_path}")
    sync_env(example_path, env_path)


if __name__ == "__main__":
    main()
