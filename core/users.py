"""Botdan foydalangan foydalanuvchilarni yozib borish (statistika uchun).

Ma'lumot `USAGE_FILE` (standart: data/usage.json) faylida saqlanadi.
data/ papkasi .gitignore da — GitHub'ga tushmaydi.

Diqqat: bu fayl Telegram bergan ma'lumotlardan iborat (id, ism, username).
Uni uchinchi shaxslarga tarqatmang va o'chirib yuborish imkonini qoldiring.
"""
from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_lock = threading.Lock()
_cache: dict | None = None


def _path() -> Path:
    p = Path(os.getenv("USAGE_FILE", "data/usage.json"))
    if not p.is_absolute():
        p = ROOT / p
    return p


def _load() -> dict:
    global _cache
    if _cache is None:
        p = _path()
        try:
            _cache = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
        except (OSError, ValueError):
            _cache = {}
    return _cache


def _save(data: dict) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)


def record(user) -> None:
    """Har bir xabarda foydalanuvchi yozuvini yangilaydi (xato bo'lsa jim o'tadi)."""
    if user is None:
        return
    try:
        with _lock:
            data = _load()
            key = str(user.id)
            now = datetime.now().isoformat(timespec="seconds")
            row = data.get(key) or {"first_seen": now, "messages": 0}
            row.update({
                "username": user.username or "",
                "name": " ".join(x for x in (user.first_name, user.last_name) if x),
                "lang": getattr(user, "language_code", "") or "",
                "last_seen": now,
            })
            row["messages"] = int(row.get("messages", 0)) + 1
            data[key] = row
            _save(data)
    except Exception:  # statistika hech qachon botni to'xtatmasin
        pass


def summary() -> dict:
    """{"users": N, "messages": M, "rows": {id: {...}}}"""
    data = _load()
    return {
        "users": len(data),
        "messages": sum(int(r.get("messages", 0)) for r in data.values()),
        "rows": data,
    }


def is_admin(user_id: int | None) -> bool:
    """ADMIN_ID muhit o'zgaruvchisida sanab o'tilgan id larmi (vergul yoki bo'sh joy bilan)."""
    if user_id is None:
        return False
    raw = os.getenv("ADMIN_ID", "")
    ids = {int(x) for x in re.split(r"[,\s]+", raw) if x.strip().isdigit()}
    return user_id in ids
