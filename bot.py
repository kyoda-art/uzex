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
import threading

from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from core.data import load
from core.formatter import format_result, detect_lang
from core.router import answer, make_llm, run_tool
from core.health import start_health_server

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

GREETINGS = {
    "salom", "assalomu alaykum", "assalomu alaykum!", "salom alik", "hello", "hi", "privet",
    "привет", "здравствуйте", "здравствуй", "салом", "ассалому алейкум", "qalaysiz", "qalesiz",
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
        "loading": "⏳ Birja ma'lumotlari yuklanmoqda, bir necha daqiqa kuting va qayta yozing.",
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
        "loading": "⏳ Данные биржи загружаются, подождите пару минут и напишите снова.",
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
    lang = _ui(context)
    ds = context.application.bot_data.get("ds")
    if ds is None:
        await _send(update, TEXT[lang]["loading"], lang)
        return
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

    lang = detect_lang(text)  # javob savol tilida
    if text.lower().strip(" !.,") in GREETINGS:
        await _send(update, TEXT[lang]["welcome"], lang)
        return
    ds = context.application.bot_data.get("ds")
    if ds is None:
        await _send(update, TEXT[lang]["loading"], lang)
        return
    llm = context.application.bot_data.get("llm")
    history = context.user_data.setdefault("history", [])
    await update.message.chat.send_action("typing")
    try:
        reply = await asyncio.to_thread(answer, ds, text, llm, list(history))
    except Exception:
        log.exception("Savolga javob berishda xato: %r", text)
        reply = TEXT[lang]["error"]
    history.append(("user", text))
    history.append(("agent", reply))
    del history[:-10]  # oxirgi 10 ta xabar
    await _send(update, reply, lang)


async def _post_init(app: Application):
    # Oldin webhook o'rnatilgan bo'lsa, polling ishlashi uchun uni o'chiramiz
    await app.bot.delete_webhook(drop_pending_updates=True)
    log.info("Webhook o'chirildi, polling boshlandi")


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN o'rnatilmagan")

    app = Application.builder().token(token).post_init(_post_init).build()
    app.bot_data["ds"] = None
    app.bot_data["llm"] = make_llm()
    log.info("Gemini: %s", "ulangan" if app.bot_data["llm"] else "yo'q (qoidalar rejimi)")

    # Ma'lumot fonda yuklanadi
    def _load_data():
        try:
            log.info("Birja ma'lumotlari yuklanmoqda...")
            app.bot_data["ds"] = load()
            log.info("Bitimlar tayyor: %d", len(app.bot_data["ds"].deals))
        except Exception:
            log.exception("Ma'lumot yuklanmadi")

    threading.Thread(target=_load_data, daemon=True).start()

    app.add_handler(CommandHandler(["start", "menu"], cmd_start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    # Render'da (PORT bor): monitor uchun HTTP javob. Mahalliy ishda port kerak emas.
    port = os.environ.get("PORT")
    if port:
        start_health_server(int(port))

    log.info("Polling rejimi boshlandi")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
