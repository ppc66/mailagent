"""主页（仪表板）：状态卡片 + 快捷操作。"""
from datetime import datetime

import customtkinter as ctk

OK = ("#2E9E63", "#4CAF7D")
BAD = ("#D64545", "#E05D5D")
MUTED = ("#6B6B80", "#9A9AB0")


class DashboardPage(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, corner_radius=0)
        self.app = app
        ctk.CTkLabel(self, text="主页", font=ctk.CTkFont(size=22, weight="bold")).pack(anchor="w", padx=26, pady=(22, 14))
        cards = ctk.CTkFrame(self, fg_color="transparent")
        cards.pack(fill="x", padx=26)
        self.cards = {}
        for col, (key, title) in enumerate([("agent", "Agent 运行状态"), ("email", "邮件连接状态"), ("last", "最后指令时间"), ("tasks", "运行中任务数")]):
            self.cards[key] = self._make_card(cards, title, col)
        ctk.CTkLabel(self, text="快捷操作", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", padx=26, pady=(22, 8))
        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.pack(fill="x", padx=26)
        ctk.CTkButton(actions, text="启动 Agent", command=self.app.agent.start).pack(side="left", padx=(0, 10))
        ctk.CTkButton(actions, text="停止 Agent", command=self.app.agent.stop).pack(side="left", padx=(0, 10))
        ctk.CTkButton(actions, text="重新载入配置", command=self._reload).pack(side="left", padx=(0, 10))
        ctk.CTkButton(actions, text="刷新状态", command=self._refresh).pack(side="left")
        self.toast_label = ctk.CTkLabel(self, text="", text_color=MUTED)
        self.toast_label.pack(anchor="w", padx=26, pady=(10, 0))
        self.after(1200, self._refresh_loop)

    def _make_card(self, parent, title, col):
        card = ctk.CTkFrame(parent, corner_radius=10)
        card.grid(row=0, column=col, padx=(0 if col == 0 else 8, 0), sticky="ew")
        parent.grid_columnconfigure(col, weight=1)
        ctk.CTkLabel(card, text=title, text_color=MUTED, font=ctk.CTkFont(size=12)).pack(anchor="w", padx=16, pady=(14, 2))
        value = ctk.CTkLabel(card, text="—", font=ctk.CTkFont(size=20, weight="bold"))
        value.pack(anchor="w", padx=16, pady=(0, 14))
        return value

    def set_toast(self, message: str):
        self.toast_label.configure(text=message)

    def _reload(self):
        result = self.app.agent.reload_config()
        self.set_toast("配置已重载" if result else "重载失败（Agent 未运行？）")
        self._refresh()

    def _refresh_loop(self):
        self._refresh()
        self.after(2000, self._refresh_loop)

    def _refresh(self):
        if not self.app.agent.is_running():
            self._set_card("agent", "已停止", BAD)
            self._set_card("email", "—", MUTED)
            self._set_card("last", "—", MUTED)
            self._set_card("tasks", "—", MUTED)
            return
        self._set_card("agent", "运行中", OK)
        status = self.app.agent.get_status()
        if not status:
            self._set_card("email", "未知", MUTED)
            self._set_card("last", "未知", MUTED)
            self._set_card("tasks", "未知", MUTED)
            return
        if status.get("email_connected"):
            self._set_card("email", "已连接", OK)
        else:
            self._set_card("email", "未连接", BAD)
        ts = status.get("last_instruction_time")
        if ts:
            self._set_card("last", datetime.fromtimestamp(ts).strftime("%m-%d %H:%M:%S"), MUTED)
        else:
            self._set_card("last", "暂无", MUTED)
        self._set_card("tasks", str(status.get("running_tasks", 0)), MUTED)

    def _set_card(self, key, text, color):
        self.cards[key].configure(text=text, text_color=color)