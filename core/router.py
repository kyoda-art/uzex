"""Savolni tahlil vositasiga yo'naltirish.

- GEMINI_API_KEY bo'lsa: Gemini savolni tushunib, to'g'ri vosita va parametrlarni JSON ko'rinishida beradi.
- Kalit bo'lmasa yoki model xato qilsa: kalit so'zlarga asoslangan qoidalar ishlaydi.
Raqamlar har doim pandas bilan ma'lumotdan hisoblanadi — model javobni o'zi yozmaydi.
"""
from __future__ import annotations

import inspect
import json
import logging
import os
import re

from . import analytics as A
from .data import Dataset
from .formatter import NO_DATA, detect_lang, format_result

log = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-2.5-flash-lite"

TOOLS = {
    "summary": {"fn": A.summary, "doc": "overall market statistics: deal count, volume, executed deals, sellers and buyers counts; args: year"},
    "top_sellers": {"fn": A.top_sellers, "doc": "largest sellers by traded volume; args: year, n"},
    "top_buyers": {"fn": A.top_buyers, "doc": "largest buyers by traded volume; args: year, n"},
    "top_brokers": {"fn": A.top_brokers, "doc": "most active brokers by volume; args: year, n"},
    "top_products": {"fn": A.top_products, "doc": "most traded products by volume; args: year, n"},
    "top_regions": {"fn": A.top_regions, "doc": "regions by traded volume; args: year, n"},
    "price_trend": {"fn": A.price_trend, "doc": "monthly average unit price dynamics of a product; args: product (commodity name or keyword), year"},
    "anomalies": {"fn": A.anomalies, "doc": "deals with unit price far from the contract's typical price; args: year, n"},
    "risky_sellers": {"fn": A.risky_sellers, "doc": "sellers with highest share of annulled (unpaid) deals; args: year, n"},
    "trade_network": {"fn": A.trade_network, "doc": "largest seller-buyer trade pairs; args: year, n"},
    "forecast": {"fn": A.forecast, "doc": "forecast of monthly traded volume (last-year seasonality x recent growth); args: months (1-12)"},
    "usd_rate": {"fn": A.usd_rate, "doc": "USD exchange rate in UZS on a date; args: date (DD.MM.YYYY or null for latest)"},
}


def _clean(args: dict, ds: Dataset) -> dict:
    out = {}
    if args.get("year") not in (None, "", "null"):
        try:
            y = int(args["year"])
            out["year"] = y if y in ds.years else None
        except (TypeError, ValueError):
            pass
    if "n" in args:
        try:
            out["n"] = max(1, min(20, int(args["n"])))
        except (TypeError, ValueError):
            pass
    if "months" in args:
        try:
            out["months"] = max(1, min(12, int(args["months"])))
        except (TypeError, ValueError):
            pass
    if args.get("product"):
        out["product"] = str(args["product"])
    if args.get("date"):
        out["date"] = str(args["date"])
    return out


def _sources(tool: str, args: dict) -> list:
    if tool == "usd_rate":
        return ["usd_rates.csv"]
    year = args.get("year")
    files = [f"deals_{year}.csv" if year else "deals_2022–2026.csv", "usd_rates.csv"]
    if tool in ("top_sellers", "top_buyers", "trade_network", "risky_sellers"):
        files.append("participants.csv")
    if tool == "top_brokers":
        files.append("brokers.csv")
    if tool in ("price_trend", "anomalies"):
        files.append("contracts.csv")
    return files


def run_tool(ds: Dataset, tool: str, args: dict) -> dict:
    fn = TOOLS[tool]["fn"]
    allowed = inspect.signature(fn).parameters
    clean = _clean(args or {}, ds)
    kwargs = {k: v for k, v in clean.items() if k in allowed and k != "ds"}
    result = fn(ds, **kwargs)
    result.setdefault("meta", {})["sources"] = _sources(tool, clean)
    return result


# ---------- Qoidalarga asoslangan yo'naltirish ----------

