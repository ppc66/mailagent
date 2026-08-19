"""设置中心：邮件 / 白名单 / 大模型 / 权限 / 系统 五个选项卡（美化重构版）。"""
import csv
import imaplib
import smtplib
import ssl
import threading
from tkinter import filedialog

import customtkinter as ctk

from store import parse_list, format_list

FONT_TITLE = ("Microsoft YaHei", 14, "bold")
FONT_BODY = ("Microsoft YaHei", 12)
PRIMARY = ("#3a7ebf", "#1f538d")
PRIMARY_HOVER = ("#2f6a9a", "#17405f")
DANGER = ("#e74c3c", "#c0392b")
DANGER_HOVER = ("#c0392b", "#96281b")


class SettingsPage(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, corner_radius=0)
        self.app = app
        self.entries: dict[str, ctk.CTkEntry] = {}
        self.switches: dict[str, ctk.CTkSwitch] = {}
        self.options: dict[str, ctk.CTkOptionMenu] = {}
        self.sliders: dict[str, ctk.CTkSlider] = {}
        self.slider_labels: dict[str, ctk.CTkLabel] = {}
        self.areas: dict[str, ctk.CTkTextbox] = {}
        self._list_rows: dict[str, list[dict]] = {}
        self._list_add_entry: dict[str, ctk.CTkEntry] = {}
        self._list_meta: dict[str, dict] = {}
        self.provider_rows: list[dict] = []
        self.test_result: ctk.CTkLabel | None = None
        self.sections: dict[str, ctk.CTkFrame] = {}

        self.title_label = ctk.CTkLabel(self, text="", font=("Microsoft YaHei", 22, "bold"))
        self.title_label.pack(anchor="w", padx=26, pady=(22, 10))
        self.body = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.body.pack(fill="both", expand=True, padx=26, pady=(0, 6))

        self._build_email()
        self._build_whitelist()
        self._build_llm()
        self._build_permissions()
        self._build_system()
        self._build_action_bar()
        self.show_section("email")

    def _section(self, key: str) -> ctk.CTkFrame:
        frame = ctk.CTkScrollableFrame(self.body)
        self.sections[key] = frame
        return frame

    def show_section(self, key: str):
        titles = {"email": "邮件设置", "whitelist": "白名单", "llm": "大模型", "permissions": "权限", "system": "系统设置"}
        for k, frame in self.sections.items():
            if k == key:
                frame.pack(fill="both", expand=True)
            else:
                frame.pack_forget()
        self.title_label.configure(text=titles.get(key, "设置"))

    def _group(self, parent, title):
        frame = ctk.CTkFrame(parent, corner_radius=15, border_width=2, border_color=PRIMARY)
        frame.pack(fill="x", padx=20, pady=(12, 4))
        ctk.CTkLabel(frame, text=title, font=FONT_TITLE).pack(anchor="w", padx=16, pady=(12, 4))
        return frame

    def _row(self, parent):
        r = ctk.CTkFrame(parent, fg_color="transparent")
        r.pack(fill="x", padx=16, pady=5)
        return r

    def _entry(self, parent, label, key, value="", placeholder="", numeric=False, show=None):
        row = self._row(parent)
        ctk.CTkLabel(row, text=label, width=160, anchor="w", font=FONT_BODY).pack(side="left", padx=(0, 10))
        e = ctk.CTkEntry(row, placeholder_text=placeholder, height=32, font=FONT_BODY, show=show)
        e.pack(side="left", fill="x", expand=True)
        e.insert(0, str(value))
        if numeric:
            e.bind("<KeyRelease>", lambda ev, w=e: self._filter_digits(w))
        self.entries[key] = e
        return e

    @staticmethod
    def _filter_digits(entry):
        text = entry.get()
        filtered = "".join(ch for ch in text if ch.isdigit())
        if filtered != text:
            entry.delete(0, "end")
            entry.insert(0, filtered)

    def _switch(self, parent, label, key, value=False):
        row = self._row(parent)
        ctk.CTkLabel(row, text=label, width=160, anchor="w", font=FONT_BODY).pack(side="left", padx=(0, 10))
        s = ctk.CTkSwitch(row, text="")
        s.pack(side="left")
        if value:
            s.select()
        self.switches[key] = s
        return s

    def _option(self, parent, label, key, values, value):
        row = self._row(parent)
        ctk.CTkLabel(row, text=label, width=160, anchor="w", font=FONT_BODY).pack(side="left", padx=(0, 10))
        cb = ctk.CTkOptionMenu(row, values=values, width=280, font=FONT_BODY)
        if value in values:
            cb.set(value)
        cb.pack(side="left")
        self.options[key] = cb
        return cb

    def _slider_row(self, parent, label, key, value, from_, to, steps=None, fmt="int"):
        row = self._row(parent)
        ctk.CTkLabel(row, text=label, width=160, anchor="w", font=FONT_BODY).pack(side="left", padx=(0, 10))
        s = ctk.CTkSlider(row, from_=from_, to=to, number_of_steps=steps, command=lambda v: self._update_slider(key))
        s.pack(side="left", fill="x", expand=True, padx=(0, 10))
        s.set(value)
        lbl = ctk.CTkLabel(row, text=self._fmt_slider(value, fmt), width=70, font=FONT_BODY)
        lbl.pack(side="left")
        self.sliders[key] = s
        self.slider_labels[key] = lbl

    @staticmethod
    def _fmt_slider(v, fmt):
        if fmt == "float":
            return f"{float(v):.1f}"
        return str(int(round(float(v))))

    def _update_slider(self, key):
        v = self.sliders[key].get()
        fmt = getattr(self, "_slider_fmt", {}).get(key, "int")
        self.slider_labels[key].configure(text=self._fmt_slider(v, fmt))

    def _path_entry(self, parent, label, key, value="", directory=True):
        row = self._row(parent)
        ctk.CTkLabel(row, text=label, width=160, anchor="w", font=FONT_BODY).pack(side="left", padx=(0, 10))
        e = ctk.CTkEntry(row, height=32, font=FONT_BODY)
        e.pack(side="left", fill="x", expand=True, padx=(0, 8))
        e.insert(0, str(value))
        self.entries[key] = e

        def browse():
            if directory:
                p = filedialog.askdirectory()
            else:
                p = filedialog.askopenfilename()
            if p:
                e.delete(0, "end")
                e.insert(0, p)

        ctk.CTkButton(row, text="浏览", width=70, command=browse).pack(side="left")
        return e

    def _area(self, parent, label, key, text="", height=150):
        ctk.CTkLabel(parent, text=label, anchor="w", font=FONT_BODY).pack(fill="x", padx=16, pady=(10, 2))
        box = ctk.CTkTextbox(parent, height=height, font=FONT_BODY)
        box.pack(fill="x", padx=16, pady=(0, 4))
        box.insert("1.0", text)
        self.areas[key] = box
        return box

    def _build_list_group(self, parent, title, key, items, add_placeholder, with_switch=False, browse=False):
        group = self._group(parent, title)
        box = ctk.CTkFrame(group, fg_color="transparent")
        box.pack(fill="x", padx=16, pady=(6, 6))
        self._list_meta[key] = {"box": box, "with_switch": with_switch}
        self._list_rows[key] = []
        for it in items:
            if with_switch:
                self._list_add_row(key, it[0], enabled=it[1])
            else:
                self._list_add_row(key, it, enabled=True)
        addrow = ctk.CTkFrame(group, fg_color="transparent")
        addrow.pack(fill="x", padx=16, pady=(0, 12))
        entry = ctk.CTkEntry(addrow, placeholder_text=add_placeholder, height=30, font=FONT_BODY)
        entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self._list_add_entry[key] = entry
        if browse:
            def pick():
                p = filedialog.askdirectory()
                if p:
                    entry.delete(0, "end")
                    entry.insert(0, p)
            ctk.CTkButton(addrow, text="浏览", width=70, command=pick).pack(side="left", padx=(0, 8))
        ctk.CTkButton(addrow, text="添加", width=70, command=lambda k=key: self._list_add_from_entry(k)).pack(side="left")
        return group

    def _list_add_from_entry(self, key):
        entry = self._list_add_entry.get(key)
        if not entry:
            return
        value = entry.get().strip()
        if not value:
            return
        self._list_add_row(key, value, enabled=True)
        entry.delete(0, "end")

    def _list_add_row(self, key, value, enabled=True):
        meta = self._list_meta.get(key, {})
        container = meta.get("box")
        if container is None:
            return
        with_switch = meta.get("with_switch", False)
        row = ctk.CTkFrame(container, corner_radius=8, border_width=1)
        row.pack(fill="x", pady=2)
        switch = None
        if with_switch:
            ctk.CTkLabel(row, text=value, anchor="w", font=FONT_BODY).pack(side="left", fill="x", expand=True, padx=10)
            switch = ctk.CTkSwitch(row, text="")
            switch.pack(side="left", padx=6)
            if enabled:
                switch.select()
        else:
            ctk.CTkLabel(row, text=value, anchor="w", font=FONT_BODY).pack(side="left", fill="x", expand=True, padx=10)

        def rm(r=row):
            r.destroy()
            idx = next((i for i, x in enumerate(self._list_rows[key]) if x["frame"] is r), None)
            if idx is not None:
                self._list_rows[key].pop(idx)

        ctk.CTkButton(row, text="删除", width=56, fg_color=DANGER, hover_color=DANGER_HOVER, command=rm).pack(side="left", padx=6, pady=4)
        self._list_rows[key].append({"frame": row, "value": value, "switch": switch})

    def _build_email(self):
        frame = self._section("email")
        cfg = self.app.config.load("email.json")
        sec = self.app.secrets.load()
        g = self._group(frame, "IMAP 设置")
        self._entry(g, "IMAP 服务器", "imap_server", cfg.get("imap_server", ""), "例如: imap.qq.com")
        self._entry(g, "IMAP 端口", "imap_port", cfg.get("imap_port", 993), "993", numeric=True)
        self._switch(g, "启用 SSL", "imap_ssl", cfg.get("imap_ssl", True))
        self._entry(g, "邮箱账号", "email_account", cfg.get("email_account", ""), "your_email@example.com")
        self._entry(g, "邮箱密码/授权码", "email_password", sec.get("email_password", ""), show="*")
        g = self._group(frame, "SMTP 设置")
        self._entry(g, "SMTP 服务器", "smtp_server", cfg.get("smtp_server", ""), "例如: smtp.qq.com")
        self._entry(g, "SMTP 端口", "smtp_port", cfg.get("smtp_port", 587), "587", numeric=True)
        self._switch(g, "启用 TLS", "smtp_tls", cfg.get("smtp_tls", True))
        self._entry(g, "SMTP 密码/授权码", "smtp_password", sec.get("smtp_password", ""), show="*")
        g = self._group(frame, "轮询与附件")
        self._entry(g, "轮询间隔", "polling_interval", cfg.get("polling_interval", 30), "单位: 秒", numeric=True)
        self._switch(g, "启用 IDLE 实时推送", "use_idle", cfg.get("use_idle", True))
        self._entry(g, "每次轮询最大邮件数", "max_emails_per_poll", cfg.get("max_emails_per_poll", 5), numeric=True)
        self._entry(g, "附件最大大小", "max_attachment_size_mb", cfg.get("max_attachment_size_mb", 50), "单位: MB", numeric=True)
        self._entry(g, "每封最多附件数", "max_attachments_per_email", cfg.get("max_attachments_per_email", 10), numeric=True)
        self._entry(g, "临时目录清理", "temp_cleanup_hours", cfg.get("temp_cleanup_hours", 24), "单位: 小时", numeric=True)
        self._path_entry(g, "临时目录", "temp_dir", cfg.get("temp_dir", ""))
        g = self._group(frame, "连接测试")
        row = self._row(g)
        self.test_button = ctk.CTkButton(row, text="测试连接", fg_color=PRIMARY, hover_color=PRIMARY_HOVER, command=self._test_connection)
        self.test_button.pack(side="left", padx=(4, 12))
        self.test_result = ctk.CTkLabel(row, text="", font=FONT_BODY)
        self.test_result.pack(side="left")

    def _test_connection(self):
        self.test_button.configure(text="连接中...", state="disabled")
        if self.test_result:
            self.test_result.configure(text="")

        def run():
            errors = []
            try:
                server = self.entries["imap_server"].get().strip()
                port = int(self.entries["imap_port"].get() or 993)
                account = self.entries["email_account"].get().strip()
                password = self.entries["email_password"].get()
                im = imaplib.IMAP4_SSL(server, port) if self._get_bool("imap_ssl") else imaplib.IMAP4(server, port)
                im.login(account, password)
                im.logout()
            except Exception as e:
                errors.append(f"IMAP: {e}")
            try:
                server = self.entries["smtp_server"].get().strip()
                port = int(self.entries["smtp_port"].get() or 587)
                account = self.entries["email_account"].get().strip()
                password = self.entries["smtp_password"].get() or self.entries["email_password"].get()
                if port == 465 or not self._get_bool("smtp_tls"):
                    sm = smtplib.SMTP_SSL(server, port, timeout=15)
                else:
                    sm = smtplib.SMTP(server, port, timeout=15)
                    sm.starttls(context=ssl.create_default_context())
                sm.login(account, password)
                sm.quit()
            except Exception as e:
                errors.append(f"SMTP: {e}")

            def done():
                self.test_button.configure(text="测试连接", state="normal")
                if self.test_result:
                    if errors:
                        self.test_result.configure(text="失败: " + "; ".join(errors), text_color=("red", "red"))
                    else:
                        self.test_result.configure(text="连接成功", text_color=("green", "green"))
            self.after(0, done)

        threading.Thread(target=run, daemon=True).start()

    def _build_whitelist(self):
        frame = self._section("whitelist")
        cfg = self.app.config.load("whitelist.json")
        emails = cfg.get("emails", [])
        disabled = cfg.get("disabled", [])
        items = [(a, True) for a in emails] + [(a, False) for a in disabled]
        self._build_list_group(frame, "白名单（允许/禁用的邮箱）", "whitelist", items, "输入邮箱地址后点击添加", with_switch=True)
        ops = ctk.CTkFrame(frame, fg_color="transparent")
        ops.pack(fill="x", padx=20, pady=(4, 8))
        ctk.CTkButton(ops, text="导入 CSV", width=100, command=lambda: self._import_whitelist_csv()).pack(side="left", padx=(0, 8))
        ctk.CTkButton(ops, text="导出 CSV", width=100, command=lambda: self._export_whitelist_csv()).pack(side="left")

    def _import_whitelist_csv(self):
        path = filedialog.askopenfilename(filetypes=[("CSV 文件", "*.csv")])
        if not path:
            return
        addrs = []
        with open(path, "r", encoding="utf-8-sig") as f:
            for row in csv.reader(f):
                for cell in row:
                    cell = cell.strip()
                    if cell:
                        addrs.append(cell)
        for a in addrs:
            self._list_add_row("whitelist", a, enabled=True)
        self.app.notify(f"已导入 {len(addrs)} 个邮箱")

    def _export_whitelist_csv(self):
        rows = self._list_rows.get("whitelist", [])
        if not rows:
            self.app.notify("白名单为空")
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV 文件", "*.csv")])
        if not path:
            return
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            for r in rows:
                w.writerow([r["value"]])
        self.app.notify("已导出白名单")

    def _build_llm(self):
        frame = self._section("llm")
        cfg = self.app.config.load("llm.json")
        sec = self.app.secrets.load()
        self.providers_cfg = cfg.get("providers", [])
        ids = [p.get("id", "") for p in self.providers_cfg]
        active = cfg.get("active_provider", ids[0] if ids else "")
        self._option(frame, "当前模型", "active_provider", ids, active)
        self.options["active_provider"].configure(command=self._on_active_provider_change)
        g = self._group(frame, "提供商列表")
        ctk.CTkButton(g, text="添加提供商", width=110, command=self._provider_add_row).pack(anchor="w", padx=16, pady=(0, 8))
        self._provider_box = ctk.CTkFrame(g, fg_color="transparent")
        self._provider_box.pack(fill="x", padx=16, pady=(0, 12))
        for p in self.providers_cfg:
            self._provider_add_row(p)
        g = self._group(frame, "模型参数（当前提供商）")
        active_provider = next((p for p in self.providers_cfg if p.get("id") == active), {})
        self._slider_fmt = {"max_tokens": "int", "temperature": "float"}
        self._slider_row(g, "Max Tokens", "max_tokens", active_provider.get("max_tokens", 4096), 256, 32768)
        self._slider_row(g, "Temperature", "temperature", active_provider.get("temperature", 0.7), 0.0, 2.0, steps=20, fmt="float")
        self._entry(g, "超时(秒)", "timeout", active_provider.get("timeout", 60), numeric=True)
        api_keys = sec.get("api_keys", {}) or {}
        self._entry(g, "API Key", "api_key", api_keys.get(active, ""), show="*")
        g = self._group(frame, "任务预算")
        self._entry(g, "单任务 Token 上限", "max_total_tokens_per_task", cfg.get("max_total_tokens_per_task", 8000), numeric=True)
        self._entry(g, "最大 LLM 调用次数", "max_llm_calls_per_task", cfg.get("max_llm_calls_per_task", 10), numeric=True)
        self._area(frame, "系统提示词", "system_prompt", cfg.get("system_prompt", ""), height=120)

    def _provider_add_row(self, provider: dict | None = None):
        provider = provider or {}
        row = ctk.CTkFrame(self._provider_box, corner_radius=10, border_width=1)
        row.pack(fill="x", pady=4)

        def f(label, key, val):
            r = self._row(row)
            ctk.CTkLabel(r, text=label, width=70, anchor="w", font=FONT_BODY).pack(side="left", padx=(0, 8))
            e = ctk.CTkEntry(r, height=28, font=FONT_BODY)
            e.pack(side="left", fill="x", expand=True)
            e.insert(0, str(val))
            return e

        widgets = {
            "frame": row, "orig_id": provider.get("id", ""),
            "id": f("ID", "id", provider.get("id", "")),
            "name": f("名称", "name", provider.get("name", "")),
            "model": f("模型", "model_name", provider.get("model_name", "")),
            "base": f("API 地址", "api_base", provider.get("api_base", "")),
        }
        btns = ctk.CTkFrame(row, fg_color="transparent")
        btns.pack(fill="x", padx=10, pady=(0, 8))
        ctk.CTkButton(btns, text="设为激活", width=90, command=lambda w=widgets: self._provider_set_active(w)).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btns, text="删除", width=70, fg_color=DANGER, hover_color=DANGER_HOVER, command=lambda w=widgets: self._provider_remove(w)).pack(side="left")
        self.provider_rows.append(widgets)

    def _provider_remove(self, widgets):
        widgets["frame"].destroy()
        self.provider_rows = [r for r in self.provider_rows if r is not widgets]

    def _provider_set_active(self, widgets):
        pid = widgets["id"].get().strip()
        if not pid:
            return
        self.options["active_provider"].set(pid)
        self._on_active_provider_change(pid)

    def _on_active_provider_change(self, pid: str):
        provider = next((p for p in self.providers_cfg if p.get("id") == pid), {})
        if "max_tokens" in self.sliders:
            self.sliders["max_tokens"].set(provider.get("max_tokens", 4096))
        if "temperature" in self.sliders:
            self.sliders["temperature"].set(provider.get("temperature", 0.7))
        if "timeout" in self.entries:
            self.entries["timeout"].delete(0, "end")
            self.entries["timeout"].insert(0, str(provider.get("timeout", 60)))
        api_keys = self.app.secrets.load().get("api_keys", {}) or {}
        if "api_key" in self.entries:
            self.entries["api_key"].delete(0, "end")
            self.entries["api_key"].insert(0, api_keys.get(pid, ""))

    def _build_permissions(self):
        frame = self._section("permissions")
        cfg = self.app.config.load("permissions.json")
        self._build_list_group(frame, "命令白名单", "commands", cfg.get("allowed_commands", []), "输入命令后点击添加")
        self._build_list_group(frame, "工作目录沙盒", "workspace_dirs", cfg.get("workspace_dirs", []), "选择或输入目录", browse=True)
        g = self._group(frame, "权限控制")
        self._option(g, "沙盒模式", "sandbox_mode", ["global", "workspace", "custom"], cfg.get("sandbox_mode", "workspace"))
        self._area(g, "自定义目录（每行一个）", "custom_dirs", format_list(cfg.get("custom_dirs", [])), height=80)
        self._switch(g, "允许删除文件", "allow_delete", cfg.get("allow_delete", False))
        self._area(g, "高风险操作（每行一个）", "high_risk_actions", format_list(cfg.get("high_risk_actions", ["delete"])), height=80)
        self._switch(g, "允许发送给非白名单邮箱", "allow_send_to_non_whitelist", cfg.get("allow_send_to_non_whitelist", False))
        self._entry(g, "命令超时(秒)", "command_timeout", cfg.get("command_timeout", 30), numeric=True)
        self._entry(g, "确认等待超时(秒)", "confirm_timeout_seconds", cfg.get("confirm_timeout_seconds", 300), numeric=True)
        self._entry(g, "每分钟限频(条)", "rate_limit_per_minute", cfg.get("rate_limit_per_minute", 5), numeric=True)

    def _build_system(self):
        frame = self._section("system")
        cfg = self.app.config.load("system.json")
        g = self._group(frame, "外观与语言")
        self._option(g, "主题模式", "theme", ["dark", "light", "system"], cfg.get("theme", "dark"))
        self._option(g, "语言", "language", ["zh-CN", "en-US"], cfg.get("language", "zh-CN"))
        g = self._group(frame, "日志")
        self._option(g, "日志级别", "log_level", ["DEBUG", "INFO", "WARNING", "ERROR"], cfg.get("log_level", "INFO"))
        self._entry(g, "日志保留天数", "log_retention_days", cfg.get("log_retention_days", 30), numeric=True)
        self._entry(g, "单日志文件上限(MB)", "max_log_file_size_mb", cfg.get("max_log_file_size_mb", 50), numeric=True)
        g = self._group(frame, "操作")
        row = self._row(g)
        ctk.CTkButton(row, text="清空日志", fg_color=DANGER, hover_color=DANGER_HOVER, command=self._clear_logs).pack(side="left", padx=(8, 10))
        ctk.CTkButton(row, text="打开配置目录", command=self._open_config_dir).pack(side="left")

    def _clear_logs(self):
        import glob
        import os
        from store import LOG_DIR
        for p in glob.glob(os.path.join(LOG_DIR, "*.jsonl")):
            try:
                os.remove(p)
            except OSError:
                pass
        self.app.notify("日志已清空")

    def _open_config_dir(self):
        import os
        from store import CONFIG_DIR
        os.startfile(CONFIG_DIR)

    def _build_action_bar(self):
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=26, pady=(4, 14))
        self.status_label = ctk.CTkLabel(bar, text="", font=FONT_BODY)
        self.status_label.pack(side="left", padx=(4, 0))
        ctk.CTkButton(bar, text="保存设置", width=120, height=36, fg_color=PRIMARY, hover_color=PRIMARY_HOVER, command=self.save_all).pack(side="right")

    def _set_status(self, text, color=None):
        self.status_label.configure(text=text, text_color=color or ("gray", "gray"))
        self.after(3000, lambda: self.status_label.configure(text=""))

    def _get(self, key: str) -> str:
        e = self.entries.get(key)
        return e.get().strip() if e else ""

    def _get_int(self, key: str, default=0) -> int:
        try:
            return int(self._get(key))
        except ValueError:
            return default

    def _get_bool(self, key: str) -> bool:
        s = self.switches.get(key)
        return bool(s.get()) if s else False

    def save_all(self):
        self._save_email()
        self._save_whitelist()
        self._save_llm()
        self._save_permissions()
        self._save_system()
        self.app.apply_theme()
        self._set_status("✓ 配置已保存", ("green", "green"))

    def _save_email(self):
        data = self.app.config.load("email.json")
        data["imap_server"] = self._get("imap_server")
        data["imap_port"] = self._get_int("imap_port", 993)
        data["imap_ssl"] = self._get_bool("imap_ssl")
        data["smtp_server"] = self._get("smtp_server")
        data["smtp_port"] = self._get_int("smtp_port", 587)
        data["smtp_tls"] = self._get_bool("smtp_tls")
        data["email_account"] = self._get("email_account")
        data["polling_interval"] = self._get_int("polling_interval", 30)
        data["use_idle"] = self._get_bool("use_idle")
        data["max_emails_per_poll"] = self._get_int("max_emails_per_poll", 5)
        data["max_attachment_size_mb"] = self._get_int("max_attachment_size_mb", 50)
        data["max_attachments_per_email"] = self._get_int("max_attachments_per_email", 10)
        data["temp_cleanup_hours"] = self._get_int("temp_cleanup_hours", 24)
        data["temp_dir"] = self._get("temp_dir")
        self.app.config.save("email.json", data)
        sec = self.app.secrets.load()
        sec["email_password"] = self._get("email_password")
        sec["smtp_password"] = self._get("smtp_password")
        self.app.secrets.save(sec)

    def _save_whitelist(self):
        emails, disabled = [], []
        for r in self._list_rows.get("whitelist", []):
            if r["switch"] and bool(r["switch"].get()):
                emails.append(r["value"])
            else:
                disabled.append(r["value"])
        data = self.app.config.load("whitelist.json")
        data["emails"] = emails
        data["disabled"] = disabled
        self.app.config.save("whitelist.json", data)

    def _save_llm(self):
        data = self.app.config.load("llm.json")
        active = self.options["active_provider"].get()
        data["active_provider"] = active
        data["max_total_tokens_per_task"] = self._get_int("max_total_tokens_per_task", 8000)
        data["max_llm_calls_per_task"] = self._get_int("max_llm_calls_per_task", 10)
        data["system_prompt"] = self.areas["system_prompt"].get("1.0", "end").strip()
        existing = {p.get("id"): p for p in self.providers_cfg}
        new_providers = []
        for row in self.provider_rows:
            pid = row["id"].get().strip()
            if not pid:
                continue
            prev = existing.get(row["orig_id"], {})
            provider = {
                "id": pid,
                "name": row["name"].get().strip(),
                "model_name": row["model"].get().strip(),
                "api_base": row["base"].get().strip(),
                "max_tokens": prev.get("max_tokens", 4096),
                "temperature": prev.get("temperature", 0.7),
                "timeout": prev.get("timeout", 60),
            }
            if pid == active:
                provider["max_tokens"] = int(self.sliders["max_tokens"].get())
                provider["temperature"] = round(float(self.sliders["temperature"].get()), 2)
                provider["timeout"] = self._get_int("timeout", 60)
            new_providers.append(provider)
        data["providers"] = new_providers
        self.app.config.save("llm.json", data)
        sec = self.app.secrets.load()
        api_keys = sec.get("api_keys", {}) or {}
        api_keys[active] = self._get("api_key")
        sec["api_keys"] = api_keys
        self.app.secrets.save(sec)

    def _save_permissions(self):
        data = self.app.config.load("permissions.json")
        data["allowed_commands"] = [r["value"] for r in self._list_rows.get("commands", [])]
        data["workspace_dirs"] = [r["value"] for r in self._list_rows.get("workspace_dirs", [])]
        data["sandbox_mode"] = self.options["sandbox_mode"].get()
        data["custom_dirs"] = parse_list(self.areas["custom_dirs"].get("1.0", "end"))
        data["allow_delete"] = self._get_bool("allow_delete")
        data["high_risk_actions"] = parse_list(self.areas["high_risk_actions"].get("1.0", "end"))
        data["allow_send_to_non_whitelist"] = self._get_bool("allow_send_to_non_whitelist")
        data["command_timeout"] = self._get_int("command_timeout", 30)
        data["confirm_timeout_seconds"] = self._get_int("confirm_timeout_seconds", 300)
        data["rate_limit_per_minute"] = self._get_int("rate_limit_per_minute", 5)
        self.app.config.save("permissions.json", data)

    def _save_system(self):
        data = self.app.config.load("system.json")
        data["theme"] = self.options["theme"].get()
        data["log_level"] = self.options["log_level"].get()
        data["log_retention_days"] = self._get_int("log_retention_days", 30)
        data["max_log_file_size_mb"] = self._get_int("max_log_file_size_mb", 50)
        data["language"] = self.options["language"].get()
        self.app.config.save("system.json", data)