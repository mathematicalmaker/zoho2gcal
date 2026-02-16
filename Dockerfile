# z2g: one-way Zoho Calendar → Google Calendar sync (Docker + supercronic)
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
  && rm -rf /var/lib/apt/lists/*

# Install supercronic (cron for containers)
# https://github.com/aptible/supercronic/releases
ENV SUPERCRONIC_URL=https://github.com/aptible/supercronic/releases/download/v0.2.43/supercronic-linux-amd64 \
  SUPERCRONIC_SHA1SUM=f97b92132b61a8f827c3faf67106dc0e4467ccf2 \
  SUPERCRONIC=supercronic-linux-amd64
RUN curl -fsSLO "$SUPERCRONIC_URL" \
  && echo "${SUPERCRONIC_SHA1SUM} ${SUPERCRONIC}" | sha1sum -c - \
  && chmod +x "$SUPERCRONIC" \
  && mv "$SUPERCRONIC" "/usr/local/bin/${SUPERCRONIC}" \
  && ln -s "/usr/local/bin/${SUPERCRONIC}" /usr/local/bin/supercronic

WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY src ./src
ENV UV_NO_DEV=1
RUN uv sync --frozen --no-dev

# Docker assets and config templates (for bootstrap when DATA_DIR is empty)
COPY .env.example /app/.env.example
COPY secrets/private.env.example secrets/README.md /app/secrets/
COPY docker/crontab.example docker/entrypoint.sh /app/docker/
RUN chmod +x /app/docker/entrypoint.sh

ENV DATA_DIR=/data
ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD []
