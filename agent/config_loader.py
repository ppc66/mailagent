"""配置加载与热加载。"""
import json
import os
import shutil
import threading
import time
from typing import Callable, Optional

from logger import logger

CURRENT_VERSION = "1.0"
COLD_FILES = {"llm.json"}
EMAIL_HOT_KEYS = {
    "polling_interval", "use_idle", "max_emails_per_poll",
    "max_attachment_size_mb", "max_attachments_per_email",
    "temp_cleanup_hours", "temp_dir",
}
DEFAULTS: dict[str, dict] = {
    "email.json": {
        "version": CURRENT_VERSION, "imap_server": "imap.qq.com", "imap_port": 993,
        "imap_ssl": True, "smtp_server": "smtp.qq.com", "smtp_port": 587,
        "smtp_tls": True, "email_account": "", "polling_interval": 30,
        "use_idle": True, "max_emails_per_poll": 5, "max_attachment_size_mb": 50,
        "max_attachments_per_email": 10, "temp_cleanup_hours": 24, "temp_dir": "",
    },
    "whitelist.json": {"version": CURRENT_VERSION, "emails": [], "disabled": []},
    "llm.json": {
        "version": CURRENT_VERSION, "active_provider": "deepseek",
        "max_total_tokens_per_task": 8000, "max_llm_calls_per_task": 10,
        "providers": [], "system_prompt": "",
    },
    "permissions.json": {
        "version": CURRENT_VERSION, "allowed_commands": [], "workspace_dirs": [],
        "sandbox_mode": "workspace", "custom_dirs": [], "allow_delete": False,
        "high_risk_actions": ["delete"], "allow_send_to_non_whitelist": False,
        "command_timeout": 30, "confirm_timeout_seconds": 300, "rate_limit_per_minute": 5,
    },
    "mcp_servers.json": {
        "version": CURRENT_VERSION, "auto_restart": True, "max_restart_attempts": 3, "servers": [],
    },
    "system.json": {
        "version": CURRENT_VERSION, "theme": "dark", "log_level": "INFO",
        "log_retention_days": 30, "max_log_file_size_mb": 50, "language": "zh-CN",
    },
}


class ConfigManager:
    def __init__(self, config_dir: str, poll_interval: float = 2.0):
        self.config_dir = config_dir
        self.backup_dir = os.path.join(config_dir, "backup")
        self.poll_interval = poll_interval
        self._configs: dict[str, dict] = {}
        self._mtimes: dict[str, float] = {}
        self._on_change: list[Callable[[str, bool], None]] = []
        self._stop = threading.Event()
        os.makedirs(self.backup_dir, exist_ok=True)

    def register_change_callback(self, fn: Callable[[str, bool], None]):
        self._on_change.append(fn)

    def load_all(self):
        for name in DEFAULTS:
            self._load_file(name)

    def _load_file(self, name: str):
        path = os.path.join(self.config_dir, name)
        if not os.path.exists(path):
            logger.warning(f"配置文件缺失，使用默认值: {name}")
            self._configs[name] = dict(DEFAULTS[name])
            self._mtimes[name] = 0
            return
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        migrated = self._migrate_if_needed(name, data, path)
        if migrated:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        self._configs[name] = data
        self._mtimes[name] = os.path.getmtime(path)

    def _migrate_if_needed(self, name: str, data: dict, path: str) -> bool:
        if data.get("version") == CURRENT_VERSION:
            return False
        logger.info(f"检测到配置版本变化，执行迁移: {name}")
        backup = os.path.join(self.backup_dir, f"{name}.{int(time.time())}")
        try:
            shutil.copy2(path, backup)
        except OSError:
            pass
        default = DEFAULTS[name]
        merged = dict(default)
        merged.update({k: v for k, v in data.items() if k != "version"})
        merged["version"] = CURRENT_VERSION
        data.clear()
        data.update(merged)
        return True

    def get(self, name: str, key: Optional[str] = None, default=None):
        cfg = self._configs.get(name, {})
        if key is None:
            return cfg
        return cfg.get(key, default)

    def get_config(self, name: str) -> dict:
        return dict(self._configs.get(name, {}))

    def start_watching(self):
        threading.Thread(target=self._watch_loop, daemon=True).start()

    def _watch_loop(self):
        while not self._stop.is_set():
            time.sleep(self.poll_interval)
            for name in list(DEFAULTS):
                path = os.path.join(self.config_dir, name)
                if not os.path.exists(path):
                    continue
                try:
                    mtime = os.path.getmtime(path)
                except OSError:
                    continue
                if mtime == self._mtimes.get(name):
                    continue
                self._on_file_changed(name, path, mtime)

    def _on_file_changed(self, name: str, path: str, mtime: float):
        try:
            with open(path, "r", encoding="utf-8") as f:
                new_data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.error(f"配置解析失败: {name} 原因: {e}")
            return
        old = self._configs.get(name, {})
        cold = self._is_cold_change(name, old, new_data)
        self._migrate_if_needed(name, new_data, path)
        self._configs[name] = new_data
        self._mtimes[name] = mtime
        logger.info(f"配置已更新: {name} ({'需重启' if cold else '热加载'})")
        for fn in self._on_change:
            try:
                fn(name, cold)
            except Exception as e:
                logger.error(f"配置变更回调异常: {e}")

    def _is_cold_change(self, name: str, old: dict, new: dict) -> bool:
        if name in COLD_FILES:
            return True
        if name == "email.json":
            for key in new:
                if key not in EMAIL_HOT_KEYS and old.get(key) != new.get(key):
                    return True
            return False
        return False

    def stop(self):
        self._stop.set()