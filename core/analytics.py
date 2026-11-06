"""Tahlil funksiyalari. Har biri {"rows": [...], "meta": {...}} qaytaradi.

Ma'lumot topilmasa rows bo'sh ro'yxat bo'ladi — bu botda "Ma'lumotda javob yo'q" degani.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from .data import ANNULLED, EXECUTED, Dataset

FINISHED = {EXECUTED, "Исполнен(Частично)", ANNULLED}


def _row(**kw) -> dict:
    base = {"name": None, "label": None, "code": None, "tag": None, "value": None, "vtype": "text", "cur": None}
    base.update(kw)
    return base


def _res(rows, **meta) -> dict:
    return {"rows": rows, "meta": meta}


def _ys(year) -> str:
    return f" ({year})" if year else ""


def _sel(df: pd.DataFrame, year) -> pd.DataFrame:
    return df if year is None else df[df["year"] == year]


def _nm(ds: Dataset, inn) -> str:
    return ds.names.get(inn, str(inn))


def _top(df, col, n, namer, show_code=True, vtype="uzs"):
    g = df.groupby(col)["amount_uzs"].sum().sort_values(ascending=False).head(n)
    return [
        _row(name=namer(k), code=str(k) if show_code else None, value=float(v), vtype=vtype)
        for k, v in g.items()
    ]


# ---------- Umumiy ko'rsatkichlar ----------

def summary(ds: Dataset, year=None):
    df = _sel(ds.valid, year)
    if df.empty:
        return _res([])
    rows = [
        _row(label="deals", value=len(df), vtype="count"),
        _row(label="volume", value=float(df["amount_uzs"].sum()), vtype="uzs"),
        _row(label="executed", value=int((df["status"] == EXECUTED).sum()), vtype="count"),
        _row(label="sellers", value=int(df["seller"].nunique()), vtype="count"),
        _row(label="buyers", value=int(df["buyer"].nunique()), vtype="count"),
    ]
    if year is None:
        by_year = ds.valid.groupby("year")["amount_uzs"].sum()
        rows += [_row(name=str(y), value=float(v), vtype="uzs") for y, v in by_year.items()]
    return _res(rows, year_s=_ys(year))


def top_sellers(ds: Dataset, year=None, n=10):
    rows = _top(_sel(ds.valid, year), "seller", n, lambda k: _nm(ds, k))
    return _res(rows, year_s=_ys(year))


def top_buyers(ds: Dataset, year=None, n=10):
    rows = _top(_sel(ds.valid, year), "buyer", n, lambda k: _nm(ds, k))
    return _res(rows, year_s=_ys(year))


def top_brokers(ds: Dataset, year=None, n=10):
    rows = _top(_sel(ds.valid, year), "seller_broker", n, lambda k: ds.brokers.get(k, str(k)))
    return _res(rows, year_s=_ys(year))


def top_products(ds: Dataset, year=None, n=10):
    rows = _top(_sel(ds.valid, year), "product", n, lambda k: k, show_code=False)
    return _res(rows, year_s=_ys(year))


def top_regions(ds: Dataset, year=None, n=10):
    rows = _top(_sel(ds.valid, year), "region", n, lambda k: k, show_code=False)
    return _res(rows, year_s=_ys(year))


# ---------- Market Intelligence / narx dinamikasi ----------

def price_trend(ds: Dataset, product: str, year=None):
    """Mahsulot bo'yicha oylik o'rtacha birlik narx (shartnoma valyutasida)."""
    head = resolve_head(ds, product)
    if not head:
        return _res([])
    df = ds.valid[ds.valid["product"].str.lower().str.startswith(head)]
    df = _sel(df, year)
    if year is None:
        df = df[df["date"] >= ds.last_date - pd.DateOffset(months=12)]
    df = df[df["volume"] > 0]
    if df.empty:
        return _res([], subject=head.capitalize(), year_s=_ys(year))
    g = (
        df.groupby(["month", "currency"])
        .agg(amount=("amount", "sum"), volume=("volume", "sum"))
        .reset_index()
        .sort_values("month")
    )
    rows = [
        _row(name=str(r.month), value=float(r.amount / r.volume), vtype="price",
             cur="UZS" if "сум" in r.currency.lower() else "USD")
        for r in g.itertuples()
    ]
    return _res(rows, subject=head.capitalize(), year_s=_ys(year))


UZ_SYNONYMS = {
    "paxta": "хлопок", "bug'doy": "пшеница", "bugdoy": "пшеница", "bug‘doy": "пшеница",
    "un": "мука", "sement": "цемент", "shakar": "сахар", "benzin": "бензин",
    "dizel": "дизель", "yoqilg'i": "топливо", "yoqilg‘i": "топливо", "polietilen": "полиэтилен",
    "armatura": "арматура", "ammiak": "аммиачн", "mis": "медн", "guruch": "рис",
}


def _norm(text: str) -> str:
    t = text.lower().replace("’", "'").replace("‘", "'").replace("ʻ", "'")
    for uz, ru in UZ_SYNONYMS.items():
        t = re.sub(rf"\b{re.escape(uz)}\b", ru, t)
    return t


def resolve_head(ds: Dataset, text: str) -> str | None:
    """Matndagi mahsulot nomini (masalan 'хлопка', 'paxta') ma'lumotdagi bosh so'zga moslaydi."""
    t = _norm(text)
    words = re.findall(r"[^\W\d_]+", t)
    word_stems = [w[: max(4, len(w) - 2)] for w in words if len(w) >= 4]
    # Avval to'g'ridan-to'g'ri o'zak mosligi, bo'lmasa so'z o'zagi bo'yicha qidiriladi
    direct = [h for h in ds.heads if _stem(h) in t]
    found = direct or [h for h in ds.heads if any(ws in h for ws in word_stems)]
    if not found:
        return None
    return max(found, key=lambda h: (len(_stem(h)), ds.heads[h]))


def _stem(head: str) -> str:
    return head[: max(3, len(head) - 2)]


# ---------- Anomaly Hunter ----------

def anomalies(ds: Dataset, year=None, n=10, ratio=1.3, min_deals=5):
    """Shartnoma bo'yicha medianadan keskin farq qilgan birlik narxli bitimlar."""
    df = _sel(ds.valid, year)
    df = df[df["unit_price"].notna()].copy()
    if df.empty:
        return _res([])
    grp = df.groupby("contract_id")["unit_price"]
    df["median"] = grp.transform("median")
    df["cnt"] = grp.transform("size")
    df["ratio"] = df["unit_price"] / df["median"]
    flagged = df[(df["cnt"] >= min_deals) & ((df["ratio"] >= ratio) | (df["ratio"] <= 1 / ratio))].copy()
    total = len(flagged)
    if total == 0:
        return _res([], count=0)
    flagged["dev"] = np.abs(np.log(flagged["ratio"]))
    top = flagged.sort_values("dev", ascending=False).head(n)
    rows = [
        _row(
            name=f"{r.date:%d.%m.%Y} · №{r.deal_id} · {str(r.product)[:60]}",
            value=float(r.ratio),
            vtype="ratio",
        )
        for r in top.itertuples()
    ]
    return _res(rows, count=total, year_s=_ys(year))


