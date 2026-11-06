"""UZEX birja ma'lumotlarini yuklash va tayyorlash (xotiraga tejamkor)."""
from __future__ import annotations

import glob
import logging
import os
import re
import urllib.request
import zipfile
from dataclasses import dataclass

import pandas as pd

log = logging.getLogger(__name__)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.getenv("UZEX_DATA_DIR", os.path.join(ROOT, "data", "uzex_spot_data"))

EXECUTED = "Исполнен"
ANNULLED = "Аннулирован(Не оплачен)"
# Bu holatdagi bitimlar amalga oshmagan — tahlildan chiqariladi
NOT_REALIZED = {ANNULLED, "Не подписан"}

# Faqat kerakli ustunlar o'qiladi (xotirani tejash uchun)
DEAL_COLS = {
    "Номер сделки": "deal_id",
    "Дата сделки": "date_s",
    "Тип торгов": "auction",
    "Количество": "qty_s",
    "Сумма сделки": "amount_s",
    "Номер контракта": "contract_id",
    "Наименование товара": "product",
    "Лот": "lot_s",
    "Регион": "region",
    "Состояние сделки": "status",
    "ИНН продавца": "seller",
    "ИНН покупателя": "buyer",
    "Брокер продавца": "seller_broker",
}
CATEGORY_COLS = ["contract_id", "product", "region", "status", "auction", "seller", "buyer", "seller_broker", "currency"]


def _num(s: pd.Series) -> pd.Series:
    """'304 547 938.4' -> 304547938.4 (bo'shliqli minglik ajratgich)."""
    cleaned = s.astype(str).str.replace(r"\s+", "", regex=True).str.replace(",", ".", regex=False)
    return pd.to_numeric(cleaned, errors="coerce")


def ensure_data(data_dir: str = DATA_DIR) -> None:
    """Ma'lumot yo'q bo'lsa DATA_URL dan (zip) yuklab oladi. Serverda ishlatiladi."""
    if glob.glob(os.path.join(data_dir, "deals_*.csv")):
        return
    url = os.getenv("DATA_URL")
    if not url:
        raise FileNotFoundError(f"Ma'lumot topilmadi: {data_dir}. DATA_URL o'rnating yoki fayllarni joylang.")
    dest_parent = os.path.dirname(os.path.abspath(data_dir))  # zip ichida uzex_spot_data/ papkasi bor
    os.makedirs(dest_parent, exist_ok=True)
    tmp = os.path.join(dest_parent, "_data.zip")
    log.info("Ma'lumot yuklab olinmoqda...")
    urllib.request.urlretrieve(url, tmp)
    with zipfile.ZipFile(tmp) as z:
        z.extractall(dest_parent)
    os.remove(tmp)


@dataclass
class Dataset:
    deals: pd.DataFrame      # barcha bitimlar
    valid: pd.DataFrame      # amalga oshgan bitimlar (annulyatsiyasiz, imzosiz emas)
    names: dict              # STIR -> kompaniya nomi
    brokers: dict            # broker kodi -> nomi
    heads: dict              # mahsulot "bosh so'zi" -> bitimlar soni
    rates: pd.Series         # kun -> USD kursi (so'm)
    last_date: pd.Timestamp
    years: list


def load(data_dir: str = DATA_DIR) -> Dataset:
    ensure_data(data_dir)
    files = sorted(glob.glob(os.path.join(data_dir, "deals_*.csv")))

    raw = pd.concat(
        [pd.read_csv(f, dtype=str, usecols=list(DEAL_COLS)) for f in files],
        ignore_index=True,
    ).rename(columns=DEAL_COLS)

    d = pd.DataFrame()
    d["deal_id"] = raw["deal_id"]
    d["date"] = pd.to_datetime(raw["date_s"], format="%d.%m.%Y", errors="coerce")
    d["year"] = d["date"].dt.year.astype("Int16")
    d["month"] = d["date"].dt.to_period("M")
    qty = _num(raw["qty_s"])
    lot = _num(raw["lot_s"]).fillna(1.0)
    d["qty"] = qty
    d["volume"] = qty * lot
    d["amount"] = _num(raw["amount_s"])
    for c in ["contract_id", "product", "region", "status", "auction", "seller", "buyer", "seller_broker"]:
        d[c] = raw[c].astype("category")
    del raw

    # Valyuta shartnomadan olinadi
    contracts = pd.read_csv(
        os.path.join(data_dir, "contracts.csv"), dtype=str, usecols=["Номер контракта", "Валюта"]
    )
    currency = dict(zip(contracts["Номер контракта"], contracts["Валюта"]))
    del contracts
    d["currency"] = d["contract_id"].map(currency).fillna("Узбекский сум").astype("category")
    d["is_usd"] = d["currency"].astype(str).str.contains("Доллар", case=False, na=False)

    # Dollar kursi: har kun uchun, bo'sh kunlar oldingi kurs bilan to'ldiriladi
    rr = pd.read_csv(os.path.join(data_dir, "usd_rates.csv"), dtype=str)
    rates = pd.Series(
        _num(rr["Курс"]).to_numpy(),
        index=pd.to_datetime(rr["Дата"], format="%d.%m.%Y"),
    )
    rates = rates[~rates.index.duplicated(keep="last")].sort_index().asfreq("D").ffill()
    d["rate"] = rates.reindex(d["date"]).to_numpy()

    # Hamma summalar so'mda (USD bitimlar bitim kunidagi kurs bo'yicha)
    d["amount_uzs"] = d["amount"].where(~d["is_usd"], d["amount"] * d["rate"])
    # Birlik narx — shartnoma valyutasida
    d["unit_price"] = (d["amount"] / d["volume"]).where(d["volume"] > 0)

    valid = d[~d["status"].astype(str).isin(NOT_REALIZED)]

    parts = pd.read_csv(os.path.join(data_dir, "participants.csv"), dtype=str, usecols=["ИНН", "Наименование"])
    names = dict(zip(parts["ИНН"], parts["Наименование"]))
    brk = pd.read_csv(os.path.join(data_dir, "brokers.csv"), dtype=str, usecols=["Код брокера", "Наименование"])
    brokers = dict(zip(brk["Код брокера"], brk["Наименование"]))

    heads: dict = {}
    for p, cnt in d["product"].value_counts().items():
        m = re.match(r"[^\W\d_]+", str(p).lower())
        if m and len(m.group()) >= 3:
            heads[m.group()] = heads.get(m.group(), 0) + int(cnt)

    return Dataset(
        deals=d,
        valid=valid,
        names=names,
        brokers=brokers,
        heads=heads,
        rates=rates,
        last_date=d["date"].max(),
        years=sorted(int(y) for y in d["year"].dropna().unique()),
    )
