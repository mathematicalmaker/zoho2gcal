#!/usr/bin/env python3
"""Sync .env from .env.example: keep structure and comments from the example, use values from .env.

Output conforms to .env.example (order, comments, blank lines). Values come from your existing
.env when the key exists there; otherwise the example value is used. Comments or keys that exist
only in .env (and not in .env.example) are not preserved—they will be removed.

Run from project root:
  uv run python scripts/sync_env.py
  # or: python scripts/sync_env.py

In Docker, .env lives under DATA_DIR (e.g. /data). The script uses DATA_DIR when set so it works
when run inside the container (e.g. docker exec z2g python /app/scripts/sync_env.py).
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


def _parse_example_line(line: str) -> tuple[str, str, str, bool] | None:
    """If line is KEY=VALUE or # KEY=VALUE, return (key, example_value, trailing, commented).
    commented=True means the line was commented in the example (optional var). Else None."""
    stripped = line.strip()
    commented = stripped.startswith("#")
    if commented:
        # Optional var: "# KEY=value" or "#KEY=value"
        rest = stripped.lstrip("#").strip()
        if "=" not in rest:
            return None
        key, _, value_part = rest.partition("=")
        key = key.strip()
        if not key:
            return None
        value_part = value_part.strip()
        if " #" in value_part:
            example_value = value_part.split(" #", 1)[0].strip()
            trailing = " #" + value_part.split(" #", 1)[1]
        else:
            example_value = value_part
            trailing = ""
        return (key, example_value, trailing, True)
    if "=" not in line:
        return None
    key, _, rest = line.partition("=")
    key = key.strip()
    if not key:
        return None
    rest_stripped = rest.strip()
    if " #" in rest_stripped:
        example_value = rest_stripped.split(" #", 1)[0].strip()
        trailing = " #" + rest_stripped.split(" #", 1)[1]
    else:
        example_value = rest_stripped
        trailing = ""
    return (key, example_value, trailing, False)


def sync_env(example_path: Path, env_path: Path) -> None:
    """Write env_path using example_path structure and comments; values from env_path if it exists."""
    current = _parse_env_file(env_path) if env_path.exists() else {}
    example_lines = example_path.read_text().splitlines()
    output: list[str] = []
    for line in example_lines:
        parsed = _parse_example_line(line)
        if parsed is None:
            # Blank or non-assignment comment: keep line as-is
            output.append(line)
            continue
        key, example_value, trailing, was_commented = parsed
        if key in current:
            # User has this var: output uncommented so it takes effect
            output.append(f"{key}={current[key]}{trailing}")
        elif was_commented:
            # Optional var, user didn't set it: keep commented line as-is
            output.append(line)
        else:
            output.append(f"{key}={example_value}{trailing}")
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
