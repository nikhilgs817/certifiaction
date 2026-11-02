from __future__ import annotations

import json
import logging

from app.logging_setup import JsonFormatter


def test_json_log_line() -> None:
    record = logging.LogRecord("app", logging.INFO, __file__, 1, "request", None, None)
    record.status = 200
    line = json.loads(JsonFormatter("svc").format(record))
    assert line["level"] == "info"
    assert line["service"] == "svc"
    assert line["msg"] == "request"
    assert line["status"] == 200
