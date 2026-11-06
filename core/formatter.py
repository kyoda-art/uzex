"""Natijalarni tanlangan tilda matnga aylantirish. Raqamlar faqat ma'lumotdan olinadi."""
from __future__ import annotations

import math
import re

NO_DATA = {"uz": "Ma'lumotda javob yo'q", "ru": "Ответа нет в данных"}

UNITS = {
    "uz": {"mlrd": "mlrd so'm", "som": "so'm", "rate": "so'm/USD"},
    "ru": {"mlrd": "млрд сум", "som": "сум", "rate": "сум/USD"},
}

LABELS = {
    "uz": {
        "deals": "Bitimlar soni", "volume": "Umumiy hajm", "executed": "Ijro etilgan bitimlar",
        "sellers": "Sotuvchilar", "buyers": "Xaridorlar", "forecast": "prognoz", "actual": "fakt",
    },
    "ru": {
        "deals": "Количество сделок", "volume": "Общий объём", "executed": "Исполненные сделки",
        "sellers": "Продавцы", "buyers": "Покупатели", "forecast": "прогноз", "actual": "факт",
    },
}

TITLES = {
    "summary": {"uz": "📊 Bozor xulosasi{year_s}", "ru": "📊 Сводка рынка{year_s}"},
    "top_sellers": {"uz": "🏆 Eng yirik sotuvchilar{year_s}", "ru": "🏆 Крупнейшие продавцы{year_s}"},
    "top_buyers": {"uz": "🛒 Eng yirik xaridorlar{year_s}", "ru": "🛒 Крупнейшие покупатели{year_s}"},
    "top_brokers": {"uz": "🤝 Eng faol brokerlar{year_s}", "ru": "🤝 Самые активные брокеры{year_s}"},
    "top_products": {"uz": "📦 Eng ko'p savdo qilingan mahsulotlar{year_s}",
                     "ru": "📦 Самые торгуемые товары{year_s}"},
    "top_regions": {"uz": "🗺 Hududlar bo'yicha savdo{year_s}", "ru": "🗺 Торговля по регионам{year_s}"},
    "price_trend": {"uz": "💹 Narx dinamikasi: {subject}{year_s}", "ru": "💹 Динамика цены: {subject}{year_s}"},
    "anomalies": {"uz": "🔎 Anomal bitimlar: jami {count} ta{year_s}",
                  "ru": "🔎 Аномальные сделки: всего {count}{year_s}"},
    "risky_sellers": {"uz": "⚠️ Annulyatsiya ulushi yuqori sotuvchilar (kamida {min_deals} ta bitim)",
                      "ru": "⚠️ Продавцы с высокой долей аннулирования (не менее {min_deals} сделок)"},
    "trade_network": {"uz": "🌐 Eng yirik savdo juftliklari{year_s}",
                      "ru": "🌐 Крупнейшие торговые пары{year_s}"},
    "forecast": {"uz": "🔮 Hajm prognozi (o'tgan yil mavsumiyligi, o'sish {growth_s}, taxminiy)",
                 "ru": "🔮 Прогноз объёма (сезонность прошлого года, рост {growth_s}, ориентировочно)"},
    "usd_rate": {"uz": "💵 Dollar kursi", "ru": "💵 Курс доллара"},
}


class _SafeDict(dict):
    def __missing__(self, key):
        return ""


def detect_lang(text: str) -> str:
    """Savol tilini aniqlaydi: o'zbekcha (lotin/kirill) yoki ruscha."""
    if re.search(r"[ўқғҳЎҚҒҲ]", text):
        return "uz"
    if re.search(r"[а-яёА-ЯЁ]", text):
        return "ru"
    return "uz"


def _sp(s: str) -> str:
    return s.replace(",", " ")


def fmt_value(v, vtype: str, cur: str | None, lang: str) -> str:
    u = UNITS[lang]
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    if vtype == "uzs":
        if abs(v) >= 1e9:
            return _sp(f"{v / 1e9:,.2f}") + f" {u['mlrd']}"
        return _sp(f"{v:,.0f}") + f" {u['som']}"
    if vtype == "count":
        return _sp(f"{v:,.0f}")
    if vtype == "pct":
        return f"{v * 100:.1f}%"
    if vtype == "ratio":
        return f"x{v:.2f}"
    if vtype == "rate":
        return _sp(f"{v:,.2f}") + f" {u['rate']}"
    if vtype == "price":
        unit = u["som"] if cur == "UZS" else "USD"
        return _sp(f"{v:,.2f}") + f" {unit}"
    return str(v)


def format_result(tool: str, result: dict, lang: str) -> str:
    rows = result.get("rows") or []
    if not rows:
        return NO_DATA[lang]
    meta = _SafeDict(result.get("meta") or {})
    meta.setdefault("year_s", "")
    title = TITLES[tool][lang].format_map(meta)

    out = [title, ""]
    for i, r in enumerate(rows, 1):
        if r.get("name") is not None:
            left = str(r["name"])
        else:
            left = LABELS[lang].get(r.get("label"), "")
        prefix = "• " if tool == "summary" else f"{i}. "
        line = prefix + left
        if r.get("code"):
            line += f" · {r['code']}"
        line += " — " + fmt_value(r.get("value"), r.get("vtype", "text"), r.get("cur"), lang)
        if r.get("tag"):
            line += f" ({LABELS[lang].get(r['tag'], r['tag'])})"
        out.append(line)
    return "\n".join(out)
