"""本地工具执行器：命令白名单、路径沙盒、文件操作、高风险操作标记。"""
import json
import os
import subprocess
import zipfile
from typing import Callable, Optional

from logger import logger

HARD_BLOCKLIST = {"del", "erase", "rm", "rmdir", "format", "shutdown", "reg", "regedit"}


def _expand_path(path: str) -> str:
    return os.path.expandvars(os.path.expanduser(path))


class ToolExecutor:
    def __init__(self, config_manager, send_email_handler: Optional[Callable] = None):
        self._cfg = config_manager
        self._send_email_handler = send_email_handler

    def _permissions(self) -> dict:
        return self._cfg.get_config("permissions.json")

    def _allowed_commands(self) -> set:
        return {c.lower() for c in self._permissions().get("allowed_commands", [])}

    def _high_risk_actions(self) -> set:
        return {a.lower() for a in self._permissions().get("high_risk_actions", ["delete"])}

    def get_tool_schemas(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "execute_command",
                    "description": "在 Windows 上执行一条受白名单约束的 shell 命令。",
                    "parameters": {
                        "type": "object",
                        "properties": {"command": {"type": "string", "description": "要执行的命令"}},
                        "required": ["command"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "file_operations",
                    "description": "文件操作：读取、写入、列表、压缩、删除。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "action": {"type": "string", "enum": ["read", "write", "list", "zip", "delete"]},
                            "path": {"type": "string", "description": "目标路径"},
                            "content": {"type": "string", "description": "写入的内容（仅 write 需要）"},
                        },
                        "required": ["action", "path"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "send_email",
                    "description": "发送一封邮件，可附带附件（attachment_path 填完整文件路径）。给用户发文件时用此工具。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "to": {"type": "string"},
                            "subject": {"type": "string"},
                            "body": {"type": "string"},
                            "attachment_path": {"type": "string"},
                        },
                        "required": ["to", "subject", "body"],
                    },
                },
            },
        ]

    def is_high_risk(self, tool_name: str, arguments: dict) -> bool:
        if tool_name == "execute_command":
            first = arguments.get("command", "").strip().split()[0].lower() if arguments.get("command", "").strip() else ""
            return first in self._high_risk_actions()
        if tool_name == "file_operations":
            return arguments.get("action", "").lower() in self._high_risk_actions()
        return False

    def execute(self, tool_name: str, arguments: dict) -> str:
        try:
            if tool_name == "execute_command":
                return self._execute_command(arguments.get("command", ""))
            if tool_name == "file_operations":
                return self._file_operations(arguments)
            if tool_name == "send_email":
                return self._send_email(arguments)
            return f"未知工具: {tool_name}"
        except Exception as e:
            logger.error(f"工具执行异常 {tool_name}: {e}")
            return f"工具执行失败: {e}"

    def _execute_command(self, command: str) -> str:
        command = command.strip()
        if not command:
            return "命令为空"
        first = command.split()[0].lower()
        if first in HARD_BLOCKLIST:
            return f"命令被安全策略禁止: {first}"
        if first not in self._allowed_commands():
            return f"命令不在白名单中: {first}"
        timeout = int(self._permissions().get("command_timeout", 30))
        try:
            proc = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return f"命令执行超时（{timeout}秒）"
        out = (proc.stdout or "") + (proc.stderr or "")
        return out.strip()[:8000] or "(无输出)"

    def _file_operations(self, args: dict) -> str:
        action = args.get("action", "").lower()
        path = _expand_path(args.get("path", ""))
        if action == "delete" and not self._permissions().get("allow_delete", False):
            return "删除操作被禁止（allow_delete=false）"
        if action in ("read", "write", "list", "zip", "delete") and not self._path_allowed(path):
            return f"路径越出沙盒范围: {path}"
        if action == "list":
            return self._list(path)
        if action == "read":
            return self._read(path)
        if action == "write":
            return self._write(path, args.get("content", ""))
        if action == "zip":
            return self._zip(path)
        if action == "delete":
            return self._delete(path)
        return f"不支持的文件操作: {action}"

    def _path_allowed(self, path: str) -> bool:
        mode = self._permissions().get("sandbox_mode", "workspace")
        if mode == "global":
            return True
        if mode == "custom":
            dirs = self._permissions().get("custom_dirs", [])
        else:
            dirs = self._permissions().get("workspace_dirs", []) + self._permissions().get("custom_dirs", [])
        allowed = [os.path.abspath(_expand_path(d)) for d in dirs if d]
        target = os.path.abspath(path)
        return any(target == a or target.startswith(a + os.sep) for a in allowed)

    def _list(self, path: str) -> str:
        if os.path.isfile(path):
            return f"{path} 是一个文件"
        if not os.path.isdir(path):
            return f"目录不存在: {path}"
        entries = os.listdir(path)
        return "\n".join(os.path.join(path, e) for e in entries[:500]) or "(空目录)"

    def _read(self, path: str) -> str:
        if not os.path.isfile(path):
            return f"文件不存在: {path}"
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                return f.read()[:8000]
        except OSError as e:
            return f"读取失败: {e}"

    def _write(self, path: str, content: str) -> str:
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return f"写入成功: {path}"
        except OSError as e:
            return f"写入失败: {e}"

    def _zip(self, path: str) -> str:
        if not os.path.exists(path):
            return f"路径不存在: {path}"
        out = path + ".zip"
        try:
            if os.path.isfile(path):
                with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
                    z.write(path, os.path.basename(path))
            else:
                with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
                    for root, _, files in os.walk(path):
                        for f in files:
                            full = os.path.join(root, f)
                            z.write(full, os.path.relpath(full, os.path.dirname(path)))
            return f"压缩成功: {out}"
        except OSError as e:
            return f"压缩失败: {e}"

    def _delete(self, path: str) -> str:
        try:
            if os.path.isfile(path):
                os.remove(path)
            elif os.path.isdir(path):
                os.rmdir(path)
            else:
                return f"路径不存在: {path}"
            return f"删除成功: {path}"
        except OSError as e:
            return f"删除失败: {e}"

    def _send_email(self, args: dict) -> str:
        if not self._send_email_handler:
            return "邮件发送器未初始化"
        to = args.get("to", "").lower()
        whitelisted = set(x.lower() for x in self._cfg.get("whitelist.json", "emails", []))
        if to not in whitelisted and not self._permissions().get("allow_send_to_non_whitelist", False):
            return "发送给非白名单邮箱被禁止（allow_send_to_non_whitelist=false）"
        self._send_email_handler(
            to=args.get("to"),
            subject=args.get("subject", ""),
            body=args.get("body", ""),
            attachment_path=args.get("attachment_path"),
        )
        return f"邮件已发送: {args.get('to')}"


def tool_result_to_str(result: object) -> str:
    if isinstance(result, str):
        return result
    return json.dumps(result, ensure_ascii=False, default=str)