KW = {
    "anomaly": ["anomal", "аномал", "ayritab", "айритаб", "подозрит", "shubhali"],
    "forecast": ["prognoz", "прогноз", "bashorat", "башорат", "forecast", "future", "kelajak", "будущ", "keyingi"],
    "risky": ["annul", "аннул", "bekor", "risk", "риск", "ishonchsiz"],
    "network": ["network", "tarmoq", "juftlik", "связ", "пары", "маршрут"],
    "usd": ["kurs", "курс", "usd"],
    "price": ["narx", "цен", "stoimost", "стоимост", "dinamika", "динамик", "price", "stoit", "стоит", "qancha", "сколько"],
    "broker": ["broker", "брокер"],
    "buyer": ["xaridor", "покуп"],
    "seller": ["sotuvchi", "продав"],
    "region": ["region", "viloyat", "hudud", "регион", "област"],
    "product": ["mahsulot", "tovar", "товар", "продукт", "product"],
    "summary": ["umumiy", "statistika", "xulosa", "hisobot", "bozor", "общ", "статист", "сводк", "итог", "обзор", "summary", "overview"],
}


def _has(t: str, key: str) -> bool:
    return any(k in t for k in KW[key])


def _year(t: str, ds: Dataset):
    m = re.search(r"\b(20\d{2})\b", t)
    if m and int(m.group(1)) in ds.years:
        return int(m.group(1))
    return None


def _n(t: str):
    m = re.search(r"(?<![\d.])(\d{1,2})(?![\d.])", t)
    return int(m.group(1)) if m else None


def _date(t: str):
    m = re.search(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{4})\b", t)
    if m:
        return f"{m.group(1)}.{m.group(2)}.{m.group(3)}"
    m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", t)
    if m:
        return f"{m.group(3)}.{m.group(2)}.{m.group(1)}"
    return None


def route_rules(text: str, ds: Dataset):
    t = text.lower()
    year = _year(t, ds)
    args = {"year": year, "n": _n(t)}
    if _has(t, "anomaly"):
        return "anomalies", args
    if _has(t, "forecast"):
        return "forecast", {}
    if _has(t, "risky"):
        return "risky_sellers", args
    if _has(t, "network"):
        return "trade_network", args
    if _has(t, "usd"):
        return "usd_rate", {"date": _date(t)}
    if _has(t, "price") and A.resolve_head(ds, t):
        return "price_trend", {"product": t, "year": year}
    if _has(t, "broker"):
        return "top_brokers", args
    if _has(t, "buyer"):
        return "top_buyers", args
    if _has(t, "seller"):
        return "top_sellers", args
    if _has(t, "region"):
        return "top_regions", args
    if _has(t, "product"):
        return "top_products", args
    if _has(t, "summary"):
        return "summary", {"year": year}
    return None, {}


# ---------- Gemini yo'naltirish ----------

ROUTER_PROMPT = """Savolga javob ber va uni vositaga yo'naltir. FAQAT JSON qaytar:
{"tool": "<vosita nomi yoki null>", "args": {...}, "reply": "<matn>"}
- Savol birja ma'lumotlari bo'yicha vosita bilan javob berilsa: tool va args ni to'ldir, reply ni "" qil.
- Aks holda: tool ni null qil va reply ga foydalanuvchi savoliga TO'LIQ javobingni yoz (savol tilida).
Birja raqamlarini o'zing o'ylab topma.

Vositalar:
{tools}

Args: year = 2022..2026 yoki null; n = 1..20; product = mahsulot nomi yoki kalit so'z; date = DD.MM.YYYY yoki null; months = 1..12.

Savol: """


def route_llm(client, text: str, ds: Dataset):
    """Bitta so'rov: vosita tanlash YOKI to'liq javob. Qaytaradi: (tool, args, reply)."""
    from google.genai import types  # import lazily: kutubxona faqat kalit bo'lganda kerak

    tools_txt = "\n".join(f"- {name}: {meta['doc']}" for name, meta in TOOLS.items())
    prompt = ROUTER_PROMPT.replace("{tools}", tools_txt) + text
    resp = client.models.generate_content(
        model=os.getenv("GEMINI_MODEL", DEFAULT_MODEL),
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=CHAT_SYSTEM,
            response_mime_type="application/json",
            temperature=0.5,
        ),
    )
    data = json.loads(resp.text or "{}")
    tool = data.get("tool")
    reply = (data.get("reply") or "").strip() or None
    if tool in TOOLS:
        args = data.get("args") or {}
        if tool == "price_trend" and not args.get("product"):
            return None, {}, reply
        return tool, args, None
    return None, {}, reply


def make_llm():
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        return None
    try:
        from google import genai
    except ImportError:
        log.warning("google-genai o'rnatilmagan, qoidalar rejimi ishlatiladi")
        return None
    return genai.Client(api_key=key)


