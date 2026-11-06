"""UZEX AI agent — Telegram bot.

Ishga tushirish:
    export TELEGRAM_BOT_TOKEN=...      # BotFather'dan
    export GEMINI_API_KEY=...          # ixtiyoriy; bo'lmasa qoidalar rejimi ishlaydi
    python bot.py
"""
from __future__ import annotations

import asyncio
import logging
import os

from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from core.data import load
from core.formatter import format_result, detect_lang
from core.router import answer, make_llm, run_tool

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
log = logging.getLogger("uzex_bot")

# Menyu tugmalari (skrinshotdagi bo'limlar)
MENUS = {
    "uz": [
        ["📊 Market Intelligence"], ["🔎 Anomaly Hunter"], ["🔮 Future Vision"], ["🌐 Trade Network"],
        ["📑 Smart Reports"], ["🧠 NEXUS AI"], ["🌍 Til / Language", "ℹ️ Yordam"], ["🔄 Asosiy menyu"],
    ],
    "ru": [
        ["📊 Market Intelligence"], ["🔎 Anomaly Hunter"], ["🔮 Future Vision"], ["🌐 Trade Network"],
        ["📑 Smart Reports"], ["🧠 NEXUS AI"], ["🌍 Язык / Til", "ℹ️ Помощь"], ["🔄 Главное меню"],
    ],
}

# Tugma matni -> amal
ACTION_BY_LABEL = {
    "📊 Market Intelligence": "market",
    "🔎 Anomaly Hunter": "anomaly",
    "🔮 Future Vision": "future",
    "🌐 Trade Network": "trade",
    "📑 Smart Reports": "reports",
    "🧠 NEXUS AI": "nexus",
    "🌍 Til / Language": "lang",
    "🌍 Язык / Til": "lang",
    "ℹ️ Yordam": "help",
    "ℹ️ Помощь": "help",
    "🔄 Asosiy menyu": "menu",
    "🔄 Главное меню": "menu",
}

# Har bir bo'lim qaysi vositalarni ishga tushirishi
MODULE_PLAN = {
    "market": [("summary", {})],
    "anomaly": [("anomalies", {"n": 5}), ("risky_sellers", {"n": 5})],
    "future": [("forecast", {"months": 3})],
    "trade": [("trade_network", {"n": 10})],
    "reports": [("summary", {}), ("top_brokers", {"n": 5})],
}

TEXT = {
    "uz": {
        "welcome": (
            "Assalomu alaykum! Men UZEX birja bitimlari bo'yicha AI-agentman.\n"
            "Savolingizni yozing yoki menyudan bo'lim tanlang. Javoblar faqat birja ma'lumotlariga asoslanadi."
        ),
        "nexus": "🧠 Savolingizni yozing — men birja ma'lumotlari bo'yicha javob beraman.",
        "help": (
            "ℹ️ Yordam\n\n"
            "Misollar:\n"
            "• Umumiy statistika 2025\n"
            "• Eng yirik sotuvchilar 2026\n"
            "• Хлопок narxi dinamikasi 2025\n"
            "• Dollar kursi 30.10.2026\n"
            "• Anomal bitimlar 2025\n"
            "• Keyingi 3 oy prognoz\n\n"
            "Savol qaysi tilda bo'lsa, javob o'sha tilda beriladi (o'zbekcha yoki ruscha)."
        ),
        "lang_switched": "🌍 Til o'zgartirildi: O'zbekcha",
        "busy": "⏳ Hisoblanmoqda...",
        "error": "Xatolik yuz berdi. Iltimos, qayta urinib ko'ring.",
    },
    "ru": {
        "welcome": (
            "Здравствуйте! Я AI-агент по сделкам биржи UZEX.\n"
            "Задайте вопрос или выберите раздел в меню. Ответы основаны только на данных биржи."
        ),
        "nexus": "🧠 Задайте вопрос — я отвечу по данным биржи.",
        "help": (
            "ℹ️ Помощь\n\n"
            "Примеры:\n"
            "• Общая статистика 2025\n"
            "• Крупнейшие продавцы 2026\n"
            "• Динамика цены хлопка 2025\n"
            "• Курс доллара 30.10.2026\n"
            "• Аномальные сделки 2025\n"
            "• Прогноз на 3 месяца\n\n"
            "Ответ даётся на том языке, на котором задан вопрос (узбекский или русский)."
        ),
        "lang_switched": "🌍 Язык изменён: Русский",
        "busy": "⏳ Считаю...",
        "error": "Произошла ошибка. Попробуйте ещё раз.",
    },
}


