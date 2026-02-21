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
if [ ! -f "${DATA_DIR}/crontab" ]; then
  cp /app/docker/crontab.example "${DATA_DIR}/crontab"
  echo "z2g: created ${DATA_DIR}/crontab from example; edit it to change schedule." >&2
fi

# If the user passed a command, run z2g with it (one-off: list-zoho-calendars, google-auth --manual, etc.)
if [ $# -gt 0 ]; then
  exec /app/.venv/bin/z2g "$@"
fi

# No args: run supercronic (cron), or keep shell alive, or verify and exit
# Z2G_CRON_ENABLED and Z2G_SHELL are independent: if both set, cron runs (container stays up so you can exec in)
if [ "${Z2G_CRON_ENABLED}" = "1" ] || [ "${Z2G_CRON_ENABLED}" = "true" ] || [ "${Z2G_CRON_ENABLED}" = "yes" ]; then
  exec supercronic -json "${DATA_DIR}/crontab"
fi
# Z2G_SHELL=1: keep container running (for docker exec, setup, debugging) when cron is not enabled
if [ "${Z2G_SHELL}" = "1" ] || [ "${Z2G_SHELL}" = "true" ] || [ "${Z2G_SHELL}" = "yes" ]; then
  exec sleep infinity
fi

# Default: run verify (checks config + Zoho/Google); exits 0 if OK
exec /app/.venv/bin/z2g verify