CHAT_SYSTEM = """Sen UZEX birja bo'yicha AI-agentsan, lekin foydalanuvchining istalgan savoliga to'liq javob berasan:
oddiy suhbat, umumiy bilim, maslahat, tushuntirish. Foydalanuvchi qaysi tilda yozsa, o'sha tilda javob ber
(o'zbekcha lotin, kirill yoki ruscha). Javobni aniq va tushunarli yoz.
Agar savol UZEX bitimlarining aniq raqamlari haqida bo'lsa-yu, bu ma'lumot sening bazangda bo'lmasa, buni
ochiq ayt, umumiy tushuncha ber va aniq raqam so'ralsa, savolni yanada aniq yozishni tavsiya qil.
Birja raqamlarini o'zing o'ylab topma."""

CHAT_FALLBACK = {
    "uz": "Hozircha bu savolga javob bera olmayman. Birja bo'yicha savol bering, masalan: "
          "\"Umumiy statistika 2025\" yoki \"Dollar kursi 30.10.2026\".",
    "ru": "Пока не могу ответить на этот вопрос. Задайте вопрос о бирже, например: "
          "\"Общая статистика 2025\" или \"Курс доллара 30.10.2026\".",
}

AI_OFF = {
    "uz": "🔌 AI hozircha ulanmagan (GEMINI_API_KEY sozlanmagan). Birja savollari ishlayveradi.",
    "ru": "🔌 AI пока не подключён (GEMINI_API_KEY не задан). Вопросы по бирже работают.",
}

AI_ERR = {
    "uz": "⚠️ AI hozir javob bera olmadi. Birozdan keyin qayta urinib ko'ring.",
    "ru": "⚠️ AI сейчас не смог ответить. Попробуйте чуть позже.",
}


def chat_reply(llm, text: str, lang: str, history=None) -> str:
    """Oddiy suhbat javobi (Gemini). Raqamlar uchun bu funksiya ishlatilmaydi."""
    from google.genai import types

    transcript = ""
    for role, msg in (history or [])[-8:]:
        transcript += f"{'Foydalanuvchi' if role == 'user' else 'Agent'}: {msg}\n"
    prompt = transcript + f"Foydalanuvchi: {text}\nAgent:"
    resp = llm.models.generate_content(
        model=os.getenv("GEMINI_MODEL", DEFAULT_MODEL),
        contents=prompt,
        config=types.GenerateContentConfig(system_instruction=CHAT_SYSTEM, temperature=0.7),
    )
    out = (resp.text or "").strip()
    return out or AI_ERR[lang]


def chat_enabled() -> bool:
    return os.getenv("CHAT_ENABLED", "1").lower() not in ("0", "false", "no", "off")


def resolve(ds: Dataset, text: str, llm=None):
    """Qoidalar avval ishlaydi (Gemini kvotasini tejaydi). Topilmasa bitta Gemini so'rovi.
    Qaytaradi: (tool, args, reply). reply — Gemini to'liq javobi (vosita bo'lmaganda)."""
    tool, args = route_rules(text, ds)
    if tool:
        return tool, args, None
    if llm is None:
        return None, {}, None
    try:
        return route_llm(llm, text, ds)
    except Exception:
        log.exception("Gemini so'rovida xato")
        return None, {}, "__ERROR__"  # takroriy so'rov yubormaslik uchun belgi


def run_question(ds: Dataset, text: str, llm=None, history=None) -> dict:
    """Bitta savolni to'liq qayta ishlaydi: matn, vosita, parametrlar va natija."""
    lang = detect_lang(text)
    tool, args, reply = resolve(ds, text, llm)
    if tool:
        result = run_tool(ds, tool, args)
        return {"text": format_result(tool, result, lang), "tool": tool, "args": args,
                "result": result, "lang": lang}
    if chat_enabled():
        if llm is None:
            return {"text": AI_OFF[lang], "tool": None, "args": {}, "result": None, "lang": lang}
        if reply == "__ERROR__":
            return {"text": AI_ERR[lang], "tool": None, "args": {}, "result": None, "lang": lang}
        try:
            out = reply or chat_reply(llm, text, lang, history)
            return {"text": out, "tool": None, "args": {}, "result": None, "lang": lang}
        except Exception:
            log.exception("Suhbat javobida xato")
            return {"text": AI_ERR[lang], "tool": None, "args": {}, "result": None, "lang": lang}
    return {"text": CHAT_FALLBACK[lang], "tool": None, "args": {}, "result": None, "lang": lang}


def answer(ds: Dataset, text: str, llm=None, history=None) -> str:
    return run_question(ds, text, llm, history)["text"]
