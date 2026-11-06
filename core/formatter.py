"""Natijalarni tanlangan tilda matnga aylantirish. Raqamlar faqat ma'lumotdan olinadi.

`format_result(..., rich=True)` bo'lsa matnga Telegram HTML teglari (<b>, <i>) qo'shiladi —
bot uni parse_mode="HTML" bilan yuboradi. cli.py rich=False oladi va oddiy matn ko'radi.
"""
from __future__ import annotations

import html
import math
import re

NO_DATA = {"uz": "Ma'lumotda javob yo'q", "ru": "Ответа нет в данных"}

UNITS = {
    "uz": {"mlrd": "mlrd so'm", "som": "so'm", "rate": "so'm/USD", "dev": "medianadan", "src": "Manba"},
    "ru": {"mlrd": "млрд сум", "som": "сум", "rate": "сум/USD", "dev": "от медианы", "src": "Источник"},
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

# Karta (2-3 qatorli blok) ko'rinishida chiqadigan vositalar — nomlari uzun bo'lganlar
CARD_TOOLS = {"anomalies", "risky_sellers"}

# Juftlik ko'rinishi: "sotuvchi → xaridor" nomli qatorlar (karta bilan bir xil, faqat teskari tartibda)
PAIR_TOOLS = {"trade_network"}

# Karta sarlavhasi: (emoji, sarlavha, izoh-shablon). Izoh meta ma'lumotidan to'ldiriladi.
HEADERS = {
    "anomalies": {
        "uz": ("🔎", "Anomal bitimlar", "jami {count} ta"),
        "ru": ("🔎", "Аномальные сделки", "всего {count}"),
    },
    "risky_sellers": {
        "uz": ("⚠️", "Annulyatsiya ulushi yuqori sotuvchilar", "kamida {min_deals} ta bitim"),
        "ru": ("⚠️", "Продавцы с высокой долей аннулирования", "не менее {min_deals} сделок"),
    },
}

HINTS = {
    "anomalies": {
        "uz": "medianadan keskin chetlashgan bitimlar",
        "ru": "сделки с резким отклонением от медианы",
    },
    "risky_sellers": {
        "uz": "annulyatsiya (bekor qilingan) bitimlar ulushi bo'yicha",
        "ru": "по доле аннулированных сделок",
    },
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


def _esc(v) -> str:
    """HTML uchun xavfsiz matn (& < > belgilaridan himoya)."""
    return html.escape(str(v), quote=False)


def _dev(v: float) -> str:
    """0.34 -> '34%' — yo'nalish strelka bilan ko'rsatiladi, shuning uchun ishorasiz."""
    return f"{abs(v) * 100:.0f}%"


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
    if vtype == "dev":
        return f"{v * 100:+.0f}% {u['dev']}"
    if vtype == "rate":
        return _sp(f"{v:,.2f}") + f" {u['rate']}"
    if vtype == "price":
        unit = u["som"] if cur == "UZS" else "USD"
        return _sp(f"{v:,.2f}") + f" {unit}"
    return str(v)


def title_text(tool: str, result: dict, lang: str) -> str:
    meta = _SafeDict(result.get("meta") or {})
    meta.setdefault("year_s", "")
    return TITLES[tool][lang].format_map(meta)


# ---------- Oddiy ro'yxat ko'rinishi ----------

def _list_block(tool: str, rows: list, result: dict, lang: str, rich: bool) -> list[str]:
    title = title_text(tool, result, lang)
    out = [f"<b>{_esc(title)}</b>" if rich else title, ""]
    for i, r in enumerate(rows, 1):
        if r.get("name") is not None:
            left = str(r["name"])
        else:
            left = LABELS[lang].get(r.get("label"), "")
        prefix = "• " if tool == "summary" else f"{i}. "
        val = fmt_value(r.get("value"), r.get("vtype", "text"), r.get("cur"), lang)
        if rich:
            left, val = _esc(left), f"<b>{_esc(val)}</b>"
        line = prefix + left
        if r.get("code"):
            line += " · " + (_esc(r["code"]) if rich else str(r["code"]))
        line += " — " + val
        if r.get("tag"):
            tag = LABELS[lang].get(r["tag"], r["tag"])
            line += f" ({_esc(tag) if rich else tag})"
        out.append(line)
    return out


# ---------- Karta ko'rinishi (anomal bitimlar, riskli sotuvchilar) ----------

def _anomaly_card(i: int, r: dict, lang: str, rich: bool) -> list[str]:
    """Bitta bitim: sarlavha qatori (og'ish · sana · №) + mahsulot nomi alohida qatorda."""
    parts = [p.strip() for p in str(r.get("name") or "").split(" · ", 2)]
    date = parts[0] if len(parts) > 0 else ""
    deal = parts[1] if len(parts) > 1 else ""
    product = parts[2] if len(parts) > 2 else ""

    v = r.get("value")
    if isinstance(v, (int, float)) and not (isinstance(v, float) and math.isnan(v)):
        arrow, pct = ("⬇️" if v < 0 else "⬆️"), _dev(float(v))
    else:
        arrow, pct = "•", "—"

    head = f"{i}. {arrow} " + (f"<b>{pct}</b>" if rich else pct)
    extra = " · ".join(x for x in (date, deal) if x)
    if extra:
        head += " · " + (_esc(extra) if rich else extra)

    lines = [head]
    if product:
        lines.append(f"↳ <i>{_esc(product)}</i>" if rich else f"↳ {product}")
    return lines


def _risky_card(i: int, r: dict, lang: str, rich: bool) -> list[str]:
    """Bitta sotuvchi: annulyatsiya ulushi · nomi, tagida INN."""
    name = str(r.get("name") or "")
    code = str(r.get("code") or "")
    pct = fmt_value(r.get("value"), "pct", None, lang)

    head = f"{i}. " + (f"<b>{_esc(pct)}</b>" if rich else pct)
    if name:
        head += " · " + (_esc(name) if rich else name)

    lines = [head]
    if code:
        inn = "INN" if lang == "uz" else "ИНН"
        lines.append(f"↳ <i>{inn} {_esc(code)}</i>" if rich else f"↳ {inn} {code}")
    return lines


def _card_block(tool: str, rows: list, meta: dict, lang: str, rich: bool) -> list[str]:
    emoji, title, sub = HEADERS[tool][lang]
    head = f"{emoji} <b>{_esc(title)}</b>" if rich else f"{emoji} {title}"

    fill = _SafeDict({"count": meta.get("count"), "min_deals": meta.get("min_deals")})
    sub_txt = sub.format_map(fill) if (meta.get("count") is not None or meta.get("min_deals") is not None) else ""
    if sub_txt:
        head += " · " + (_esc(sub_txt) if rich else sub_txt)

    out = [head]
    hint = HINTS.get(tool, {}).get(lang)
    if hint:
        tail = f"{hint} · top {len(rows)}"
        out.append(f"<i>{_esc(tail)}</i>" if rich else tail)
    out.append("")

    for i, r in enumerate(rows, 1):
        if tool == "anomalies":
            out.extend(_anomaly_card(i, r, lang, rich))
        else:
            out.extend(_risky_card(i, r, lang, rich))
        out.append("")

    while out and out[-1] == "":
        out.pop()
    return out


def _pair_block(tool: str, rows: list, result: dict, lang: str, rich: bool) -> list[str]:
    """Savdo juftliklari: birinchi qatorda hajm, tagida "sotuvchi → xaridor"."""
    title = title_text(tool, result, lang)
    out = [f"<b>{_esc(title)}</b>" if rich else title, ""]
    for i, r in enumerate(rows, 1):
        name = str(r.get("name") or "")
        val = fmt_value(r.get("value"), r.get("vtype", "uzs"), r.get("cur"), lang)
        if rich:
            out.append(f"{i}. <b>{_esc(val)}</b>")
            out.append(f"↳ <i>{_esc(name)}</i>")
        else:
            out.append(f"{i}. {name} — {val}")
        out.append("")
    while out and out[-1] == "":
        out.pop()
    return out


def _forecast_block(rows: list, result: dict, lang: str) -> list[str]:
    """Prognozni ustunlari tekislangan jadval (monospace <pre>) ko'rinishida beradi."""
    title = title_text("forecast", result, lang)
    unit = "mlrd so'm" if lang == "uz" else "млрд сум"
    c_month = "Oy" if lang == "uz" else "Месяц"
    c_state = "Holat" if lang == "uz" else "Статус"

    table = [f"{c_month:<8}{unit:>12}  {c_state}", "─" * 28]
    for r in rows:
        v = r.get("value")
        if v is None:
            num = "—"
        elif abs(v) >= 1e9:
            num = _sp(f"{v / 1e9:,.2f}")
        else:
            num = _sp(f"{v:,.0f}")
        state = LABELS[lang].get(r.get("tag"), "") if r.get("tag") else ""
        table.append(f"{str(r.get('name') or ''):<8}{num:>12}  {state}")

    return [f"<b>{_esc(title)}</b>", "", "<pre>" + _esc("\n".join(table)) + "</pre>"]


def format_result(tool: str, result: dict, lang: str, rich: bool = False) -> str:
    """Natijani matnga aylantiradi.

    rich=True — Telegram HTML teglari bilan (bot parse_mode="HTML" yuboradi).
    rich=False — oddiy matn (cli.py, loglar, testlar).
    """
    rows = result.get("rows") or []
    if not rows:
        return NO_DATA[lang]

    meta = result.get("meta") or {}
    if tool in CARD_TOOLS:
        out = _card_block(tool, rows, meta, lang, rich)
    elif tool in PAIR_TOOLS:
        out = _pair_block(tool, rows, result, lang, rich)
    elif tool == "forecast" and rich:
        out = _forecast_block(rows, result, lang)
    else:
        out = _list_block(tool, rows, result, lang, rich)

    sources = meta.get("sources")
    if sources:
        src = ", ".join(_esc(s) if rich else str(s) for s in sources)
        line = f"📎 {UNITS[lang]['src']}: {src}"
        out += ["", f"<i>{line}</i>" if rich else line]
    return "\n".join(out)
