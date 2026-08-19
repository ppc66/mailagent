"""IPC 命名管道服务端：接收客户端指令（RELOAD_CONFIG / EXECUTE_TEST / SHUTDOWN），发送 PING 心跳。

使用字节流 + 换行帧（JSON 每行一条），与 C# NamedPipeClientStream 可直接互通。
"""
import json
import threading
from typing import Callable, Optional

from logger import logger

PIPE_NAME = r"\\.\pipe\MDLA_Agent"

try:
    import win32file
    import win32pipe
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

HEARTBEAT_INTERVAL = 1.0

# 连续多少次 PONG 丢失判定客户端断开（服务端侧辅助判断）
PONG_MISS_THRESHOLD = 3


class IPCServer:
    def __init__(self, on_command: Callable[[str, dict], Optional[dict]]):
        self._on_command = on_command
        self._stop = threading.Event()
        self._clients: list["_ClientSession"] = []

    def start(self):
        if not HAS_WIN32:
            logger.error("缺少 pywin32，IPC 服务不可用")
            return
        threading.Thread(target=self._serve_loop, daemon=True).start()
        logger.info(f"IPC 服务已启动: {PIPE_NAME}")

    def stop(self):
        self._stop.set()
        for c in list(self._clients):
            c.close()
        self._clients.clear()

    def _serve_loop(self):
        while not self._stop.is_set():
            handle = None
            try:
                handle = win32pipe.CreateNamedPipe(
                    PIPE_NAME,
                    win32pipe.PIPE_ACCESS_DUPLEX,
                    win32pipe.PIPE_TYPE_BYTE | win32pipe.PIPE_READMODE_BYTE | win32pipe.PIPE_WAIT,
                    1, 65536, 65536, 0, None,
                )
                win32pipe.ConnectNamedPipe(handle, None)
                session = _ClientSession(handle, self._on_command, self._remove_client)
                self._clients.append(session)
                session.start()
            except Exception:  # noqa: BLE001
                if handle is not None:
                    try:
                        win32file.CloseHandle(handle)
                    except Exception:  # noqa: BLE001
                        pass
                if not self._stop.is_set():
                    threading.Event().wait(0.5)

    def _remove_client(self, session: "_ClientSession"):
        if session in self._clients:
            self._clients.remove(session)


class _ClientSession:
    def __init__(self, handle, on_command, on_close):
        self._handle = handle
        self._on_command = on_command
        self._on_close = on_close
        self._closed = False
        self._pong_ok = True

    def start(self):
        threading.Thread(target=self._read_loop, daemon=True).start()
        threading.Thread(target=self._heartbeat_loop, daemon=True).start()

    def _read_loop(self):
        buf = b""
        while not self._closed:
            try:
                _, chunk = win32file.ReadFile(self._handle, 65536)
            except Exception:  # noqa: BLE001
                break
            if not chunk:
                continue
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                self._handle_line(line)
        self.close()

    def _handle_line(self, line: bytes):
        line = line.strip()
        if not line:
            return
        try:
            msg = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return
        if msg.get("type") == "PONG":
            self._pong_ok = True
            return
        if msg.get("type") == "command":
            name = msg.get("name", "")
            rid = msg.get("id")
            payload = msg.get("payload", {})
            try:
                result = self._on_command(name, payload)
            except Exception as e:  # noqa: BLE001
                logger.error(f"IPC 指令处理异常 {name}: {e}")
                result = {"status": "error", "message": str(e)}
            self._send({"type": "response", "id": rid, "name": name, "result": result})

    def _heartbeat_loop(self):
        while not self._closed:
            threading.Event().wait(HEARTBEAT_INTERVAL)
            self._send({"type": "PING"})

    def _send(self, obj: dict):
        if self._closed:
            return
        try:
            win32file.WriteFile(
                self._handle, (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")
            )
        except Exception:  # noqa: BLE001
            self.close()

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            win32file.CloseHandle(self._handle)
        except Exception:  # noqa: BLE001
            pass
        self._on_close(self)