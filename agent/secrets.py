"""敏感信息管理：使用 Windows DPAPI 加密存储到 secrets.enc。

优先读取 secrets.enc（DPAPI 加密）；若不存在则回退读取 secrets.json（明文，仅开发用）。
首次运行提供 encrypt() 将明文转为密文。
"""
import json
import os
from typing import Any

try:
    import win32crypt  # pywin32
except ImportError:  # 非 Windows 环境降级
    win32crypt = None

DPAPI_DESCRIPTION = "MDLA-secrets"


class SecretService:
    def __init__(self, secrets_enc_path: str, secrets_json_path: str):
        self.enc_path = secrets_enc_path
        self.json_path = secrets_json_path
        self._data: dict = {}

    def load(self) -> dict:
        if os.path.exists(self.enc_path):
            self._data = self._decrypt_file(self.enc_path)
        elif os.path.exists(self.json_path):
            with open(self.json_path, "r", encoding="utf-8") as f:
                self._data = json.load(f)
        else:
            self._data = {}
        return self._data

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def all(self) -> dict:
        return dict(self._data)

    def save_encrypted(self, data: dict):
        """将明文 dict 加密写入 secrets.enc。"""
        if win32crypt is None:
            raise RuntimeError("DPAPI 仅在 Windows 可用")
        plain = json.dumps(data, ensure_ascii=False).encode("utf-8")
        cipher = self._encrypt(plain)
        with open(self.enc_path, "wb") as f:
            f.write(cipher)

    def _encrypt(self, plain: bytes) -> bytes:
        result = win32crypt.CryptProtectData(plain, DPAPI_DESCRIPTION)
        if isinstance(result, tuple):
            return result[0]
        return result

    def _decrypt_file(self, path: str) -> dict:
        if win32crypt is None:
            return {}
        with open(path, "rb") as f:
            cipher = f.read()
        plain = self._decrypt(cipher)
        return json.loads(plain.decode("utf-8"))

    def _decrypt(self, cipher: bytes) -> bytes:
        result = win32crypt.CryptUnprotectData(cipher)
        if isinstance(result, tuple):
            return result[-1]
        return result


def build_service(config_dir: str) -> SecretService:
    return SecretService(
        secrets_enc_path=os.path.join(config_dir, "secrets.enc"),
        secrets_json_path=os.path.join(config_dir, "secrets.json"),
    )