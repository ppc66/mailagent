"""历史问答页：按时间范围筛选展示提问与回复记录（日期选择组件）。"""
import glob
import json
import os
from datetime import datetime, timedelta

import customtkinter as ctk
from tkcalendar import DateEntry

from store import LOG_DIR


class HistoryPage(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, corner_radius=0)
        self.app = app
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=26, pady=(22, 8))
        ctk.CTkLabel(head, text="历史问答", font=("Microsoft YaHei", 22, "bold")).pack(side="left")
        ctk.CTkButton(head, text="刷新", width=80, command=self.refresh).pack(side="right")
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=26, pady=(0, 8))
        ctk.CTkLabel(bar, text="时间范围").pack(side="left", padx=(0, 8))
        self.range_menu = ctk.CTkOptionMenu(bar, values=["全部", "今天", "三天内", "近一周", "近一月", "自定义"], width=120, command=lambda _: self.refresh())
        self.range_menu.pack(side="left", padx=(0, 16))
        ctk.CTkLabel(bar, text="从").pack(side="left", padx=(0, 6))
        self.start_entry = DateEntry(bar, date_pattern="yyyy-mm-dd", width=12, locale="zh_CN", background="darkblue", foreground="white", borderwidth=1)
        self.start_entry.pack(side="left", padx=(0, 10))
        ctk.CTkLabel(bar, text="到").pack(side="left", padx=(0, 6))
        self.end_entry = DateEntry(bar, date_pattern="yyyy-mm-dd", width=12, locale="zh_CN", background="darkblue", foreground="white", borderwidth=1)
        self.end_entry.pack(side="left", padx=(0, 12))
        ctk.CTkButton(bar, text="查询", width=70, command=self.refresh).pack(side="left")
        self.box = ctk.CTkScrollableFrame(self)
        self.box.pack(fill="both", expand=True, padx=26, pady=(0, 16))
        self.refresh()

    def _read(self):
        history_dir = os.path.join(LOG_DIR, "history")
        files = sorted(glob.glob(os.path.join(history_dir, "*.jsonl")))
        records = []
        for path in files:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            records.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
            except OSError:
                continue
        records.sort(key=lambda r: r.get("received_at", ""), reverse=True)
        return records

    @staticmethod
    def _parse_ts(value):
        try:
            return datetime.fromisoformat(str(value))
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _combine(d):
        return datetime.combine(d, datetime.min.time())

    def _range(self):
        preset = self.range_menu.get()
        now = datetime.now()
        if preset == "今天":
            return now.replace(hour=0, minute=0, second=0, microsecond=0), now
        if preset == "三天内":
            return now - timedelta(days=3), now
        if preset == "近一周":
            return now - timedelta(days=7), now
        if preset == "近一月":
            return now - timedelta(days=30), now
        if preset == "自定义":
            lo = self._combine(self.start_entry.get_date())
            hi = self._combine(self.end_entry.get_date()) + timedelta(days=1)
            return lo, hi
        return None, None

    def refresh(self):
        for child in self.box.winfo_children():
            child.destroy()
        lo, hi = self._range()
        filtered = []
        for rec in self._read():
            dt = self._parse_ts(rec.get("received_at"))
            if dt is None:
                continue
            if lo is not None and dt < lo:
                continue
            if hi is not None and dt > hi:
                continue
            filtered.append(rec)
        if not filtered:
            ctk.CTkLabel(self.box, text="该时间范围内暂无记录", text_color=("gray", "gray")).pack(pady=40)
            return
        for rec in filtered:
            self._render_record(rec)

    def _render_record(self, rec):
        card = ctk.CTkFrame(self.box, corner_radius=12, border_width=1)
        card.pack(fill="x", pady=6)
        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=14, pady=(10, 4))
        ctk.CTkLabel(header, text=rec.get("sender", ""), font=("Microsoft YaHei", 13, "bold")).pack(side="left")
        time_text = f"收到 {rec.get('received_at', '')} · 回复 {rec.get('replied_at', '')}"
        ctk.CTkLabel(header, text=time_text, text_color=("gray50", "gray70")).pack(side="right")
        q = ctk.CTkLabel(card, text="问：" + str(rec.get("instruction", "")), anchor="w", font=("Microsoft YaHei", 13), justify="left", wraplength=760)
        q.pack(fill="x", padx=14, pady=(2, 4))
        a = ctk.CTkLabel(card, text="答：" + str(rec.get("reply", "")), anchor="w", font=("Microsoft YaHei", 13), justify="left", wraplength=760, text_color=("gray20", "gray90"))
        a.pack(fill="x", padx=14, pady=(0, 12))