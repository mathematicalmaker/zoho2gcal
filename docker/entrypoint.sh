#!/bin/sh
# If the user passed a command, run z2g with it (one-off: list-zoho-calendars, google-auth --manual, etc.)
if [ $# -gt 0 ]; then
  exec /app/.venv/bin/z2g "$@"
fi

# No args: either run supercronic (cron) or verify and exit
if [ "${Z2G_CRON_ENABLED}" = "1" ] || [ "${Z2G_CRON_ENABLED}" = "true" ] || [ "${Z2G_CRON_ENABLED}" = "yes" ]; then
  DATA_DIR="${DATA_DIR:-/data}"
  CRONTAB="${DATA_DIR}/crontab"
  if [ ! -f "$CRONTAB" ]; then
    cp /app/docker/crontab.example "$CRONTAB"
    echo "z2g: created $CRONTAB from example; edit it to change schedule." >&2
  fi
  exec supercronic "$CRONTAB"
fi

# Default: run verify (checks config + Zoho/Google); exits 0 if OK
exec /app/.venv/bin/z2g verify
