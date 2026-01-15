import json
import logging
import sys
from datetime import datetime
from typing import Optional

class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "message": record.getMessage(),
        }
        return json.dumps(log_data)

def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = JSONFormatter()
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger

def log_request(request_id: str, method: str, path: str, status: int, latency_ms: float, level: str = "INFO", extra: Optional[dict] = None) -> None:
    logger = get_logger("request")
    log_data = {
        "ts": datetime.utcnow().isoformat() + "Z",
        "level": level,
        "request_id": request_id,
        "method": method,
        "path": path,
        "status": status,
        "latency_ms": round(latency_ms, 2),
    }
    if extra:
        log_data.update(extra)
    logger.info(json.dumps(log_data))
