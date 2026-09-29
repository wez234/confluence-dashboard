"""Cross-cutting service: monitoring & logging.

Structured (JSON lines) logs to stdout so Docker / any log aggregator can
collect them; optional file sink via LOG_FILE.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)),
                   "level": record.levelname, "service": record.name, "msg": record.getMessage()}
        if hasattr(record, "extra_fields"):
            payload.update(record.extra_fields)
        return json.dumps(payload, default=str)


def get_logger(service: str) -> logging.Logger:
    logger = logging.getLogger(service)
    if logger.handlers:
        return logger
    logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))
    fmt = JsonFormatter() if os.environ.get("LOG_FORMAT", "text") == "json" else \
        logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    h = logging.StreamHandler(sys.stdout); h.setFormatter(fmt); logger.addHandler(h)
    if os.environ.get("LOG_FILE"):
        fh = logging.FileHandler(os.environ["LOG_FILE"]); fh.setFormatter(JsonFormatter()); logger.addHandler(fh)
    logger.propagate = False
    return logger


def log_metric(logger: logging.Logger, msg: str, **fields):
    logger.info(msg, extra={"extra_fields": fields})
