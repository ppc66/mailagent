"""GUI 侧配置与密钥读写（直接操作 Config/*.json，与 Agent 共享同一份配置）。"""
import json
import os
from typing import Any

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(BASE_DIR, "Config")
LOG_DIR = os.path.join(BASE_DIR, "Logs")
AGENT_MAIN = os.path.join(BASE_DIR, "agent", "main.py")

CONFIG_FILES = ["email.json", "whitelist.json", "llm.json", "permissions.json", "mcp_servers.json", "system.json"]


class ConfigStore:
    def __init__(self, config_dir: str = CONFIG_DIR):
        self.config_dir = config_dir

    def load(self, name: str) -> dict:
        path = os.path.join(self.config_dir, name)
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}

    def save(self, name: str, data: dict) -> bool:
        path = os.path.join(self.config_dir, name)
        try:
            os.makedirs(self.config_dir, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except OSError:
            return False


class SecretStore:
    def __init__(self, config_dir: str = CONFIG_DIR):
        self.path = os.path.join(config_dir, "secrets.json")

    def load(self) -> dict:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}

    def save(self, data: dict) -> bool:
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except OSError:
            return False


def parse_list(text: str) -> list:
    parts = []
    for seg in text.replace("\n", ",").split(","):
        seg = seg.strip()
        if seg:
            parts.append(seg)
    return parts


def format_list(items: list) -> str:
    return "\n".join(str(x) for x in (items or []))