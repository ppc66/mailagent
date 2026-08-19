"""邮件监听器：IMAP over SSL，支持 IDLE 实时推送与轮询兜底，指数退避重连，白名单校验。"""
import email
import email.header
import imaplib
import json
import os
import re
import threading
import time
from collections import defaultdict, deque
from email.utils import parseaddr
from typing import Callable, Optional

from logger import logger

TOKEN_RE = re.compile(r"\[Token\s*:\s*([^\]]+)\]", re.IGNORECASE)
HTML_TAG_RE = re.compile(r"<[^>]+>")
IDLE_AVAILABLE = hasattr(imaplib.IMAP4, "idle")
BACKOFF_SEQ = [1, 2, 4, 8, 16, 30]


def _decode_header(value: str) -> str:
    if not value:
        return ""
    parts = email.header.decode_header(value)
    out = []
    for text, charset in parts:
        if isinstance(text, bytes):
            out.append(text.decode(charset or "utf-8", errors="replace"))
        else:
            out.append(text)
    return "".join(out)


def _extract_addr(header_value: str) -> str:
    return parseaddr(header_value)[1].lower()


class MailListener:
    def __init__(self, config_manager, secrets: dict,
                 on_instruction: Callable[[str, str, list[str]], None]):
        self._cfg = config_manager
        self._secrets = secrets
        self._on_instruction = on_instruction
        self._imap: Optional[imaplib.IMAP4_SSL] = None
        self._stop = threading.Event()
        self._connected = threading.Event()
        self._rate: dict[str, deque] = defaultdict(deque)
        self._uid_next = 0
        logs_dir = os.path.join(os.path.dirname(config_manager.config_dir), "Logs")
        self._state_path = os.path.join(logs_dir, "mail_state.json")

    def _email_cfg(self) -> dict:
        return self._cfg.get_config("email.json")

    def _whitelist(self) -> dict:
        return self._cfg.get_config("whitelist.json")

    def is_connected(self) -> bool:
        return self._connected.is_set()

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def stop(self):
        self._stop.set()
        self._close()

    def reconnect(self):
        self._close()

    def _close(self):
        if self._imap:
            try:
                self._imap.logout()
            except Exception:
                pass
            self._imap = None
        self._connected.clear()

    def _run(self):
        while not self._stop.is_set():
            if self._connect():
                use_idle = self._email_cfg().get("use_idle", True)
                if use_idle and IDLE_AVAILABLE:
                    self._idle_loop()
                else:
                    if use_idle and not IDLE_AVAILABLE:
                        logger.warning("当前 imaplib 不支持 IDLE，回退到轮询模式")
                    self._poll_loop()
            self._close()
            if not self._stop.is_set():
                time.sleep(self._email_cfg().get("polling_interval", 30))

    def _connect(self) -> bool:
        cfg = self._email_cfg()
        account = cfg.get("email_account", "")
        password = self._secrets.get("email_password", "")
        if not account or not password:
            logger.warning("邮箱账号或密码未配置，监听器空闲")
            time.sleep(30)
            return False
        attempt = 0
        while not self._stop.is_set():
            try:
                if cfg.get("imap_ssl", True):
                    self._imap = imaplib.IMAP4_SSL(cfg.get("imap_server"), int(cfg.get("imap_port", 993)))
                else:
                    self._imap = imaplib.IMAP4(cfg.get("imap_server"), int(cfg.get("imap_port", 143)))
                self._imap.login(account, password)
                self._imap.select("INBOX")
                self._init_watermark()
                self._connected.set()
                logger.info("IMAP 连接成功")
                return True
            except Exception as e:
                self._close()
                delay = BACKOFF_SEQ[min(attempt, len(BACKOFF_SEQ) - 1)]
                logger.warning(f"IMAP 连接失败（第 {attempt + 1} 次），{delay}s 后重试: {e}")
                attempt += 1
                if attempt >= 10:
                    logger.error("连续 10 次 IMAP 重连失败")
                    return False
                time.sleep(delay)
        return False

    def _idle_loop(self):
        interval = float(self._email_cfg().get("polling_interval", 30))
        while not self._stop.is_set():
            try:
                self._imap.idle()
                self._imap.socket.settimeout(max(interval * 2, 30))
                try:
                    self._imap._get_response()
                except Exception:
                    pass
                self._imap.socket.settimeout(None)
                self._imap.send(b"DONE\r\n")
                self._process_unseen()
            except Exception:
                self._connected.clear()
                return

    def _poll_loop(self):
        interval = float(self._email_cfg().get("polling_interval", 30))
        while not self._stop.is_set():
            try:
                self._imap.noop()
                self._process_unseen()
            except Exception as e:
                logger.warning(f"轮询异常: {e}")
                self._connected.clear()
                return
            self._stop.wait(interval)

    def _init_watermark(self):
        if self._uid_next > 0:
            return
        saved = self._load_state().get("uid_next", 0)
        if saved:
            self._uid_next = saved
        else:
            try:
                _, data = self._imap.uid("search", None, "ALL")
                uids = [int(x) for x in data[0].split() if x]
                self._uid_next = (max(uids) + 1) if uids else 1
            except Exception:
                self._uid_next = 1
            self._save_state()

    def _load_state(self) -> dict:
        try:
            with open(self._state_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_state(self):
        try:
            os.makedirs(os.path.dirname(self._state_path), exist_ok=True)
            with open(self._state_path, "w", encoding="utf-8") as f:
                json.dump({"uid_next": self._uid_next}, f)
        except OSError:
            pass

    def _process_unseen(self):
        try:
            _, data = self._imap.uid("search", None, "UNSEEN")
        except Exception as e:
            logger.error(f"搜索未读邮件失败: {e}")
            return
        limit = int(self._email_cfg().get("max_emails_per_poll", 5))
        count = 0
        for uid in data[0].split():
            if self._stop.is_set():
                break
            uid_int = int(uid)
            if uid_int < self._uid_next:
                continue
            if count >= limit:
                break
            count += 1
            self._handle_message(uid)
        self._save_state()

    def _handle_message(self, uid: bytes):
        self._uid_next = int(uid) + 1
        try:
            _, data = self._imap.uid("fetch", uid, "(RFC822)")
            raw = data[0][1]
            msg = email.message_from_bytes(raw)
        except Exception as e:
            logger.error(f"拉取邮件失败: {e}")
            return
        sender = _extract_addr(msg.get("From", "") or "")
        if not self._check_whitelist(sender):
            logger.info(f"忽略非白名单发件人: {sender}")
            return
        if not self._check_rate(sender):
            logger.warning(f"发件人超频，忽略: {sender}")
            return
        instruction = self._extract_instruction(msg)
        if not instruction:
            logger.info("邮件不含有效指令")
            return
        attachments = self._download_attachments(msg)
        self._mark_seen(uid)
        logger.info(f"收到指令（来自 {sender}）：{instruction[:80]}")
        threading.Thread(target=self._on_instruction, args=(sender, instruction, attachments), daemon=True).start()

    def _check_whitelist(self, sender: str) -> bool:
        wl = self._whitelist()
        if sender in set(x.lower() for x in wl.get("disabled", [])):
            return False
        return sender in set(x.lower() for x in wl.get("emails", []))

    def _check_rate(self, sender: str) -> bool:
        limit = int(self._cfg.get("permissions.json", "rate_limit_per_minute", 5))
        now = time.time()
        q = self._rate[sender]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
        return True

    def _extract_instruction(self, msg) -> str:
        body = self._extract_body(msg)
        lines = [ln for ln in body.splitlines() if not ln.strip().startswith(">")]
        text = "\n".join(lines).strip()
        text = TOKEN_RE.sub("", text).strip()
        return text

    def _extract_body(self, msg) -> str:
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    return self._decode_payload(part)
            for part in msg.walk():
                if part.get_content_type() == "text/html":
                    html = self._decode_payload(part)
                    return HTML_TAG_RE.sub("", html)
            return ""
        return self._decode_payload(msg)

    def _decode_payload(self, part) -> str:
        try:
            payload = part.get_payload(decode=True)
            if payload is None:
                return ""
            charset = part.get_content_charset() or "utf-8"
            return payload.decode(charset, errors="replace")
        except Exception:
            return ""

    def _download_attachments(self, msg) -> list[str]:
        cfg = self._email_cfg()
        max_size = int(cfg.get("max_attachment_size_mb", 50)) * 1024 * 1024
        max_count = int(cfg.get("max_attachments_per_email", 10))
        temp_dir = (_expand_temp(cfg.get("temp_dir", "")) or os.environ.get("TEMP", "")) or "."
        os.makedirs(temp_dir, exist_ok=True)
        paths: list[str] = []
        if not msg.is_multipart():
            return paths
        for part in msg.walk():
            if len(paths) >= max_count:
                break
            filename = part.get_filename()
            if not filename:
                continue
            filename = _decode_header(filename)
            payload = part.get_payload(decode=True)
            if not payload or len(payload) > max_size:
                continue
            safe = os.path.basename(filename) or f"attachment_{len(paths)}"
            path = os.path.join(temp_dir, safe)
            with open(path, "wb") as f:
                f.write(payload)
            paths.append(path)
        return paths

    def _mark_seen(self, uid: bytes):
        try:
            self._imap.uid("store", uid, "+FLAGS", "\\Seen")
        except Exception:
            pass


def _expand_temp(path: str) -> str:
    if not path:
        return ""
    return os.path.expandvars(os.path.expanduser(path))