"""日志查看页：读取 Logs/*.jsonl，按级别/关键词过滤，自动刷新与导出。"""
import glob
import json
import os
from datetime import datetime

import customtkinter as ctk
from tkinter import filedialog

from store import LOG_DIR

LEVELS = ["ALL", "DEBUG", "INFO", "WARNING", "ERROR"]


class LogsPage(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, corner_radius=0)
        self.app = app
        self._lines: list[str] = []
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=26, pady=(22, 8))
        ctk.CTkLabel(head, text="日志查看", font=ctk.CTkFont(size=22, weight="bold")).pack(side="left")
        self.level = ctk.CTkComboBox(head, values=LEVELS, width=120)
        self.level.set("ALL")
        self.level.pack(side="left", padx=(20, 6))
        self.keyword = ctk.CTkEntry(head, placeholder_text="关键词过滤…", width=200)
        self.keyword.pack(side="left", padx=6)
        ctk.CTkButton(head, text="过滤", width=70, command=self._render).pack(side="left", padx=6)
        ctk.CTkButton(head, text="导出TXT", width=90, command=self._export).pack(side="left", padx=6)
        self.box = ctk.CTkTextbox(self, wrap="none", font=ctk.CTkFont(family="Consolas", size=12))
        self.box.pack(fill="both", expand=True, padx=26, pady=(0, 16))
        self.after(2000, self._auto_refresh)

    def _read_lines(self) -> list[str]:
        files = sorted(glob.glob(os.path.join(LOG_DIR, "*.jsonl")))
        out: list[str] = []
        for path in files[-2:]:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    out.extend(f.readlines())
            except OSError:
                continue
        return out

    def _filter(self, lines: list[str]) -> list[str]:
        level = self.level.get()
        kw = self.keyword.get().strip().lower()
        rank = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3}
        result = []
        for line in lines:
            if kw and kw not in line.lower():
                continue
            if level != "ALL":
                try:
                    lvl = json.loads(line).get("level", "")
                except json.JSONDecodeError:
                    lvl = ""
                if rank.get(lvl, -1) < rank[level]:
                    continue
            result.append(self._pretty(line))
        return result

    def _pretty(self, line: str) -> str:
        try:
            obj = json.loads(line)
            ts, lvl, msg = obj.get("timestamp", ""), obj.get("level", ""), obj.get("message", "")
            fields = obj.get("fields")
            text = f"{ts}  {lvl:<7}  {msg}"
            if fields:
                text += "  " + json.dumps(fields, ensure_ascii=False)
            return text
        except json.JSONDecodeError:
            return line

    def _render(self):
        self._lines = self._read_lines()
        filtered = self._filter(self._lines)
        self.box.delete("1.0", "end")
        self.box.insert("1.0", "\n".join(filtered[-2000:]))
        self.box.see("end")

    def _auto_refresh(self):
        self._render()
        self.after(3000, self._auto_refresh)

    def _export(self):
        filtered = self._filter(self._read_lines())
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            initialfile=f"mdla_logs_{datetime.now():%Y%m%d_%H%M%S}.txt",
            filetypes=[("文本文件", "*.txt")],
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(filtered))
            self.app.notify(f"已导出到 {path}")
        except OSError:
            self.app.notify("导出失败")