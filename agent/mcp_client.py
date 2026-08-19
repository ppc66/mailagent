"""MCP 客户端：通过 stdio + JSON-RPC 管理 MCP 服务器子进程，健康检查、自动重启、失败禁用。"""
import json
import os
import subprocess
import threading
import time
from typing import Optional

from logger import logger


class MCPConnection:
    def __init__(self, conf: dict):
        self.conf = conf
        self.proc: Optional[subprocess.Popen] = None
        self.disabled = False
        self._lock = threading.Lock()
        self._req_id = 0
        self._pending: dict[int, threading.Event] = {}
        self._results: dict[int, dict] = {}

    def start(self) -> bool:
        try:
            env = os.environ.copy()
            for k, v in self.conf.get("env", {}).items():
                env[k] = str(v)
            self.proc = subprocess.Popen(
                [self.conf.get("command", "python")] + self.conf.get("args", []),
                cwd=self.conf.get("cwd") or None,
                env=env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except Exception as e:
            logger.error(f"MCP 进程启动失败 {self.conf.get('id')}: {e}")
            self.disabled = True
            return False
        threading.Thread(target=self._read_loop, daemon=True).start()
        threading.Thread(target=self._drain_stderr, daemon=True).start()
        try:
            self._request("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "MDLA", "version": "4.0"},
            })
        except Exception as e:
            logger.error(f"MCP 初始化失败 {self.conf.get('id')}: {e}")
            self.stop()
            self.disabled = True
            return False
        return True

    def stop(self):
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.stdin.close()
                self.proc.terminate()
                self.proc.wait(timeout=5)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
        self.proc = None

    def is_alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def _read_loop(self):
        if not self.proc:
            return
        try:
            for line in self.proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                rid = msg.get("id")
                if rid is not None and rid in self._pending:
                    self._results[rid] = msg
                    self._pending[rid].set()
        except Exception:
            pass

    def _drain_stderr(self):
        if not self.proc:
            return
        try:
            for _ in self.proc.stderr:
                pass
        except Exception:
            pass

    def _request(self, method: str, params: dict, timeout: float = 15):
        if not self.is_alive():
            raise RuntimeError(f"MCP 进程未运行: {self.conf.get('id')}")
        with self._lock:
            self._req_id += 1
            rid = self._req_id
            event = threading.Event()
            self._pending[rid] = event
            payload = {"jsonrpc": "2.0", "id": rid, "method": method, "params": params}
            try:
                self.proc.stdin.write(json.dumps(payload) + "\n")
                self.proc.stdin.flush()
            except Exception as e:
                self._pending.pop(rid, None)
                raise RuntimeError(f"写入 MCP 进程失败: {e}") from e
        if event.wait(timeout):
            msg = self._results.pop(rid, None)
            self._pending.pop(rid, None)
            if msg is None:
                raise RuntimeError("MCP 响应缺失")
            if "error" in msg:
                raise RuntimeError(f"MCP 错误: {msg['error']}")
            return msg.get("result")
        self._pending.pop(rid, None)
        raise TimeoutError(f"MCP 请求超时: {method}")

    def list_tools(self) -> list:
        result = self._request("tools/list", {})
        return result.get("tools", [])

    def call_tool(self, name: str, arguments: dict) -> str:
        result = self._request("tools/call", {"name": name, "arguments": arguments})
        content = result.get("content", [])
        parts = []
        for item in content:
            if isinstance(item, dict) and "text" in item:
                parts.append(item["text"])
            else:
                parts.append(json.dumps(item, ensure_ascii=False, default=str))
        return "\n".join(parts)


def _to_openai_tool(mcp_tool: dict) -> dict:
    return {
        "type": "function",
        "function": {
            "name": mcp_tool.get("name", ""),
            "description": mcp_tool.get("description", ""),
            "parameters": mcp_tool.get("inputSchema", {"type": "object", "properties": {}}),
        },
    }


