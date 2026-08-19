"""MDLA 图形界面（CustomTkinter）主窗口与导航。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import customtkinter as ctk

from store import BASE_DIR, AGENT_MAIN, ConfigStore, SecretStore
from agent_manager import AgentManager
from pages.dashboard import DashboardPage
from pages.settings import SettingsPage
from pages.mcp_page import McpPage
from pages.logs_page import LogsPage
from pages.history_page import HistoryPage

NAV_ACTIVE_FG = ("#5B4CE0", "#6C63FF")
NAV_INACTIVE_TEXT = ("#1E1E2E", "#E0E0E6")
SETTING_KEYS = {"email", "whitelist", "llm", "permissions", "system"}


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("MDLA · 邮件驱动智能代理")
        self.geometry("1200x760")
        self.minsize(1000, 640)
        self.config = ConfigStore()
        self.secrets = SecretStore()
        self.agent = AgentManager(AGENT_MAIN, BASE_DIR)
        self.apply_theme()

        self.sidebar = ctk.CTkFrame(self, width=190, corner_radius=0)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)
        ctk.CTkLabel(self.sidebar, text="MDLA", font=("Microsoft YaHei", 24, "bold")).pack(pady=(26, 20))

        self.nav_buttons: dict[str, ctk.CTkButton] = {}
        items = [
            ("dashboard", "主页"),
            ("email", "邮件设置"), ("whitelist", "白名单"), ("llm", "大模型"),
            ("permissions", "权限"),
            ("mcp", "MCP 管理"), ("history", "历史问答"), ("logs", "日志查看"),
            ("system", "系统设置"),
        ]
        for key, label in items:
            btn = ctk.CTkButton(
                self.sidebar, text=label, anchor="w", height=40, corner_radius=6, fg_color="transparent",
                text_color=NAV_INACTIVE_TEXT, hover_color=("gray90", "gray25"),
                font=("Microsoft YaHei", 14), command=lambda k=key: self.show_page(k),
            )
            btn.pack(fill="x", padx=14, pady=4)
            self.nav_buttons[key] = btn

        self.content = ctk.CTkFrame(self, corner_radius=0)
        self.content.pack(side="left", fill="both", expand=True)

        self.pages: dict[str, ctk.CTkFrame] = {
            "dashboard": DashboardPage(self.content, self),
            "settings": SettingsPage(self.content, self),
            "mcp": McpPage(self.content, self),
            "history": HistoryPage(self.content, self),
            "logs": LogsPage(self.content, self),
        }
        self.show_page("dashboard")

    def apply_theme(self):
        theme = self.config.load("system.json").get("theme", "dark")
        ctk.set_appearance_mode(theme if theme in ("dark", "light") else "system")

    def show_page(self, key: str):
        target = "settings" if key in SETTING_KEYS else key
        for k, page in self.pages.items():
            if k == target:
                page.pack(fill="both", expand=True)
            else:
                page.pack_forget()
        if target == "settings":
            self.pages["settings"].show_section(key)
        for k, btn in self.nav_buttons.items():
            if k == key:
                btn.configure(fg_color=NAV_ACTIVE_FG, text_color="white")
            else:
                btn.configure(fg_color="transparent", text_color=NAV_INACTIVE_TEXT)

    def notify(self, message: str):
        dashboard = self.pages.get("dashboard")
        if dashboard is not None:
            dashboard.set_toast(message)


def main():
    ctk.set_default_color_theme("dark-blue")
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()