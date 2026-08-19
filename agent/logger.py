"""结构化日志模块：JSONL 格式、异步批量写入、按日期切割、脱敏、大小轮转。"""
import json
import os
import re
import threading
import time
from datetime import datetime
from typing import Any

SENSITIVE_KEYWORDS = ("password", "token", "apikey", "api_key", "access_token")


def _redact(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {
            k: ("***" if any(kw in k.lower() for kw in SENSITIVE_KEYWORDS) else _redact(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_redact(v) for v in obj]
    return obj


class JsonlLogger:
    LEVELS = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40}

    def __init__(self, log_dir: str, level: str = "INFO",
                 max_file_size_mb: int = 50, retention_days: int = 30):
        self.log_dir = log_dir
        self.level = level.upper()
        self.max_file_size_mb = max_file_size_mb
        self.retention_days = retention_days
        os.makedirs(log_dir, exist_ok=True)

        self._buffer: list[dict] = []
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._flush_loop, daemon=True)
        self._thread.start()

    def update_settings(self, level: str, max_file_size_mb: int, retention_days: int):
        self.level = level.upper()
        self.max_file_size_mb = max_file_size_mb
        self.retention_days = retention_days

    def _log(self, level: str, message: str, **fields):
        if self.LEVELS.get(level, 0) < self.LEVELS.get(self.level, 20):
            return
        record = {"timestamp": datetime.now().isoformat(timespec="seconds"), "level": level, "message": message}
        if fields:
            record["fields"] = _redact(fields)
        with self._lock:
            self._buffer.append(record)
            if len(self._buffer) >= 10:
                self._flush_locked()

    def debug(self, msg: str, **fields):
        self._log("DEBUG", msg, **fields)

    def info(self, msg: str, **fields):
        self._log("INFO", msg, **fields)

    def warning(self, msg: str, **fields):
        self._log("WARNING", msg, **fields)

    def error(self, msg: str, **fields):
        self._log("ERROR", msg, **fields)

    def _log_path(self) -> str:
        return os.path.join(self.log_dir, f"{datetime.now():%Y-%m-%d}.jsonl")

    def _flush_loop(self):
        while True:
            time.sleep(5)
            with self._lock:
                self._flush_locked()

    def _flush_locked(self):
        if not self._buffer:
            return
        path = self._log_path()
        try:
            with open(path, "a", encoding="utf-8") as f:
                for record in self._buffer:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            pass
        self._buffer.clear()
        self._rotate_if_needed(path)

    def _rotate_if_needed(self, path: str):
        try:
            size = os.path.getsize(path)
        except OSError:
            return
        if size >= self.max_file_size_mb * 1024 * 1024:
            stamp = time.strftime("%H%M%S")
            backup = f"{path}.{stamp}"
            try:
                os.rename(path, backup)
            except OSError:
                pass

    def flush(self):
        with self._lock:
            self._flush_locked()


logger = JsonlLogger(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Logs"))