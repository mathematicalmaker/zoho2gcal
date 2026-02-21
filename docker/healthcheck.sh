#!/bin/sh
# Healthcheck for z2g container (cron mode)
# Checks .z2g-alert-state.json for last_status and recency
# Returns 0 (healthy) if sync is succeeding and recent

STATE_FILE="${DATA_DIR:-/data}/.z2g-alert-state.json"
MAX_AGE_MINUTES="${Z2G_HEALTH_MAX_AGE_MINUTES:-35}"

if [ ! -f "$STATE_FILE" ]; then
  echo "Healthcheck: state file not found (container may be starting or cron not run yet)"
  exit 1
fi

# Parse last_status and last_run from JSON
# Use python3 (available in python3.12-bookworm-slim base image)
command -v python3 >/dev/null 2>&1 || { echo "Healthcheck: python3 not found" >&2; exit 1; }
python3 -c "
import json
import sys
from datetime import datetime, timezone

max_age_min = int('${MAX_AGE_MINUTES}')

with open('${STATE_FILE}') as f:
    state = json.load(f)

last_status = state.get('last_status', 'unknown')
last_run = state.get('last_run')

if last_status != 'ok':
    print(f'Healthcheck: last_status={last_status}', file=sys.stderr)
    sys.exit(1)

if not last_run:
    print('Healthcheck: no last_run timestamp', file=sys.stderr)
    sys.exit(1)

try:
    run_dt = datetime.fromisoformat(last_run.replace('Z', '+00:00'))
    age_minutes = (datetime.now(timezone.utc) - run_dt).total_seconds() / 60
    if age_minutes > max_age_min:
        print(f'Healthcheck: last run {age_minutes:.0f}m ago (max {max_age_min}m)', file=sys.stderr)
        sys.exit(1)
except Exception as e:
    print(f'Healthcheck: error parsing timestamp: {e}', file=sys.stderr)
    sys.exit(1)

print(f'Healthcheck: OK (last run {age_minutes:.0f}m ago)')
sys.exit(0)
"
