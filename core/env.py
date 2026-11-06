""".env faylini o'qish.

python-dotenv o'rniga — qo'shimcha kutubxona o'rnatmaslik uchun oddiy o'quvchi.
Fayl formati: KEY=VALUE, # bilan boshlangan qatorlar izoh.
"""
from __future__ import annotations

import os
from pathlib import Path

# Loyiha ildizi (core/ papkasining bir pog'ona yuqorisi)
ROOT = Path(__file__).resolve().parent.parent


def load_env(path: str | os.PathLike | None = None) -> bool:
    """`.env` faylidagi qiymatlarni os.environ ga qo'shadi.

    Allaqachon mavjud muhit o'zgaruvchilari o'zgartirilmaydi.
    Fayl topilsa True, bo'lmasa False qaytaradi.
    """
    p = Path(path) if path is not None else ROOT / ".env"
    if not p.is_absolute():
        p = ROOT / p
    if not p.is_file():
        return False

    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val
    return True
