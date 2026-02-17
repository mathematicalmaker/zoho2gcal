#!/bin/sh
DATA_DIR="${DATA_DIR:-/data}"

# Bootstrap DATA_DIR: create .env and secrets/ from examples if missing
# (so Docker users can start without a copy of the repo)
mkdir -p "${DATA_DIR}/secrets"
if [ ! -f "${DATA_DIR}/.env" ]; then
  cp /app/.env.example "${DATA_DIR}/.env"
  echo "z2g: created ${DATA_DIR}/.env from example." >&2
fi
# Always overwrite reference/example files so users get updated docs and env templates on new image versions
# (never overwrite .env or crontab — those are user config)
cp /app/.env.example "${DATA_DIR}/.env.example"
cp /app/secrets/README.md "${DATA_DIR}/secrets/README.md"
cp /app/README.md "${DATA_DIR}/README.md"
cp /app/docker/crontab.example "${DATA_DIR}/crontab.example"

# If the user passed a command, run z2g with it (one-off: list-zoho-calendars, google-auth --manual, etc.)
if [ $# -gt 0 ]; then
  exec /app/.venv/bin/z2g "$@"
fi

# Z2G_SHELL=1: drop into bash and keep container running (for docker exec, setup, debugging)
if [ "${Z2G_SHELL}" = "1" ] || [ "${Z2G_SHELL}" = "true" ] || [ "${Z2G_SHELL}" = "yes" ]; then
  exec bash
fi

# No args: either run supercronic (cron) or verify and exit
if [ "${Z2G_CRON_ENABLED}" = "1" ] || [ "${Z2G_CRON_ENABLED}" = "true" ] || [ "${Z2G_CRON_ENABLED}" = "yes" ]; then
  CRONTAB="${DATA_DIR}/crontab"
  if [ ! -f "$CRONTAB" ]; then
    cp /app/docker/crontab.example "$CRONTAB"
    echo "z2g: created $CRONTAB from example; edit it to change schedule." >&2
  fi
  exec supercronic "$CRONTAB"
fi

# Default: run verify (checks config + Zoho/Google); exits 0 if OK
exec /app/.venv/bin/z2g verify
