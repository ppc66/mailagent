"""Agent 进程管理 + 命名管道 IPC 客户端。"""
import json
import os
import subprocess
import sys
import time

try:
    import win32file
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

PIPE_NAME = r"\\.\pipe\MDLA_Agent"


class AgentManager:
    def __init__(self, agent_main: str, cwd: str, python: str | None = None):
        self.agent_main = agent_main
        self.cwd = cwd
        self.python = python or sys.executable
        self._proc: subprocess.Popen | None = None
        self._req_id = 0

    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self) -> bool:
        if self.is_running():
            return True
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        try:
            self._proc = subprocess.Popen([self.python, self.agent_main], cwd=self.cwd, creationflags=flags)
            return True
        except OSError:
            return False

    def stop(self):
        if self.is_running():
            try:
                self.request("SHUTDOWN", {}, timeout=2)
            except Exception:
                pass
            time.sleep(1)
            if self.is_running():
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
        self._proc = None

    def reload_config(self):
        return self.request("RELOAD_CONFIG", {})

    def get_status(self):
        return self.request("STATUS", {})

    def request(self, name: str, payload: dict, timeout: float = 3.0):
        if not HAS_WIN32:
            return {"status": "error", "message": "缺少 pywin32，无法使用 IPC"}
        handle = None
        try:
            handle = win32file.CreateFile(
                PIPE_NAME,
                win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                0, None, win32file.OPEN_EXISTING, 0, None,
            )
        except Exception:
            return None
        self._req_id += 1
        rid = self._req_id
        line = json.dumps({"type": "command", "id": rid, "name": name, "payload": payload})
        try:
            win32file.WriteFile(handle, (line + "\n").encode("utf-8"))
        except Exception:
            win32file.CloseHandle(handle)
            return None
        buf = b""
        deadline = time.time() + timeout
        result = None
        while time.time() < deadline:
            try:
                _, chunk = win32file.ReadFile(handle, 65536)
            except Exception:
                break
            buf += chunk
            while b"\n" in buf:
                raw, buf = buf.split(b"\n", 1)
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if msg.get("type") == "PING":
                    try:
                        win32file.WriteFile(handle, b'{"type":"PONG"}\n')
                    except Exception:
                        pass
                elif msg.get("type") == "response" and msg.get("id") == rid:
                    result = msg.get("result")
                    break
            if result is not None:
                break
        try:
            win32file.CloseHandle(handle)
        except Exception:
            pass
        return result