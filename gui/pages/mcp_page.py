"""MCP 管理页：增删 MCP 服务器、切换启用、编辑配置。"""
import customtkinter as ctk

from store import parse_list, format_list


class McpPage(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, corner_radius=0)
        self.app = app
        self.rows: list[dict] = []
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=26, pady=(22, 8))
        ctk.CTkLabel(head, text="MCP 管理", font=ctk.CTkFont(size=22, weight="bold")).pack(side="left")
        ctk.CTkButton(head, text="添加服务器", width=100, command=self._add_row).pack(side="right")
        ctk.CTkButton(head, text="重新载入", width=100, command=self._reload).pack(side="right", padx=(0, 8))
        self.scroll = ctk.CTkScrollableFrame(self)
        self.scroll.pack(fill="both", expand=True, padx=26, pady=(0, 8))
        ctk.CTkButton(self, text="保存", command=self.save).pack(pady=(4, 16))
        self._load()

    def _load(self):
        for row in self.rows:
            row["card"].destroy()
        self.rows.clear()
        data = self.app.config.load("mcp_servers.json")
        for srv in data.get("servers", []):
            self._add_row(srv)

    def _add_row(self, server: dict | None = None):
        server = server or {}
        card = ctk.CTkFrame(self.scroll, corner_radius=8, border_width=1)
        card.pack(fill="x", pady=6, padx=4)
        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=10, pady=(8, 2))
        enabled = ctk.CTkSwitch(top, text="启用")
        enabled.pack(side="left")
        if server.get("enabled", True):
            enabled.select()
        ctk.CTkButton(top, text="删除", width=60, fg_color=("red", "#B33"), command=lambda: self._remove_row(card)).pack(side="right")

        def field(label, key, value):
            row = ctk.CTkFrame(card, fg_color="transparent")
            row.pack(fill="x", padx=10, pady=2)
            ctk.CTkLabel(row, text=label, width=80, anchor="w").pack(side="left")
            e = ctk.CTkEntry(row)
            e.pack(side="left", fill="x", expand=True)
            e.insert(0, str(value))
            return e

        widgets = {
            "card": card, "enabled": enabled,
            "id": field("ID", "id", server.get("id", "")),
            "name": field("名称", "name", server.get("name", "")),
            "command": field("命令", "command", server.get("command", "python")),
            "args": field("参数", "args", ", ".join(server.get("args", []))),
            "cwd": field("工作目录", "cwd", server.get("cwd", "")),
        }
        self.rows.append(widgets)

    def _remove_row(self, card):
        card.destroy()
        self.rows = [r for r in self.rows if r["card"] is not card]

    def _reload(self):
        self._load()
        self.app.agent.reload_config()
        self.app.notify("MCP 配置已重新载入")

    def save(self):
        servers = []
        existing = {}
        for srv in self.app.config.load("mcp_servers.json").get("servers", []):
            existing[srv.get("id", "")] = srv
        for r in self.rows:
            sid = r["id"].get().strip()
            if not sid:
                continue
            prev = existing.get(sid, {})
            servers.append({
                "id": sid,
                "name": r["name"].get().strip(),
                "command": r["command"].get().strip() or "python",
                "args": parse_list(r["args"].get()),
                "cwd": r["cwd"].get().strip(),
                "env": prev.get("env", {}),
                "enabled": bool(r["enabled"].get()),
                "auto_start": prev.get("auto_start", True),
            })
        data = self.app.config.load("mcp_servers.json")
        data["servers"] = servers
        self.app.config.save("mcp_servers.json", data)
        self.app.agent.reload_config()
        self.app.notify("MCP 配置已保存")