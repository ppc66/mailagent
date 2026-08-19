"""对话历史：按天分文件保存到本地（Logs/history/YYYY-MM-DD.jsonl）。"""
import json
import os
from datetime import datetime


class HistoryStore:
    def __init__(self, base_dir: str):
        self.dir = os.path.join(base_dir, "history")
        os.makedirs(self.dir, exist_ok=True)

    def add(self, record: dict):
        path = os.path.join(self.dir, f"{datetime.now():%Y-%m-%d}.jsonl")
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            pass