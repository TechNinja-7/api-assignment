# Lyftr AI Backend Assignment

A production-style FastAPI service for ingesting WhatsApp-like messages via a secure webhook, storing them in SQLite exactly once, and exposing APIs for listing messages, analytics, health checks, and metrics.

---

## Features

- **POST /webhook**
  - Ingests “WhatsApp-like” messages.
  - Validates HMAC-SHA256 signature from `X-Signature` header using `WEBHOOK_SECRET`.
  - Pydantic validation for:
    - `message_id`: non-empty string.
    - `from`, `to`: E.164-like (`+` followed by digits).
    - `ts`: ISO-8601 UTC (`YYYY-MM-DDTHH:MM:SSZ`).
    - `text`: optional, max length 4096.
  - Idempotent using `message_id` as primary key.
    - First valid request: insert row, return `{"status": "ok"}`.
    - Duplicate `message_id`: no new row, still return `{"status": "ok"}`.

- **GET /messages**
  - Returns stored messages with:
    - `limit` (1–100, default 50).
    - `offset` (>= 0, default 0).
    - `from` filter (exact `from_msisdn`).
    - `since` filter (`ts >= since`).
    - `q` filter (case-insensitive substring in `text`).
  - Deterministic ordering: `ORDER BY ts ASC, message_id ASC`.
  - Response:
    ```json
    {
      "data": [...],
      "total": <matching rows>,
      "limit": <limit>,
      "offset": <offset>
    }
    ```

- **GET /stats**
  - Simple analytics over `messages` table:
    - `total_messages`
    - `senders_count` (distinct `from_msisdn`)
    - `messages_per_sender`: top 10 senders with `{from_msisdn, count}`
    - `first_message_ts` (min `ts`) / `last_message_ts` (max `ts`)

- **Health Probes**
  - `GET /health/live`: returns 200 if process is running.
  - `GET /health/ready`: returns 200 iff:
    - DB reachable (`SELECT 1` ok).
    - `WEBHOOK_SECRET` is set.
  - Otherwise, returns 503.

- **GET /metrics**
  - Exposes Prometheus-style text metrics:
    - `http_requests_total{path,status} N`
    - `webhook_requests_total{result} N`
    - Simple latency metrics with buckets.

- **Structured JSON logs**
  - One JSON line per request.
  - Fields: `ts`, `level`, `request_id`, `method`, `path`, `status`, `latency_ms`.
  - For `/webhook`: extra fields `message_id`, `dup`, `result`.

---

## Tech Stack

- **Framework**: FastAPI
- **Language**: Python 3.11
- **ORM**: SQLAlchemy
- **Validation**: Pydantic
- **Database**: SQLite
- **Containerization**: Docker + Docker Compose

---

## Project Structure

```text
api-assignment/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app, routes, handlers
│   ├── config.py            # Environment config (DATABASE_URL, WEBHOOK_SECRET, LOG_LEVEL)
│   ├── models.py            # SQLAlchemy ORM models (Message)
│   ├── storage.py           # DB engine, session, health check
│   ├── logging_utils.py     # JSON structured logging
│   └── metrics.py           # Simple metrics collector
├── tests/
│   └── __init__.py
├── data/                    # SQLite DB file (when run locally / via Docker)
├── Dockerfile               # Multi-stage Docker build
├── docker-compose.yml       # API service configuration
├── Makefile                 # Convenience commands (optional)
├── requirements.txt         # Python dependencies
└── README.md
