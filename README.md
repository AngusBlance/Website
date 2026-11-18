# computermath

Source for [www.computermath.org](https://www.computermath.org): a FastAPI site that keeps its data in one
SQLite file, run with Docker Compose.

## Production

```bash
mkdir -p data              # or set DATA_DIR in .env to another folder; create it before starting
docker compose up -d --build
```

The site listens on `127.0.0.1:8000`, where the Cloudflare tunnel picks it up, and restarts automatically
after a reboot. It runs as uid/gid `1000` (override with `UID`/`GID` in `.env`), so `data/website.db`
belongs to the host user, and the database platform's Airflow, running as the same user, can read and
update it.

## Development

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

Mounts the repo into the container and reloads on code changes. The database is `./data/website.db`.

## Data: SQLite + the lakehouse

```
website ──logs every request──▶ fast_api_requests ──daily──▶ lakehouse raw ▶ bronze ▶ silver ▶ gold
   ▲                                   │                                                     │
   └──── /api/visitors ◀── visitors (view) ◀──────────── gold_visitors ◀──── daily copy ─────┘
```

`website/server/store.py` owns the schema:

- `fast_api_requests`: every request (see below). Ids continue from the old Postgres table
  (`req_00010001` onwards), so they never clash in the lakehouse.
- `gold_visitors`: a copy of the lakehouse table `website.gold.visitors`, plus `sync_state.gold_through_id`,
  the newest request it includes.
- `visitors` (view): `gold_visitors` + requests to the Server Logging page newer than `gold_through_id`,
  merged per pseudonymous visitor (hashed IP, the same hash the lakehouse uses). The page's
  table and map read it through `/api/visitors`.

The database platform's nightly chain (`raw_daily` → … → `publish_daily`, in `database-projects`) copies new rows to
raw storage, rebuilds bronze → silver → gold, replaces `gold_visitors`, and deletes requests that gold
includes **and** that are older than 2 days. The view is correct at every moment, even mid-sync: nothing is
counted twice or missed.

Until 2026-11-18 the site logged to Postgres (exposed to the lakehouse through PostgREST). All of
those rows are in the lakehouse's raw storage and bronze.

## Request logging

Every request is logged to `fast_api_requests` by `website/server/request_log.py`:
the full request (URL, headers, raw headers, body, client, ASGI scope), the matched route,
and the response (status code, headers, size, content type), plus timings (time to headers,
total duration). Logging happens **after** the response is sent, in the background, so pages
never wait for it, and a logging failure never breaks a page.

Privacy: secret headers (cookies, `Authorization`, tokens, ...) are stored as `[redacted]`
(names kept); request bodies over 4 KB keep only their size and content type.

```bash
uv run pytest      # request logging + SQLite store tests (temporary database files)
```