def risky_sellers(ds: Dataset, year=None, n=10, min_deals=100):
    """Bitimlari ko'p bo'lgan sotuvchilar orasida annulyatsiya ulushi eng yuqorilari."""
    df = _sel(ds.deals, year)
    df = df[df["status"].isin(FINISHED)].copy()
    df["is_ann"] = df["status"].eq(ANNULLED)
    g = df.groupby("seller").agg(total=("deal_id", "size"), annulled=("is_ann", "sum"))
    g = g[g["total"] >= min_deals].copy()
    if g.empty:
        return _res([], min_deals=min_deals)
    g["rate"] = g["annulled"] / g["total"]
    g = g.sort_values("rate", ascending=False).head(n)
    rows = [
        _row(name=_nm(ds, inn), code=str(inn), value=float(r.rate), vtype="pct")
        for inn, r in g.iterrows()
    ]
    return _res(rows, min_deals=min_deals, year_s=_ys(year))


# ---------- Trade Network ----------

def trade_network(ds: Dataset, year=None, n=10):
    df = _sel(ds.valid, year)
    g = (
        df.groupby(["seller", "buyer"])["amount_uzs"]
        .sum()
        .sort_values(ascending=False)
        .head(n)
    )
    rows = [
        _row(name=f"{_nm(ds, s)} → {_nm(ds, b)}", code=f"{s} → {b}", value=float(v), vtype="uzs")
        for (s, b), v in g.items()
    ]
    return _res(rows, year_s=_ys(year))


# ---------- Future Vision ----------

def forecast(ds: Dataset, months=3):
    """Mavsumiylik + o'sish: maqsad oy = o'tgan yildagi shu oy * oxirgi 3 oylik o'sish sur'ati."""
    last = ds.last_date
    # Oy oxiri yaqin bo'lsa (masalan 30-oktabr) oy to'liq deb olinadi
    complete = last.day >= last.days_in_month - 1
    last_full = last.to_period("M") if complete else last.to_period("M") - 1
    s = ds.valid.groupby("month")["amount_uzs"].sum()
    s = s[s.index <= last_full]
    recent = s.iloc[-3:]
    prev = s.reindex(recent.index - 12)
    if len(recent) < 3 or prev.isna().any():
        return _res([])
    growth = float(recent.sum() / prev.sum())
    rows = [_row(name=str(p), value=float(v), vtype="uzs", tag="actual") for p, v in recent.items()]
    for k in range(1, months + 1):
        target = last_full + k
        base = s.get(target - 12)
        if base is None or pd.isna(base):
            continue
        rows.append(_row(name=str(target), value=float(base * growth), vtype="uzs", tag="forecast"))
    return _res(rows, growth_s=f"{(growth - 1) * 100:+.1f}%")


# ---------- Valyuta ----------

def usd_rate(ds: Dataset, date=None):
    ts = pd.to_datetime(date, dayfirst=True, errors="coerce") if date else ds.last_date
    if pd.isna(ts) or ts > ds.rates.index.max() or ts < ds.rates.index.min():
        return _res([])
    val = ds.rates.asof(ts)
    if pd.isna(val):
        return _res([])
    return _res([_row(name=ts.strftime("%d.%m.%Y"), value=float(val), vtype="rate")])
