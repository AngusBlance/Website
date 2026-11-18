# computermath

Source for [www.computermath.org](https://www.computermath.org): a FastAPI site backed by Postgres and PostgREST, run with Docker Compose.

Both setups need a `.env` in the repo root with `DB_HOST=db`, `DB_PORT`, `DB_USER`, `DB_PASSWORD` and `DB_NAME`.

## Production

```bash
docker compose up -d --build
```

The site listens on `127.0.0.1:8000`, where the Cloudflare tunnel picks it up. Postgres and PostgREST are only reachable inside the Compose network, and every container restarts automatically after a reboot.

## Development

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

Mounts the repo into the container and reloads on code changes. Postgres is exposed on `localhost:5432` and PostgREST on `localhost:3000`.

## Request logging

Every request is logged to `raw.fast_api_requests` by `website/server/request_log.py`:
the full request (URL, headers, raw headers, body, client, ASGI scope), the matched route,
and the response (status code, headers, size, content type), plus timings (time to headers,
total duration). Logging happens **after** the response is sent, in the background, so pages
never wait for it, and a logging failure never breaks a page.

Privacy: secret headers (cookies, `Authorization`, tokens, ...) are stored as `[redacted]`
(names kept); request bodies over 4 KB keep only their size and content type.

The app adds any missing columns to the table on start, so existing databases upgrade themselves.

```bash
uv run pytest      # request logging tests (no database needed)
```
