# app/main.py
import hmac
import hashlib
import uuid
import time
import re
from datetime import datetime
from typing import Optional, List

from fastapi import FastAPI, Depends, status, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator
from sqlalchemy.orm import Session
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.storage import init_db, get_db, db_health_check
from app.models import Message
from app.logging_utils import log_request, get_logger
from app.metrics import metrics

app = FastAPI(
    title="Lyftr AI Backend Assignment",
    version="1.0.0",
)

logger = get_logger(__name__)


# ==================== Startup ====================

@app.on_event("startup")
def on_startup() -> None:
    """Initialize database on app startup."""
    init_db()
    logger.info("Database initialized")


# ==================== Pydantic Models ====================

class MessageRequest(BaseModel):
    message_id: str
    from_field: str = Field(..., alias="from")
    to: str
    ts: str
    text: Optional[str] = None

    @validator("message_id")
    def message_id_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("message_id must not be empty")
        return v

    @validator("from_field")
    def from_is_e164(cls, v: str) -> str:
        if not re.match(r"^\+\d+$", v):
            raise ValueError("from must be in E.164 format (e.g. +919876543210)")
        return v

    @validator("to")
    def to_is_e164(cls, v: str) -> str:
        if not re.match(r"^\+\d+$", v):
            raise ValueError("to must be in E.164 format (e.g. +14155550100)")
        return v

    @validator("ts")
    def ts_is_iso8601_utc(cls, v: str) -> str:
        if not re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", v):
            raise ValueError("ts must be ISO-8601 UTC (e.g. 2025-01-15T10:00:00Z)")
        return v

    @validator("text")
    def text_max_length(cls, v: Optional[str]) -> Optional[str]:
        if v and len(v) > 4096:
            raise ValueError("text must not exceed 4096 characters")
        return v

    class Config:
        populate_by_name = True


class MessageResponse(BaseModel):
    message_id: str
    from_msisdn: str
    to_msisdn: str
    ts: str
    text: Optional[str] = None

    class Config:
        from_attributes = True


class MessagesListResponse(BaseModel):
    data: List[MessageResponse]
    total: int
    limit: int
    offset: int


class SenderStat(BaseModel):
    from_msisdn: str
    count: int


class StatsResponse(BaseModel):
    total_messages: int
    senders_count: int
    messages_per_sender: List[SenderStat]
    first_message_ts: Optional[str] = None
    last_message_ts: Optional[str] = None


# ==================== Health Endpoints ====================

@app.get("/health/live")
def health_live() -> dict:
    """Liveness probe: app is running."""
    return {"status": "live"}


@app.get("/health/ready")
def health_ready(db: Session = Depends(get_db)):
    """
    Readiness probe: DB is reachable and WEBHOOK_SECRET is set.
    Returns 503 if either check fails.
    """
    settings = get_settings()

    if not settings.WEBHOOK_SECRET:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": "WEBHOOK_SECRET not set"},
        )

    if not db_health_check(db):
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": "database not ready"},
        )

    return {"status": "ready"}


# ==================== Webhook Endpoint ====================

@app.post("/webhook")
async def webhook(request: Request, db: Session = Depends(get_db)):
    """
    Ingest WhatsApp-like messages with HMAC signature validation.
    Enforces idempotency via message_id uniqueness.
    """
    request_id = str(uuid.uuid4())
    start_time = time.time()
    settings = get_settings()

    # 1. Read raw body for HMAC
    try:
        raw_body = await request.body()
    except Exception:
        latency_ms = (time.time() - start_time) * 1000
        metrics.record_http_request("/webhook", 400)
        log_request(request_id, "POST", "/webhook", 400, latency_ms, extra={"result": "error", "reason": "read_body"})
        return JSONResponse(status_code=400, content={"detail": "Could not read request body"})

    # 2. Validate signature
    x_signature = request.headers.get("X-Signature")
    if not x_signature:
        latency_ms = (time.time() - start_time) * 1000
        metrics.record_http_request("/webhook", 401)
        metrics.record_webhook_result("invalid_signature")
        metrics.record_latency(latency_ms)
        log_request(request_id, "POST", "/webhook", 401, latency_ms, extra={"result": "invalid_signature"})
        return JSONResponse(status_code=401, content={"detail": "invalid signature"})

    expected = hmac.new(
        settings.WEBHOOK_SECRET.encode(),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(x_signature, expected):
        latency_ms = (time.time() - start_time) * 1000
        metrics.record_http_request("/webhook", 401)
        metrics.record_webhook_result("invalid_signature")
        metrics.record_latency(latency_ms)
        log_request(request_id, "POST", "/webhook", 401, latency_ms, extra={"result": "invalid_signature"})
        return JSONResponse(status_code=401, content={"detail": "invalid signature"})

    # 3. Parse JSON and validate
    try:
        data = await request.json()
        msg = MessageRequest(**data)
    except Exception as e:
        latency_ms = (time.time() - start_time) * 1000
        metrics.record_http_request("/webhook", 422)
        metrics.record_webhook_result("validation_error")
        metrics.record_latency(latency_ms)
        log_request(
            request_id,
            "POST",
            "/webhook",
            422,
            latency_ms,
            extra={"result": "validation_error", "error": str(e)},
        )
        return JSONResponse(status_code=422, content={"detail": str(e)})

    # 4. Insert into DB with idempotency
    try:
        new_msg = Message(
            message_id=msg.message_id,
            from_msisdn=msg.from_field,
            to_msisdn=msg.to,
            ts=msg.ts,
            text=msg.text,
            created_at=datetime.utcnow().isoformat() + "Z",
        )
        db.add(new_msg)
        db.commit()

        latency_ms = (time.time() - start_time) * 1000
        metrics.record_http_request("/webhook", 200)
        metrics.record_webhook_result("created")
        metrics.record_latency(latency_ms)
        log_request(
            request_id,
            "POST",
            "/webhook",
            200,
            latency_ms,
            extra={"message_id": msg.message_id, "dup": False, "result": "created"},
        )
        return JSONResponse(status_code=200, content={"status": "ok"})

    except IntegrityError:
        # Duplicate message_id → idempotent success
        db.rollback()
        latency_ms = (time.time() - start_time) * 1000
        metrics.record_http_request("/webhook", 200)
        metrics.record_webhook_result("duplicate")
        metrics.record_latency(latency_ms)
        log_request(
            request_id,
            "POST",
            "/webhook",
            200,
            latency_ms,
            extra={"message_id": msg.message_id, "dup": True, "result": "duplicate"},
        )
        return JSONResponse(status_code=200, content={"status": "ok"})

    except Exception as e:
        db.rollback()
        latency_ms = (time.time() - start_time) * 1000
        metrics.record_http_request("/webhook", 500)
        metrics.record_webhook_result("error")
        metrics.record_latency(latency_ms)
        log_request(
            request_id,
            "POST",
            "/webhook",
            500,
            latency_ms,
            extra={"result": "error", "error": str(e)},
        )
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})