class MCPManager:
    def __init__(self, config_manager):
        self._cfg = config_manager
        self._connections: dict[str, MCPConnection] = {}
        self._restart_count: dict[str, int] = {}
        self._tools_cache: dict[str, list] = {}
        self._stop = threading.Event()

    def apply_config(self):
        servers = self._cfg.get("mcp_servers.json", "servers", [])
        wanted = {s["id"]: s for s in servers if s.get("enabled", True)}
        existing = set(self._connections)
        for sid in existing - set(wanted):
            self._connections[sid].stop()
            del self._connections[sid]
            self._restart_count.pop(sid, None)
            self._tools_cache.pop(sid, None)
        for sid, conf in wanted.items():
            if sid in self._connections:
                self._connections[sid].stop()
            conn = MCPConnection(conf)
            self._connections[sid] = conn
            self._restart_count[sid] = 0
            if conn.start() and self._discover(conn):
                logger.info(f"MCP 服务器已启动: {sid}")
            else:
                conn.disabled = True
                logger.error(f"MCP 服务器启动失败，标记禁用: {sid}")

    def _discover(self, conn: MCPConnection) -> bool:
        try:
            tools = conn.list_tools()
        except Exception as e:
            logger.error(f"MCP 工具发现失败 {conn.conf.get('id')}: {e}")
            return False
        self._tools_cache[conn.conf["id"]] = tools
        return True

    def get_tool_schemas(self) -> list[dict]:
        out = []
        for sid, tools in self._tools_cache.items():
            conn = self._connections.get(sid)
            if conn and conn.disabled:
                continue
            for t in tools:
                out.append(_to_openai_tool(t))
        return out

    def find_tool_server(self, tool_name: str) -> Optional[str]:
        for sid, tools in self._tools_cache.items():
            conn = self._connections.get(sid)
            if conn and conn.disabled:
                continue
            for t in tools:
                if t.get("name") == tool_name:
                    return sid
        return None

    def call_tool(self, server_id: str, name: str, arguments: dict) -> str:
        conn = self._connections.get(server_id)
        if not conn or conn.disabled:
            return f"MCP 服务器不可用: {server_id}"
        return conn.call_tool(name, arguments)

    def get_status(self) -> list[dict]:
        out = []
        for sid, conn in self._connections.items():
            out.append({
                "id": sid,
                "disabled": conn.disabled,
                "alive": conn.is_alive(),
                "tool_count": len(self._tools_cache.get(sid, [])),
            })
        return out

    def start_health_check(self):
        threading.Thread(target=self._health_loop, daemon=True).start()

    def _health_loop(self):
        while not self._stop.is_set():
            self._stop.wait(30)
            for sid, conn in list(self._connections.items()):
                if conn.disabled or conn.is_alive():
                    continue
                self._handle_crash(sid, conn)

    def _handle_crash(self, sid: str, conn: MCPConnection):
        max_attempts = int(self._cfg.get("mcp_servers.json", "max_restart_attempts", 3))
        if not self._cfg.get("mcp_servers.json", "auto_restart", True):
            conn.disabled = True
            return
        if self._restart_count.get(sid, 0) >= max_attempts:
            conn.disabled = True
            logger.error(f"MCP 服务器重启次数超限，标记禁用: {sid}")
            return
        self._restart_count[sid] = self._restart_count.get(sid, 0) + 1
        logger.warning(f"MCP 服务器崩溃，重启中 {sid}（第 {self._restart_count[sid]} 次）")
        try:
            if conn.start() and self._discover(conn):
                self._restart_count[sid] = 0
                logger.info(f"MCP 服务器已恢复: {sid}")
        except Exception as e:
            logger.error(f"MCP 重启失败 {sid}: {e}")

    def stop_all(self):
        self._stop.set()
        for conn in self._connections.values():
            conn.stop()
        self._connections.clear()