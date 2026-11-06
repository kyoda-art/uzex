"""Natijani CSV faylga aylantirish (Excel'da ochish uchun UTF-8 BOM bilan)."""
from __future__ import annotations

import pandas as pd


def to_csv_bytes(result: dict) -> bytes:
    rows = result.get("rows") or []
    df = pd.DataFrame([
        {
            "nomi": r.get("name") if r.get("name") is not None else r.get("label"),
            "kod": r.get("code"),
            "qiymat": r.get("value"),
            "turi": r.get("vtype"),
            "valyuta": r.get("cur"),
            "izoh": r.get("tag"),
        }
        for r in rows
    ])
    return df.to_csv(index=False).encode("utf-8-sig")