# ==================== Messages Endpoint ====================

@app.get("/messages", response_model=MessagesListResponse)
def get_messages(
    limit: int = 50,
    offset: int = 0,
    from_: Optional[str] = None,
    since: Optional[str] = None,
    q: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    List messages with pagination and filters:
    - limit: 1–100 (default 50)
    - offset: >= 0
    - from_: exact match on from_msisdn
    - since: ts >= since
    - q: case-insensitive substring match on text
    """
    request_id = str(uuid.uuid4())
    start_time = time.time()

    if limit < 1 or limit > 100:
        limit = 50
    if offset < 0:
        offset = 0

    query = db.query(Message)

    if from_:
        query = query.filter(Message.from_msisdn == from_)
    if since:
        query = query.filter(Message.ts >= since)
    if q:
        query = query.filter(Message.text.ilike(f"%{q}%"))

    total = query.count()

    messages = (
        query.order_by(Message.ts.asc(), Message.message_id.asc())
        .limit(limit)
        .offset(offset)
        .all()
    )

    latency_ms = (time.time() - start_time) * 1000
    metrics.record_http_request("/messages", 200)
    metrics.record_latency(latency_ms)
    log_request(
        request_id,
        "GET",
        "/messages",
        200,
        latency_ms,
        extra={"limit": limit, "offset": offset, "total": total},
    )

    return MessagesListResponse(
        data=[MessageResponse.from_orm(m) for m in messages],
        total=total,
        limit=limit,
        offset=offset,
    )


# ==================== Stats Endpoint ====================

@app.get("/stats", response_model=StatsResponse)
def get_stats(db: Session = Depends(get_db)):
    """
    Message-level analytics:
    - total_messages
    - senders_count
    - messages_per_sender (top 10)
    - first_message_ts / last_message_ts
    """
    request_id = str(uuid.uuid4())
    start_time = time.time()

    total_messages = db.query(Message).count()
    senders_count = db.query(Message.from_msisdn).distinct().count()

    top_senders = (
        db.query(Message.from_msisdn, func.count().label("count"))
        .group_by(Message.from_msisdn)
        .order_by(func.count().desc())
        .limit(10)
        .all()
    )
    messages_per_sender = [
        SenderStat(from_msisdn=s[0], count=s[1]) for s in top_senders
    ]

    first_message_ts = db.query(func.min(Message.ts)).scalar()
    last_message_ts = db.query(func.max(Message.ts)).scalar()

    latency_ms = (time.time() - start_time) * 1000
    metrics.record_http_request("/stats", 200)
    metrics.record_latency(latency_ms)
    log_request(request_id, "GET", "/stats", 200, latency_ms)

    return StatsResponse(
        total_messages=total_messages,
        senders_count=senders_count,
        messages_per_sender=messages_per_sender,
        first_message_ts=first_message_ts,
        last_message_ts=last_message_ts,
    )


# ==================== Metrics Endpoint ====================

@app.get("/metrics")
def get_metrics():
    """Prometheus-style metrics export."""
    request_id = str(uuid.uuid4())
    start_time = time.time()

    body = metrics.export_prometheus()

    latency_ms = (time.time() - start_time) * 1000
    metrics.record_http_request("/metrics", 200)
    metrics.record_latency(latency_ms)
    log_request(request_id, "GET", "/metrics", 200, latency_ms)

    # FastAPI will return plain text here; it's fine for the assignment
    return body
