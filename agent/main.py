"""MDLA Agent 入口：初始化并编排所有组件。"""
import asyncio
import json
import os
import threading
import time
from datetime import datetime

from logger import logger
from secrets import build_service
from config_loader import ConfigManager
from tool_executor import ToolExecutor
from mail_sender import MailSender
from mcp_client import MCPManager
from agent_core import AgentCore
from mail_listener import MailListener
from ipc_server import IPCServer
from history import HistoryStore

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(BASE_DIR, "Config")
LOG_DIR = os.path.join(BASE_DIR, "Logs")


def _load_system_raw() -> dict:
    try:
        with open(os.path.join(CONFIG_DIR, "system.json"), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def main():
    sys_cfg = _load_system_raw()
    logger.update_settings(
        sys_cfg.get("log_level", "INFO"),
        sys_cfg.get("max_log_file_size_mb", 50),
        sys_cfg.get("log_retention_days", 30),
    )

    config = ConfigManager(CONFIG_DIR)
    config.load_all()
    secrets = build_service(CONFIG_DIR)
    secrets.load()

    mail_sender = MailSender(config.get_config("email.json"), secrets.all())
    tool_executor = ToolExecutor(config, send_email_handler=mail_sender.send)

    mcp_manager = MCPManager(config)
    mcp_manager.apply_config()
    mcp_manager.start_health_check()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    agent_core = AgentCore(config, secrets.all(), tool_executor, mcp_manager, mail_sender, loop)

    state = {"last_instruction_time": None}
    history = HistoryStore(LOG_DIR)

    def dispatch(sender: str, text: str, attachments: list):
        if agent_core.try_handle_confirm(sender, text):
            return
        received_at = time.time()
        state["last_instruction_time"] = received_at
        request_id = str(int(received_at * 1000))
        logger.info("收到指令", sender=sender, instruction=text)

        async def handle():
            result = await agent_core.process_instruction(sender, text, attachments)
            history.add({
                "request_id": request_id,
                "sender": sender,
                "instruction": text,
                "received_at": datetime.fromtimestamp(received_at).isoformat(timespec="seconds"),
                "replied_at": datetime.now().isoformat(timespec="seconds"),
                "reply": result,
            })
            return result

        loop.call_soon_threadsafe(lambda: asyncio.ensure_future(handle()))

    listener = MailListener(config, secrets.all(), dispatch)
    listener.start()

    def on_command(name: str, payload: dict):
        if name == "RELOAD_CONFIG":
            config.load_all()
            return {"status": "ok", "message": "配置已重载"}
        if name == "STATUS":
            return {
                "status": "ok",
                "pid": os.getpid(),
                "email_connected": listener.is_connected(),
                "running_tasks": agent_core.running_tasks,
                "last_instruction_time": state["last_instruction_time"],
                "mcp_servers": mcp_manager.get_status(),
            }
        if name == "EXECUTE_TEST":
            return {"status": "ok", "running_tasks": agent_core.running_tasks}
        if name == "SHUTDOWN":
            threading.Thread(target=shutdown, daemon=True).start()
            return {"status": "ok", "message": "正在关闭"}
        return {"status": "error", "message": f"未知指令: {name}"}

    ipc = IPCServer(on_command)
    ipc.start()

    def on_config_change(filename: str, cold: bool):
        if filename == "system.json":
            updated = config.get_config("system.json")
            logger.update_settings(
                updated.get("log_level", "INFO"),
                updated.get("max_log_file_size_mb", 50),
                updated.get("log_retention_days", 30),
            )
        elif filename == "mcp_servers.json":
            threading.Thread(target=mcp_manager.apply_config, daemon=True).start()
        if cold:
            logger.warning(f"冷配置变更，触发重连: {filename}")
            listener.reconnect()

    config.register_change_callback(on_config_change)
    config.start_watching()

    def shutdown():
        logger.info("开始优雅关闭...")
        listener.stop()
        mcp_manager.stop_all()
        ipc.stop()
        config.stop()
        logger.flush()
        loop.call_soon_threadsafe(loop.stop)

    logger.info("MDLA Agent 启动完成，等待邮件指令...")
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        shutdown()


if __name__ == "__main__":
    main()