def _ui(context: ContextTypes.DEFAULT_TYPE) -> str:
    return context.user_data.get("ui", "uz")


def _menu(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(MENUS[lang], resize_keyboard=True)


def _split(text: str, limit: int = 4000):
    """Telegram 4096 belgi cheklovi uchun uzun javobni bo'lib yuboradi."""
    parts, cur = [], ""
    for line in text.split("\n"):
        if len(cur) + len(line) + 1 > limit:
            parts.append(cur)
            cur = ""
        cur += line + "\n"
    if cur.strip():
        parts.append(cur)
    return parts


async def _send(update: Update, text: str, lang: str):
    for part in _split(text):
        await update.message.reply_text(part, reply_markup=_menu(lang))


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = _ui(context)
    await _send(update, TEXT[lang]["welcome"], lang)


async def run_module(update: Update, context: ContextTypes.DEFAULT_TYPE, module: str):
    ds = context.application.bot_data["ds"]
    lang = _ui(context)
    await update.message.reply_text(TEXT[lang]["busy"])
    blocks = []
    for tool, args in MODULE_PLAN[module]:
        result = await asyncio.to_thread(run_tool, ds, tool, args)
        blocks.append(format_result(tool, result, lang))
    await _send(update, "\n\n".join(blocks), lang)


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if not text:
        return

    action = ACTION_BY_LABEL.get(text)
    if action:
        if action == "lang":
            new = "ru" if _ui(context) == "uz" else "uz"
            context.user_data["ui"] = new
            await _send(update, TEXT[new]["lang_switched"], new)
        elif action == "help":
            await _send(update, TEXT[_ui(context)]["help"], _ui(context))
        elif action == "menu":
            await _send(update, TEXT[_ui(context)]["welcome"], _ui(context))
        elif action == "nexus":
            await _send(update, TEXT[_ui(context)]["nexus"], _ui(context))
        else:
            try:
                await run_module(update, context, action)
            except Exception:
                log.exception("Bo'lim xatosi: %s", action)
                await _send(update, TEXT[_ui(context)]["error"], _ui(context))
        return

    ds = context.application.bot_data["ds"]
    llm = context.application.bot_data.get("llm")
    lang = detect_lang(text)  # javob savol tilida
    await update.message.chat.send_action("typing")
    try:
        reply = await asyncio.to_thread(answer, ds, text, llm)
    except Exception:
        log.exception("Savolga javob berishda xato: %r", text)
        reply = TEXT[lang]["error"]
    await _send(update, reply, lang)


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN o'rnatilmagan")

    log.info("Birja ma'lumotlari yuklanmoqda...")
    ds = load()
    llm = make_llm()
    log.info("Bitimlar: %d, Gemini: %s", len(ds.deals), "ulangan" if llm else "yo'q (qoidalar rejimi)")

    app = Application.builder().token(token).build()
    app.bot_data["ds"] = ds
    app.bot_data["llm"] = llm
    app.add_handler(CommandHandler(["start", "menu"], cmd_start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    # Render Web Service (bepul tarif): PORT va RENDER_EXTERNAL_URL avtomatik beriladi.
    # Webhook rejimida Telegram xabarni servisga yuboradi, servis uxlagan bo'lsa ham uyg'onadi.
    port = os.environ.get("PORT")
    base_url = os.environ.get("RENDER_EXTERNAL_URL")
    if port and base_url:
        log.info("Webhook rejimi: %s", base_url)
        app.run_webhook(
            listen="0.0.0.0",
            port=int(port),
            url_path=token,
            webhook_url=f"{base_url}/{token}",
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
        )
    else:
        log.info("Polling rejimi (mahalliy)")
        app.run_polling()


if __name__ == "__main__":
    main()
