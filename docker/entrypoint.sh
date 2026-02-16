#!/bin/sh
DATA_DIR="${DATA_DIR:-/data}"

# Bootstrap DATA_DIR: create .env, secrets/, and private.env from examples if missing
# (so Docker users can start without a copy of the repo)
mkdir -p "${DATA_DIR}/secrets"
if [ ! -f "${DATA_DIR}/.env" ]; then
  cp /app/.env.example "${DATA_DIR}/.env"
  echo "z2g: created ${DATA_DIR}/.env from example." >&2
fi
if [ ! -f "${DATA_DIR}/secrets/private.env" ]; then
  cp /app/secrets/private.env.example "${DATA_DIR}/secrets/private.env"
  echo "z2g: created ${DATA_DIR}/secrets/private.env from example." >&2
fi
# Copy example files for reference (only if not already present)
if [ ! -f "${DATA_DIR}/.env.example" ]; then
  cp /app/.env.example "${DATA_DIR}/.env.example"
fi
if [ ! -f "${DATA_DIR}/secrets/private.env.example" ]; then
  cp /app/secrets/private.env.example "${DATA_DIR}/secrets/private.env.example"
fi
if [ ! -f "${DATA_DIR}/secrets/README.md" ]; then
  cp /app/secrets/README.md "${DATA_DIR}/secrets/README.md"
fi
if [ ! -f "${DATA_DIR}/README.md" ]; then
  cp /app/README.md "${DATA_DIR}/README.md"
fi
if [ ! -f "${DATA_DIR}/crontab.example" ]; then
  cp /app/docker/crontab.example "${DATA_DIR}/crontab.example"
fi

# If the user passed a command, run z2g with it (one-off: list-zoho-calendars, google-auth --manual, etc.)
if [ $# -gt 0 ]; then
  exec /app/.venv/bin/z2g "$@"
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
